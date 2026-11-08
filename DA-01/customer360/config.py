"""Central configuration. Everything can be overridden with environment variables (see .env.example)."""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


DATA_DIR = Path(_env("C360_DATA_DIR", str(ROOT / "data")))
REPORTS_DIR = Path(_env("C360_REPORTS_DIR", str(ROOT / "reports")))
EXPORT_DIR = Path(_env("C360_EXPORT_DIR", str(ROOT / "exports" / "tableau")))
DBT_DIR = ROOT / "dbt_project"
DBT_TARGET_DIR = Path(_env("DBT_TARGET_PATH", str(DBT_DIR / "target")))


TARGET = _env("C360_TARGET", "duckdb").lower()  # duckdb | bigquery
DUCKDB_PATH = Path(_env("C360_DUCKDB_PATH", str(DATA_DIR / "c360.duckdb")))
if not DUCKDB_PATH.is_absolute():
    DUCKDB_PATH = ROOT / DUCKDB_PATH
GCP_PROJECT = _env("GCP_PROJECT", "")
BQ_LOCATION = _env("BQ_LOCATION", "US")

# In BigQuery these are datasets; in DuckDB they are schemas. Same names on both targets.
RAW_SCHEMA = _env("C360_RAW_SCHEMA", "c360_raw")        # synthetic CRM / Segment / ads (+ synthetic GA4 locally)
ML_SCHEMA = _env("C360_ML_SCHEMA", "c360_ml")           # outputs of Python steps (identity graph, CLV, budget plan)
TRUTH_SCHEMA = _env("C360_TRUTH_SCHEMA", "c360_truth")  # simulator ground truth (local demo only)
DBT_SCHEMA = _env("C360_DBT_SCHEMA", "c360")            # dbt base schema -> c360_staging / _intermediate / _marts


def dbt_schema(layer: str) -> str:
    """Schema where dbt materialises a layer: staging | intermediate | marts."""
    return f"{DBT_SCHEMA}_{layer}"


# Tracking window = the date range of the public GA4 sample dataset.
START_DATE = date(2020, 11, 1)
END_DATE = date(2021, 1, 31)
HISTORY_START = date(2019, 11, 1)  # CRM order history starts 12 months before the GA4 window
AS_OF_DATE = END_DATE

# Business assumptions (also dbt vars - keep both in sync)
GROSS_MARGIN = 0.45
LOOKBACK_DAYS = 30
