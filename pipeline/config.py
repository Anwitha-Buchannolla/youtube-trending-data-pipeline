"""Load config.yaml and resolve paths relative to the project root."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    dataset: str
    regions: list[str]
    raw_dir: Path
    staging_dir: Path
    warehouse: Path
    reports_dir: Path
    min_views: int
    max_title_length: int


def load_settings(path: Path | None = None) -> Settings:
    cfg = yaml.safe_load((path or ROOT / "config.yaml").read_text(encoding="utf-8"))
    p = cfg["paths"]
    return Settings(
        dataset=cfg["kaggle"]["dataset"],
        regions=list(cfg["kaggle"]["regions"]),
        raw_dir=ROOT / p["raw_dir"],
        staging_dir=ROOT / p["staging_dir"],
        warehouse=ROOT / p["warehouse"],
        reports_dir=ROOT / p["reports_dir"],
        min_views=int(cfg["quality"]["min_views"]),
        max_title_length=int(cfg["quality"]["max_title_length"]),
    )
