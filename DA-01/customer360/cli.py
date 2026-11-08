"""`python -m customer360 <command>` - one entry point for every Python step of the pipeline."""
from __future__ import annotations

import argparse
import json


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="customer360", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    g = sub.add_parser("generate", help="simulate synthetic GA4+Segment+CRM+ads and load into DuckDB")
    g.add_argument("--scale", choices=["small", "medium", "large"], default="medium")
    g.add_argument("--seed", type=int, default=42)
    b = sub.add_parser("generate-bq", help="build synthetic CRM/Segment/ads around the REAL GA4 sample and load into BigQuery")
    b.add_argument("--seed", type=int, default=42)
    b.add_argument("--sample-pct", type=float, default=8.0, help="%% of non-purchasing GA4 users that also become CRM leads")
    sub.add_parser("identity", help="resolve identities (devices <-> CRM customers) and write ml.identity_nodes")
    sub.add_parser("clv", help="fit BG/NBD + Gamma-Gamma, backtest on the holdout, write ml.clv_forecast")
    sub.add_parser("recommend", help="fit response curves and write ml.budget_recommendations")
    sub.add_parser("evaluate", help="accuracy / reconciliation metrics -> reports/metrics.json + docs test results")
    sub.add_parser("report", help="charts + reports/findings.md")
    sub.add_parser("export", help="CSV extracts for Tableau")
    args = ap.parse_args(argv)

    if args.cmd == "generate":
        from .datagen.generate import generate_local

        print(json.dumps(generate_local(args.scale, args.seed), indent=2))
    elif args.cmd == "generate-bq":
        from .datagen.bq_anchor import generate_bigquery

        print(json.dumps(generate_bigquery(seed=args.seed, sample_pct=args.sample_pct), indent=2, default=str))
    elif args.cmd == "identity":
        from .identity import run

        print(json.dumps(run(), indent=2))
    elif args.cmd == "clv":
        from .clv import run

        print(json.dumps(run(), indent=2))
    elif args.cmd == "recommend":
        from .recommend import run

        print(json.dumps(run(), indent=2, default=str))
    elif args.cmd == "evaluate":
        from .evaluate import run

        print(json.dumps(run(), indent=2, default=str))
    elif args.cmd == "report":
        from .report import run

        run()
    elif args.cmd == "export":
        from .export_tableau import run

        run()


if __name__ == "__main__":
    main()
