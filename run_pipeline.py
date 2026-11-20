"""CLI entry point.

Examples
    python run_pipeline.py --sample          # synthetic data in the Kaggle schema (no credentials)
    python run_pipeline.py --download        # pull the real dataset from Kaggle, then run everything
    python run_pipeline.py                   # use files already in data/raw
    python run_pipeline.py --stage transform # run a single stage
"""
from __future__ import annotations

import argparse
import logging
import sys

from pipeline import analytics, extract, load, transform
from pipeline.config import load_settings

STAGES = ["extract", "transform", "load", "analytics"]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="YouTube Trending Videos Data Pipeline and Analytics")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--download", action="store_true", help="download the dataset from Kaggle")
    src.add_argument("--sample", action="store_true", help="generate synthetic data (Kaggle schema)")
    ap.add_argument("--stage", choices=STAGES, help="run only one stage (default: all)")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    log = logging.getLogger("pipeline")
    s = load_settings()
    stages = [args.stage] if args.stage else STAGES
    stats = None

    try:
        if "extract" in stages:
            if args.sample:
                extract.generate_sample(s)
            elif args.download:
                extract.download_from_kaggle(s)
            elif not extract.raw_files_present(s):
                log.error("No raw files in %s. Use --download (needs Kaggle credentials) or --sample.", s.raw_dir)
                return 2
            else:
                log.info("Using existing raw files in %s", s.raw_dir)
        if "transform" in stages:
            stats = transform.run(s)
        if "load" in stages:
            load.run(s)
        if "analytics" in stages:
            analytics.run(s, stats)
    except Exception as exc:  # surface a clean message, non-zero exit for schedulers
        log.error("Pipeline failed: %s", exc)
        return 1
    log.info("Pipeline finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
