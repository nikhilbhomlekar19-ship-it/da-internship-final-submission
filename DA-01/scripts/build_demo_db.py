#!/usr/bin/env python
"""Copy only the marts + ML tables (a few MB) from the full DuckDB build into app/demo.duckdb so the Streamlit demo runs
without re-running the pipeline (e.g. on Streamlit Community Cloud).   python scripts/build_demo_db.py"""
import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from customer360 import config as cfg  # noqa: E402

out = ROOT / "app" / "demo.duckdb"
out.unlink(missing_ok=True)
src = duckdb.connect(str(cfg.DUCKDB_PATH), read_only=True)
dst = duckdb.connect(str(out))
n = 0
for schema in (cfg.dbt_schema("marts"), cfg.ML_SCHEMA):
    dst.execute(f"create schema if not exists {schema}")
    for (t,) in src.execute("select table_name from information_schema.tables where table_schema = ?", [schema]).fetchall():
        df = src.execute(f"select * from {schema}.{t}").df()
        dst.register("_x", df)
        dst.execute(f"create table {schema}.{t} as select * from _x")
        dst.unregister("_x")
        n += 1
dst.close()
print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB, {n} tables)")
