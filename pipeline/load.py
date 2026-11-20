"""Load: build the DuckDB warehouse (staging tables -> star schema) and verify it."""
from __future__ import annotations

import logging

import duckdb

from .config import ROOT, Settings

log = logging.getLogger(__name__)

SCHEMA_SQL = ROOT / "sql" / "schema.sql"

# Each check returns a count of offending rows; must be 0.
QUALITY_CHECKS = {
    "fact rows without video": "SELECT count(*) FROM fact_trending f LEFT JOIN dim_video d USING (video_key) WHERE d.video_key IS NULL",
    "fact rows without channel": "SELECT count(*) FROM fact_trending f LEFT JOIN dim_channel d USING (channel_key) WHERE d.channel_key IS NULL",
    "fact rows without date": "SELECT count(*) FROM fact_trending f LEFT JOIN dim_date d ON d.date_key = f.trending_date_key WHERE d.date_key IS NULL",
    "fact rows without category": "SELECT count(*) FROM fact_trending f LEFT JOIN dim_category d ON d.category_key = f.category_key WHERE d.category_key IS NULL",
    "duplicate grain (video, region, day)": "SELECT count(*) FROM (SELECT 1 FROM fact_trending GROUP BY video_key, region_key, trending_date_key HAVING count(*) > 1)",
    "negative views": "SELECT count(*) FROM fact_trending WHERE views < 0",
}


def run(s: Settings) -> dict:
    s.warehouse.parent.mkdir(parents=True, exist_ok=True)
    clean_path = (s.staging_dir / "videos_clean.parquet").as_posix()
    cat_path = (s.staging_dir / "categories.parquet").as_posix()

    con = duckdb.connect(str(s.warehouse))
    try:
        con.execute("DROP TABLE IF EXISTS stg_videos")
        con.execute("DROP TABLE IF EXISTS stg_categories")
        con.execute(f"CREATE TABLE stg_videos AS SELECT * FROM read_parquet('{clean_path}')")
        con.execute(f"CREATE TABLE stg_categories AS SELECT * FROM read_parquet('{cat_path}')")
        con.execute(SCHEMA_SQL.read_text(encoding="utf-8"))

        failures = {}
        for name, sql in QUALITY_CHECKS.items():
            bad = con.execute(sql).fetchone()[0]
            if bad:
                failures[name] = bad
        if failures:
            raise RuntimeError(f"Warehouse quality checks failed: {failures}")

        counts = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                  for t in ["dim_region", "dim_category", "dim_channel", "dim_video", "dim_date", "fact_trending"]}
    finally:
        con.close()
    log.info("Warehouse loaded: %s", counts)
    return counts
