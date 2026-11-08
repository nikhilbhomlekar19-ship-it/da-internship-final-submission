"""One-command orchestrator:  python -m customer360.pipeline [--scale medium] [--target duckdb|bigquery] [--skip-generate]

  generate -> dbt seed -> dbt staging+identity edges -> python identity -> python clv -> dbt marts+tests
           -> python recommend -> python evaluate -> python report -> python export
Writes reports/timings.json and keeps each dbt run_results.json (used by the evaluation).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time

from . import config as cfg


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", default="medium", choices=["small", "medium", "large"])
    ap.add_argument("--target", default=cfg.TARGET, choices=["duckdb", "bigquery"])
    ap.add_argument("--skip-generate", action="store_true", help="reuse data already in the warehouse (always the case for the real GA4 sample)")
    args = ap.parse_args(argv)

    env = {**os.environ, "C360_TARGET": args.target, "C360_DUCKDB_PATH": str(cfg.DUCKDB_PATH), "PYTHONPATH": str(cfg.ROOT)}
    py = [sys.executable, "-m", "customer360"]
    dbt = ["dbt", "{cmd}", "--project-dir", str(cfg.DBT_DIR), "--profiles-dir", str(cfg.DBT_DIR), "--target", args.target]
    d = lambda cmd, *extra: [a.replace("{cmd}", cmd) for a in dbt] + list(extra)
    cfg.REPORTS_DIR.mkdir(exist_ok=True)
    rr = cfg.DBT_TARGET_DIR / "run_results.json"

    steps = []
    if not args.skip_generate:
        steps.append(("generate", py + (["generate", "--scale", args.scale] if args.target == "duckdb" else ["generate-bq"]), None))
    steps += [
        ("dbt_seed", d("seed"), None),
        ("dbt_stage1_staging_and_identity_edges", d("build", "--select", "+int_identity_edges"), "dbt_stage1_run_results.json"),
        ("python_identity_resolution", py + ["identity"], None),
        ("python_clv_bgnbd", py + ["clv"], None),
        ("dbt_stage2_marts_and_tests", d("build", "--exclude", "+int_identity_edges"), "dbt_stage2_run_results.json"),
        ("python_budget_recommendation", py + ["recommend"], None),
        ("python_evaluate", py + ["evaluate"], None),
        ("python_report", py + ["report"], None),
        ("python_export_tableau", py + ["export"], None),
    ]
    timings = {}
    for name, cmd, keep in steps:
        t0 = time.time()
        print(f"\n=== {name} ===", flush=True)
        r = subprocess.run(cmd, env=env, cwd=cfg.ROOT)
        timings[name] = round(time.time() - t0, 1)
        if keep and rr.exists():
            shutil.copy(rr, cfg.REPORTS_DIR / keep)
        if r.returncode != 0:
            (cfg.REPORTS_DIR / "timings.json").write_text(json.dumps(timings, indent=2))
            raise SystemExit(f"step {name} failed (exit {r.returncode})")
        if name == "python_budget_recommendation":
            (cfg.REPORTS_DIR / "timings.json").write_text(json.dumps(timings, indent=2))  # evaluate embeds timings so far
    timings["total"] = round(sum(timings.values()), 1)
    (cfg.REPORTS_DIR / "timings.json").write_text(json.dumps(timings, indent=2))
    mp = cfg.REPORTS_DIR / "metrics.json"
    if mp.exists():  # evaluate ran before the last steps finished: refresh timings in the metrics + test report
        from .evaluate import write_test_results

        m = json.loads(mp.read_text())
        m["pipeline_timings_seconds"] = timings
        mp.write_text(json.dumps(m, indent=2, default=str))
        write_test_results(m)
    print(f"\nDone in {timings['total']} s")


if __name__ == "__main__":
    main()
