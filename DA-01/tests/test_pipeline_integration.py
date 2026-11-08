"""End-to-end: tiny synthetic world -> dbt (seed, staging, identity edges) -> python identity + CLV -> dbt marts + 80 data tests -> evaluation."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.integration
def test_small_pipeline_runs_green(tmp_path):
    env = {**os.environ, "C360_TARGET": "duckdb", "C360_DUCKDB_PATH": str(tmp_path / "t.duckdb"), "C360_DATA_DIR": str(tmp_path / "data"),
           "C360_REPORTS_DIR": str(tmp_path / "reports"), "C360_EXPORT_DIR": str(tmp_path / "exports"), "DBT_TARGET_PATH": str(tmp_path / "target"),
           "DBT_LOG_PATH": str(tmp_path / "logs"), "PYTHONPATH": str(ROOT)}
    r = subprocess.run([sys.executable, "-m", "customer360.pipeline", "--scale", "small"], env=env, cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]
    m = json.loads((tmp_path / "reports" / "metrics.json").read_text())
    assert m["dbt"]["tests"].get("fail", 0) == 0 and m["dbt"]["tests"].get("error", 0) == 0
    assert m["dbt"]["tests"]["pass"] >= 70
    assert m["attribution_sql_vs_python_parity"]["max_abs_revenue_diff_usd"] < 0.05
    assert m["identity_resolution"]["guarded"]["precision"] > 0.9
    assert m["identity_resolution"]["channel_classification_accuracy"] == 1.0
    assert m["reconciliation"]["online_order_match_rate"] > 0.85
