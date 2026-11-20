"""Extract: obtain the raw Kaggle files (download, or generate a synthetic sample)."""
from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta, timezone

import pandas as pd

from .config import Settings

log = logging.getLogger(__name__)

CSV_SUFFIX = "_youtube_trending_data.csv"
CATEGORY_SUFFIX = "_category_id.json"

RAW_COLUMNS = [
    "video_id", "title", "publishedAt", "channelId", "channelTitle", "categoryId",
    "trending_date", "tags", "view_count", "likes", "dislikes", "comment_count",
    "thumbnail_link", "comments_disabled", "ratings_disabled", "description",
]


def raw_files_present(s: Settings) -> bool:
    return all((s.raw_dir / f"{r}{CSV_SUFFIX}").exists() for r in s.regions)


def download_from_kaggle(s: Settings) -> None:
    """Download the dataset with the official Kaggle API.

    Needs credentials: ~/.kaggle/kaggle.json, or KAGGLE_USERNAME + KAGGLE_KEY env vars.
    """
    try:
        from kaggle.api.kaggle_api_extended import KaggleApi
    except (Exception, SystemExit) as exc:  # importing kaggle authenticates and may sys.exit()
        raise RuntimeError(_credential_help()) from exc

    api = KaggleApi()
    try:
        api.authenticate()
    except (Exception, SystemExit) as exc:
        raise RuntimeError(_credential_help()) from exc

    s.raw_dir.mkdir(parents=True, exist_ok=True)
    # The full dataset is several GB (11 countries); fetch only the configured regions.
    for region in s.regions:
        for name in (f"{region}{CATEGORY_SUFFIX}", f"{region}{CSV_SUFFIX}"):
            target = s.raw_dir / name
            if target.exists():
                log.info("Already present, skipping %s", name)
                continue
            log.info("Downloading %s/%s", s.dataset, name)
            api.dataset_download_file(s.dataset, name, path=str(s.raw_dir), force=True, quiet=False)
            _unzip_if_needed(s.raw_dir, name)
            if not target.exists():
                raise RuntimeError(f"Download finished but {target} was not created")


def _unzip_if_needed(raw_dir, name: str) -> None:
    import zipfile

    archive = raw_dir / f"{name}.zip"
    if archive.exists():
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(raw_dir)
        archive.unlink()


def _credential_help() -> str:
    return (
        "Kaggle credentials not found. Create an API token at "
        "https://www.kaggle.com/settings and either save it to ~/.kaggle/access_token "
        "(or kaggle.json), or set KAGGLE_API_TOKEN (or KAGGLE_USERNAME + KAGGLE_KEY). "
        "Alternatively download the dataset manually into data/raw/, or run with --sample."
    )


# --------------------------------------------------------------------------- sample
_CATEGORIES = {
    "1": "Film & Animation", "2": "Autos & Vehicles", "10": "Music", "15": "Pets & Animals",
    "17": "Sports", "20": "Gaming", "22": "People & Blogs", "23": "Comedy",
    "24": "Entertainment", "25": "News & Politics", "26": "Howto & Style",
    "27": "Education", "28": "Science & Technology",
}
_WORDS = ["Epic", "Official", "Trailer", "Highlights", "Reaction", "Review", "Challenge",
          "Behind the Scenes", "Live", "Top 10", "Funny", "Tutorial", "Vlog", "Recap"]
_TAGS = ["music", "funny", "gaming", "news", "sports", "tech", "vlog", "review", "trailer", "viral"]


def generate_sample(s: Settings, videos_per_region: int = 400, days: int = 60, seed: int = 7) -> None:
    """Write synthetic files in the exact Kaggle schema, including deliberately dirty rows."""
    rng = random.Random(seed)
    s.raw_dir.mkdir(parents=True, exist_ok=True)
    end = datetime(2024, 3, 31, tzinfo=timezone.utc)
    start = end - timedelta(days=days)

    for region in s.regions:
        channels = [(f"UC{region}{i:05d}", f"{region} Channel {i}") for i in range(60)]
        rows = []
        for v in range(videos_per_region):
            vid = f"{region}{v:08d}"
            ch_id, ch_title = rng.choice(channels)
            cat = rng.choice(list(_CATEGORIES))
            published = start + timedelta(days=rng.randint(0, days - 5), hours=rng.randint(0, 23),
                                          minutes=rng.randint(0, 59))
            title = f"{rng.choice(_WORDS)} {rng.choice(_WORDS)} #{v}"
            tags = "|".join(rng.sample(_TAGS, rng.randint(0, 5))) or "[None]"
            base_views = int(rng.lognormvariate(12, 1.2))
            lag = rng.randint(1, 3)  # days between publication and first trending day
            for d in range(rng.randint(1, 6)):  # consecutive days on the trending list
                t_date = published + timedelta(days=d + lag)
                if t_date > end:
                    break
                views = int(base_views * (1 + 0.6 * d))
                likes = int(views * rng.uniform(0.01, 0.08))
                rows.append({
                    "video_id": vid, "title": title,
                    "publishedAt": published.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "channelId": ch_id, "channelTitle": ch_title, "categoryId": int(cat),
                    "trending_date": t_date.strftime("%Y-%m-%dT00:00:00Z"),
                    "tags": tags, "view_count": views, "likes": likes,
                    "dislikes": 0, "comment_count": int(likes * rng.uniform(0.02, 0.2)),
                    "thumbnail_link": f"https://i.ytimg.com/vi/{vid}/default.jpg",
                    "comments_disabled": rng.random() < 0.03, "ratings_disabled": rng.random() < 0.02,
                    "description": rng.choice(["", "Subscribe for more!", "Official video."]),
                })

        df = pd.DataFrame(rows, columns=RAW_COLUMNS)
        # --- dirty data so the cleaning stage has real work to do ---
        dup = df.sample(frac=0.02, random_state=seed)
        bad_views = df.sample(n=5, random_state=seed + 1).assign(view_count=-10)
        bad_date = df.sample(n=5, random_state=seed + 2).assign(trending_date="not-a-date")
        no_id = df.sample(n=3, random_state=seed + 3).assign(video_id=None)
        before_pub = df.sample(n=4, random_state=seed + 4).assign(trending_date="2000-01-01T00:00:00Z")
        df = pd.concat([df, dup, bad_views, bad_date, no_id, before_pub], ignore_index=True)
        df.loc[df.sample(frac=0.01, random_state=seed + 5).index, "description"] = None

        df.to_csv(s.raw_dir / f"{region}{CSV_SUFFIX}", index=False, encoding="utf-8")
        items = [{"kind": "youtube#videoCategory", "id": k,
                  "snippet": {"title": v, "assignable": True}} for k, v in _CATEGORIES.items()]
        (s.raw_dir / f"{region}{CATEGORY_SUFFIX}").write_text(
            json.dumps({"kind": "youtube#videoCategoryListResponse", "items": items}), encoding="utf-8")
        log.info("Sample %s: %d raw rows", region, len(df))
