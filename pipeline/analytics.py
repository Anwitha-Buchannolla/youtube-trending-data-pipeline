"""Analytics: run the SQL reports against the warehouse, export CSVs, charts and an HTML report."""
from __future__ import annotations

import base64
import html
import io
import logging

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .config import ROOT, Settings  # noqa: E402

log = logging.getLogger(__name__)
SQL_DIR = ROOT / "sql" / "analytics"

TITLES = {
    "01_top_videos": "Top 20 videos by peak views",
    "02_category_performance": "Category performance",
    "03_top_channels": "Channels that trend most often",
    "04_publish_hour": "Publish hour (UTC) of trending videos",
    "05_days_to_trend": "Days from publication to first trending appearance",
    "06_region_comparison": "Region comparison",
    "07_monthly_trend": "Monthly trending volume",
    "08_weekday_pattern": "Weekday pattern",
}


def run_queries(s: Settings) -> dict[str, pd.DataFrame]:
    con = duckdb.connect(str(s.warehouse), read_only=True)
    try:
        return {p.stem: con.execute(p.read_text(encoding="utf-8")).df()
                for p in sorted(SQL_DIR.glob("*.sql"))}
    finally:
        con.close()


def _png(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def make_charts(r: dict[str, pd.DataFrame]) -> dict[str, str]:
    charts: dict[str, str] = {}

    d = r["02_category_performance"].head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(d["category_name"], d["trending_appearances"], color="#c4302b")
    ax.set_xlabel("Trending appearances")
    ax.set_title("Most frequently trending categories")
    charts["02_category_performance"] = _png(fig)

    d = r["03_top_channels"].head(10).iloc[::-1]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.barh(d["channel_title"], d["trending_videos"], color="#065fd4")
    ax.set_xlabel("Distinct trending videos")
    ax.set_title("Top channels")
    charts["03_top_channels"] = _png(fig)

    d = r["04_publish_hour"]
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(d["publish_hour"], d["videos"], color="#2ba640")
    ax.set_xlabel("Hour published (UTC)")
    ax.set_ylabel("Trending videos")
    ax.set_xticks(range(0, 24, 2))
    charts["04_publish_hour"] = _png(fig)

    d = r["07_monthly_trend"].copy()
    d["period"] = d["year"].astype(str) + "-" + d["month"].astype(str).str.zfill(2)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(d["period"], d["trending_appearances"], marker="o", color="#c4302b")
    ax.set_ylabel("Trending appearances")
    ax.set_title("Trending volume by month")
    ax.tick_params(axis="x", rotation=45)
    charts["07_monthly_trend"] = _png(fig)

    d = r["06_region_comparison"]
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(d["region"], d["avg_engagement_rate"], color="#ff9900")
    ax.set_ylabel("Avg engagement rate")
    ax.set_title("Engagement by region")
    charts["06_region_comparison"] = _png(fig)
    return charts


def build_report(r: dict[str, pd.DataFrame], charts: dict[str, str], stats: dict | None) -> str:
    parts = ["""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>YouTube Trending Videos - Analytics Report</title>
<style>
body{font-family:system-ui,sans-serif;max-width:1000px;margin:2rem auto;padding:0 1rem;color:#222}
h1{color:#c4302b} h2{margin-top:2.2rem;border-bottom:2px solid #eee;padding-bottom:.3rem}
table{border-collapse:collapse;font-size:.85rem;margin:.8rem 0;width:100%}
th,td{border:1px solid #ddd;padding:4px 8px;text-align:left} th{background:#f6f6f6}
img{max-width:100%}
</style></head><body>
<h1>YouTube Trending Videos Data Pipeline and Analytics</h1>"""]
    if stats:
        parts.append("<h2>Pipeline summary</h2><table><tr><th>Region</th><th>Raw rows</th>"
                     "<th>Clean rows</th><th>Rejected</th></tr>")
        for reg, v in stats.items():
            parts.append(f"<tr><td>{html.escape(reg)}</td><td>{v['raw']:,}</td>"
                         f"<td>{v['clean']:,}</td><td>{v['rejected']:,}</td></tr>")
        parts.append("</table>")
    for key, df in r.items():
        parts.append(f"<h2>{html.escape(TITLES.get(key, key))}</h2>")
        if key in charts:
            parts.append(f'<img alt="{html.escape(key)}" src="data:image/png;base64,{charts[key]}">')
        parts.append(df.head(20).to_html(index=False, border=0, escape=True))
    parts.append("</body></html>")
    return "\n".join(parts)


def run(s: Settings, stats: dict | None = None) -> None:
    s.reports_dir.mkdir(parents=True, exist_ok=True)
    results = run_queries(s)
    for name, df in results.items():
        df.to_csv(s.reports_dir / f"{name}.csv", index=False)
    charts = make_charts(results)
    (s.reports_dir / "report.html").write_text(build_report(results, charts, stats), encoding="utf-8")
    log.info("Report written to %s", s.reports_dir / "report.html")
