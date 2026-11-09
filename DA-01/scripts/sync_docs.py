#!/usr/bin/env python
"""Build docs/06_test_results.md = test strategy (static) + the latest generated reports/test_results.md.   python scripts/sync_docs.py"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
head = """# Test results and test strategy

## Test layers

| Layer | What it proves | Count | Run with |
|---|---|---|---|
| dbt **data tests** (generic) | keys unique / not null, valid foreign keys, accepted values, numeric ranges | 70 | `make dbt-test` |
| dbt **data tests** (singular) | business invariants: credits sum to 1 per order and model; credited revenue = order revenue; no touch after the order or outside the lookback; one person per identifier; one first order per customer; ROI spend reconciles to the ad export | 10 (3 are warn-level data-quality alerts: GA4-CRM match rate, UTM mismatches, "Other" channel share) | `make dbt-test` |
| dbt **unit tests** | e-mail / phone normalisation, net-revenue rules, attribution weights for a 4-touch path with Direct deprioritised | 3 | `make test` |
| **pytest** | identity graph (dedupe, stitching, shared-device guard vs naive), attribution maths, BG/NBD parameter recovery + calibrated holdout + Gamma-Gamma shrinkage, budget optimiser (budget-neutral, bands), simulator integrity + BigQuery loader on a stand-in anchor + Segment replay calls, Streamlit pages | 33 | `make test` |
| **BigQuery SQL validation** | every compiled model and test (BigQuery target, no credentials) parses with the BigQuery dialect | 1 pytest (`scripts/validate_bigquery_sql.py`) | `make bq-validate` |
| **End-to-end** | tiny synthetic world -> full pipeline -> all dbt tests + accuracy thresholds | 1 pytest (`-m integration`), also in CI | `make test` |
| **Evaluation vs ground truth** | accuracy numbers below | every pipeline run | `make evaluate` |

Not executed here: queries against live BigQuery, a live Segment workspace, the Tableau workbook (no credentials / licence in the build environment).

---

"""
body = (ROOT / "reports" / "test_results.md").read_text()
(ROOT / "docs" / "06_test_results.md").write_text(head + body.replace("# Test results and accuracy numbers", "# Latest run: accuracy numbers", 1))
print("wrote docs/06_test_results.md")
