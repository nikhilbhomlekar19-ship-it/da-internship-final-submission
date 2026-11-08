"""Generate the synthetic sources and load them into the warehouse.

Local demo (DuckDB):   python -m customer360 generate --scale medium
BigQuery (real GA4):   python -m customer360 generate-bq        (see datagen/bq_anchor.py)
"""
from __future__ import annotations

import json

from .. import config as cfg
from ..warehouse import Warehouse
from .simulate import simulate


def generate_local(scale: str = "medium", seed: int = 42) -> dict:
    if cfg.TARGET != "duckdb":
        raise SystemExit("`generate` builds a fully synthetic world and only loads DuckDB. For BigQuery use `generate-bq`.")
    res = simulate(scale=scale, seed=seed)
    with Warehouse("duckdb") as wh:
        for name, df in res.tables.items():
            wh.write_df(df, cfg.RAW_SCHEMA, name)
        n = wh.load_ga4_jsonl(str(res.ga4_jsonl), cfg.RAW_SCHEMA)
        for name, df in res.truth.items():
            wh.write_df(df, cfg.TRUTH_SCHEMA, name)
    res.summary["ga4_events_loaded"] = n
    out = cfg.DATA_DIR / "generation_summary.json"
    out.write_text(json.dumps(res.summary, indent=2))
    return res.summary
