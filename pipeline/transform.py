"""Transform: clean, validate and enrich the raw trending data."""
from __future__ import annotations

import json
import logging

import pandas as pd

from .config import Settings
from .extract import CATEGORY_SUFFIX, CSV_SUFFIX

log = logging.getLogger(__name__)

NUMERIC_COLS = ["view_count", "likes", "dislikes", "comment_count"]
BOOL_COLS = ["comments_disabled", "ratings_disabled"]


# `description` is the bulk of each ~400 MB file and no analysis uses it, so it is never loaded.
USE_COLS = ["video_id", "title", "publishedAt", "channelId", "channelTitle", "categoryId",
            "trending_date", "tags", "view_count", "likes", "dislikes", "comment_count",
            "thumbnail_link", "comments_disabled", "ratings_disabled"]


def read_raw_csv(path) -> pd.DataFrame:
    kw = dict(usecols=USE_COLS, low_memory=False)
    try:
        return pd.read_csv(path, encoding="utf-8", **kw)
    except UnicodeDecodeError:
        return pd.read_csv(path, encoding="latin-1", **kw)


def read_categories(path) -> pd.DataFrame:
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    return pd.DataFrame(
        {"category_id": [int(i["id"]) for i in items],
         "category_name": [i["snippet"]["title"] for i in items]}
    )


def clean(df: pd.DataFrame, region: str, s: Settings) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (clean_rows, rejected_rows). Rejected rows carry a `reject_reason`."""
    df = df.copy()
    df["region"] = region

    # ---- type coercion ----
    df["published_at"] = pd.to_datetime(df["publishedAt"], errors="coerce", utc=True)
    df["trending_date"] = pd.to_datetime(df["trending_date"], errors="coerce", utc=True)
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in BOOL_COLS:
        df[col] = df[col].astype("string").str.lower().isin(["true", "1"])
    df["category_id"] = pd.to_numeric(df["categoryId"], errors="coerce").astype("Int64")

    # ---- text normalisation ----
    df["title"] = df["title"].astype("string").str.strip()
    df["channel_title"] = df["channelTitle"].astype("string").str.strip()
    df["tags"] = df["tags"].fillna("").astype("string").replace({"[None]": ""})
    df["tag_count"] = df["tags"].map(lambda t: len([x for x in t.split("|") if x]))
    df = df.rename(columns={"video_id": "video_id", "channelId": "channel_id",
                            "view_count": "views", "comment_count": "comments"})
    df["video_id"] = df["video_id"].astype("string").str.strip()

    # ---- validation: first failing rule wins ----
    reason = pd.Series(pd.NA, index=df.index, dtype="string")

    def flag(mask: pd.Series, text: str) -> None:
        nonlocal reason
        reason = reason.mask(mask & reason.isna(), text)

    flag(df["video_id"].isna() | (df["video_id"] == ""), "missing video_id")
    flag(df["trending_date"].isna(), "invalid trending_date")
    flag(df["published_at"].isna(), "invalid publishedAt")
    flag(df["views"].isna() | (df["views"] < s.min_views), "invalid view count")
    flag((df["likes"] < 0) | (df["dislikes"] < 0) | (df["comments"] < 0), "negative engagement count")
    flag(df["title"].isna() | (df["title"].str.len() > s.max_title_length), "invalid title")
    # trending_date is a date stamped at 00:00, so compare whole days (same-day trending is valid)
    flag(df["trending_date"].dt.normalize() < df["published_at"].dt.normalize(), "trended before publication")

    rejected = df[reason.notna()].assign(reject_reason=reason[reason.notna()])
    good = df[reason.isna()].copy()

    # ---- de-duplicate: a video appears once per region per trending day ----
    # keep the row with the highest view count (latest snapshot of that day)
    good["trending_day"] = good["trending_date"].dt.tz_localize(None).dt.normalize()
    good = good.sort_values("views", ascending=False)
    dup_mask = good.duplicated(["region", "video_id", "trending_day"], keep="first")
    dups = good[dup_mask].assign(reject_reason="duplicate (region, video, day)")
    good = good[~dup_mask].sort_values(["trending_day", "video_id"]).reset_index(drop=True)
    rejected = pd.concat([rejected, dups], ignore_index=True)

    # ---- missing counts -> 0, then derive metrics ----
    for col in ["views", "likes", "dislikes", "comments"]:
        good[col] = good[col].fillna(0).astype("int64")
    safe_views = good["views"].where(good["views"] > 0)
    good["like_ratio"] = (good["likes"] / safe_views).round(6)
    good["engagement_rate"] = ((good["likes"] + good["comments"]) / safe_views).round(6)
    good["days_to_trend"] = (
        (good["trending_day"] - good["published_at"].dt.tz_localize(None).dt.normalize()).dt.days
    )
    good["published_at"] = good["published_at"].dt.tz_localize(None)
    good["publish_hour"] = good["published_at"].dt.hour

    keep = ["region", "video_id", "title", "channel_id", "channel_title", "category_id",
            "published_at", "publish_hour", "trending_day", "views", "likes", "dislikes",
            "comments", "like_ratio", "engagement_rate", "days_to_trend", "tags", "tag_count",
            "comments_disabled", "ratings_disabled", "thumbnail_link"]
    rejected_cols = ["region", "video_id", "title", "reject_reason"]
    rejected = rejected.reindex(columns=rejected_cols)
    return good[keep], rejected


def run(s: Settings) -> dict:
    """Clean every configured region, write parquet/CSV into staging, return row counts."""
    s.staging_dir.mkdir(parents=True, exist_ok=True)
    cleaned, rejects, cats = [], [], []
    stats = {}
    for region in s.regions:
        raw = read_raw_csv(s.raw_dir / f"{region}{CSV_SUFFIX}")
        good, bad = clean(raw, region, s)
        cleaned.append(good)
        rejects.append(bad)
        cat_path = s.raw_dir / f"{region}{CATEGORY_SUFFIX}"
        if cat_path.exists():
            cats.append(read_categories(cat_path))
        stats[region] = {"raw": len(raw), "clean": len(good), "rejected": len(bad)}
        log.info("%s: %d raw -> %d clean, %d rejected", region, len(raw), len(good), len(bad))

    pd.concat(cleaned, ignore_index=True).to_parquet(s.staging_dir / "videos_clean.parquet", index=False)
    pd.concat(rejects, ignore_index=True).to_csv(s.staging_dir / "rejected.csv", index=False)
    cat_df = pd.concat(cats, ignore_index=True).drop_duplicates("category_id") if cats else \
        pd.DataFrame(columns=["category_id", "category_name"])
    cat_df.to_parquet(s.staging_dir / "categories.parquet", index=False)
    return stats
