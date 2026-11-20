import dataclasses
import sys
from pathlib import Path

import duckdb
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import analytics, extract, load, transform  # noqa: E402
from pipeline.config import load_settings  # noqa: E402


@pytest.fixture()
def settings(tmp_path):
    s = load_settings()
    return dataclasses.replace(
        s, regions=["US", "GB"], raw_dir=tmp_path / "raw", staging_dir=tmp_path / "staging",
        warehouse=tmp_path / "wh" / "t.duckdb", reports_dir=tmp_path / "reports",
    )


def _row(**kw):
    base = dict(video_id="a1", title="T", publishedAt="2024-01-01T10:00:00Z", channelId="c1",
                channelTitle="Chan", categoryId=10, trending_date="2024-01-03T00:00:00Z",
                tags="a|b", view_count=1000, likes=100, dislikes=0, comment_count=10,
                thumbnail_link="x", comments_disabled=False, ratings_disabled=False, description="d")
    base.update(kw)
    return base


def test_clean_derives_metrics(settings):
    good, bad = transform.clean(pd.DataFrame([_row()]), "US", settings)
    assert len(good) == 1 and bad.empty
    r = good.iloc[0]
    assert r["days_to_trend"] == 2
    assert r["engagement_rate"] == pytest.approx(0.11)
    assert r["like_ratio"] == pytest.approx(0.1)
    assert r["tag_count"] == 2 and r["publish_hour"] == 10


def test_clean_rejects_bad_rows_with_reasons(settings):
    df = pd.DataFrame([
        _row(video_id="ok"),
        _row(video_id=None),
        _row(video_id="neg", view_count=-5),
        _row(video_id="baddate", trending_date="nope"),
        _row(video_id="early", trending_date="2000-01-01T00:00:00Z"),
        _row(video_id="dup"), _row(video_id="dup", view_count=500),
    ])
    good, bad = transform.clean(df, "US", settings)
    assert sorted(good["video_id"]) == ["dup", "ok"]
    assert int(good.loc[good.video_id == "dup", "views"].iloc[0]) == 1000  # keeps highest snapshot
    reasons = set(bad["reject_reason"])
    assert {"missing video_id", "invalid view count", "invalid trending_date",
            "trended before publication", "duplicate (region, video, day)"} <= reasons


def test_none_tags_and_zero_views_are_safe(settings):
    good, _ = transform.clean(pd.DataFrame([_row(tags="[None]", view_count=0)]), "US", settings)
    assert good.iloc[0]["tag_count"] == 0
    assert pd.isna(good.iloc[0]["engagement_rate"])


def test_end_to_end_with_sample_data(settings):
    extract.generate_sample(settings, videos_per_region=60, days=40)
    stats = transform.run(settings)
    assert all(v["rejected"] > 0 and v["clean"] > 0 for v in stats.values())
    counts = load.run(settings)
    assert counts["fact_trending"] == sum(v["clean"] for v in stats.values())

    con = duckdb.connect(str(settings.warehouse), read_only=True)
    assert con.execute("SELECT count(*) FROM vw_trending").fetchone()[0] == counts["fact_trending"]
    con.close()

    analytics.run(settings, stats)
    assert (settings.reports_dir / "report.html").stat().st_size > 5000
    assert (settings.reports_dir / "02_category_performance.csv").exists()
