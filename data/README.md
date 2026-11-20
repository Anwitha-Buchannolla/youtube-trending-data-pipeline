# data/

This folder is populated by the pipeline and is **not committed to Git**
(the raw files are ~0.8 GB and are governed by the dataset's Kaggle terms).

| Path | Created by | Contents |
|------|-----------|----------|
| `raw/` | `extract` | Kaggle CSV + category JSON per region |
| `staging/` | `transform` | `videos_clean.parquet`, `categories.parquet`, `rejected.csv` |
| `warehouse/youtube.duckdb` | `load` | DuckDB star-schema warehouse |

Rebuild everything with:

```bash
python run_pipeline.py --download
```
