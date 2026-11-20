# Implementation guide

This guide takes you from a fresh clone to (A) a working local demo, (B) the same pipeline on **BigQuery with the real GA4 sample**,
(C) a real **Segment** source, and (D) **Tableau** dashboards.  Everything is driven from the repository root.

> Windows: use WSL2 (recommended) or run the commands from the `Makefile` by hand.  All paths below are relative to the repo root.

## 0. Prerequisites

| Need | For | Notes |
|---|---|---|
| Python 3.10+ , git | everything | `python --version` |
| `make` | convenience | optional; every target is just a command listed in the Makefile |
| Google Cloud project + `gcloud` CLI | Part B | free tier is enough (see cost notes) |
| Segment workspace (free plan) | Part C | optional - the project works on synthetic Segment tables |
| Tableau Desktop **or** Tableau Public | Part D | Public cannot connect to BigQuery: use the CSV extracts |

## A. Local demo (DuckDB, no cloud)

```bash
git clone <your-repo-url> customer360-attribution && cd customer360-attribution
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
make demo
```

What `make demo` does (each step also exists as its own `make` target, see `make help`):

| # | Step | Produces |
|---|---|---|
| 1 | `generate` | Simulates 6,000 people -> GA4-shaped events, Segment events, CRM, ad spend + ground truth, loads DuckDB (`data/c360.duckdb`) |
| 2 | `dbt seed` + `dbt build +int_identity_edges` | staging models, identity **evidence edges**, and their tests |
| 3 | `python -m customer360 identity` | `c360_ml.identity_nodes` (who is who) |
| 4 | `python -m customer360 clv` | `c360_ml.clv_forecast`, back-test in `reports/clv_backtest.json` |
| 5 | `dbt build` (everything else) | sessions, orders, profile, RFM, attribution, ROI marts + ~70 tests |
| 6 | `python -m customer360 recommend` | `c360_ml.budget_recommendations`, `c360_ml.response_curves` |
| 7 | `evaluate` / `report` / `export` | `reports/metrics.json`, `reports/test_results.md`, `reports/findings.md`, `reports/figures/*.png`, `exports/tableau/*.csv` |

Why the order matters: dbt cannot build the marts before the Python steps have written `identity_nodes` and `clv_forecast`
(they are dbt **sources**).  If you run stage 2 first you will see `Table c360_ml.identity_nodes does not exist`.

Check it worked:

```bash
python -m json.tool reports/metrics.json | head -40     # accuracy numbers
streamlit run app/streamlit_app.py                      # click through the 6 pages
make test                                               # pytest + dbt unit tests (about 1 minute)
make docs                                               # dbt lineage graph on http://localhost:8080
```

Scale knobs: `make demo SCALE=small` (800 people, roughly 20-30 s), `SCALE=large` (20,000 people).  Everything is seeded - the same seed gives identical results.

## B. BigQuery with the real GA4 sample

### B1. One-time cloud setup
```bash
cp .env.example .env            # edit GCP_PROJECT; keep BQ_LOCATION=US
set -a && source .env && set +a
gcloud auth application-default login          # or put a service-account key path in GOOGLE_APPLICATION_CREDENTIALS
./scripts/setup_bigquery.sh                     # creates c360_raw / c360_ml / c360_staging / c360_intermediate / c360_marts (US), runs a sanity query
```
The public sample (`bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`, 2020-11-01 .. 2021-01-31) lives in the **US multi-region**.
BigQuery cannot join across locations, so your datasets **must** be in `US` (the most common first-run error is
`Not found: Dataset ... was not found in location EU`).

### B2. Build the synthetic sources around the real users
```bash
make bq-load          # = C360_TARGET=bigquery python -m customer360 generate-bq
```
This runs three queries against the public sample (purchases, a user sample, daily session counts per source/medium/campaign) and then
creates in `c360_raw`:

| Table | Built from |
|---|---|
| `crm_customers`, `crm_orders` | one CRM customer per GA4 purchaser (+ ~8 % of other users as leads); **CRM orders reuse the real GA4 `transaction_id`s and revenue**; BG/NBD order history before the window |
| `segment_identifies`, `segment_tracks`, `segment_order_completed` | `identify()` calls carrying the GA client id (= `user_pseudo_id`), a mobile app with campaign context, app orders |
| `ads_spend_daily` | daily spend / clicks for every paid campaign found in the real sessions (+ the app campaigns); budget scaled to a blended ROAS of ~3.4 |

The GA4 events themselves are **not copied**: dbt reads the public tables directly.
Tune with `python -m customer360 generate-bq --sample-pct 10 --seed 7`.

### B3. Run the pipeline
```bash
make bq-demo          # = python -m customer360.pipeline --target bigquery --skip-generate
```
Same steps and order as the local run, executed by dbt-bigquery and the BigQuery client.  The ground-truth evaluation is skipped automatically
(real GA4 data has no ground truth); reconciliation, parity, CLV back-test and dbt-test counts still run.

### B4. Look at the result
```sql
-- BigQuery console
select channel_group, model, round(revenue_share, 3) as share
from `YOUR_PROJECT.c360_marts.mart_attribution_by_channel` order by model, share desc;
```
Point Tableau at `c360_marts` and `c360_ml` ([05_tableau_guide.md](05_tableau_guide.md)) and the Streamlit app at BigQuery with `C360_TARGET=bigquery streamlit run app/streamlit_app.py`.

### B5. Cost and safety notes
* Free tier: 1 TB of query processing per month.  A full run scans the GA4 sample a few times (expect a few GB in total - check with `bq query --dry_run` or the job history), the synthetic tables are small.
* Add a guard in `dbt_project/profiles.yml` (`maximum_bytes_billed: 10000000000`) once you move to a bigger export.
* The service account only needs `BigQuery Data Editor` + `BigQuery Job User`.  Never commit keys (`.gitignore` already excludes `*.json.key`, `service-account*.json`, `.env`).

### B6. Using your own GA4 export instead of the sample
```bash
dbt build ... --vars '{use_public_ga4: false, start_date: "2024-01-01", end_date: "2024-03-31", as_of_date: "2024-03-31"}'
```
and point the `ga4` source at your export dataset (`dbt_project/models/staging/_sources.yml`: `database`, `schema`, `identifier: events_*`).
For a full-size export make `stg_ga4__events` incremental (partition by `event_date`) - the comment in the model shows where.

## C. Segment (real source -> BigQuery)

1. In Segment create a **Source** (JavaScript for the site, iOS/Android for the app) and copy its **write key**.
2. Implement the tracking plan in [`segment/tracking_plan.yaml`](../segment/tracking_plan.yaml). The one rule that makes identity work:
   send the GA4 client id with `identify()` - see [`segment/snippets/analytics_js_identify.js`](../segment/snippets/analytics_js_identify.js).
3. Don't have an app yet?  Replay the synthetic events into your source:
   ```bash
   python -m customer360.segment_replay --limit 50 --dry-run            # inspect the calls
   SEGMENT_WRITE_KEY=xxxx python -m customer360.segment_replay --limit 500
   ```
4. In Segment add **BigQuery** as a *Warehouse destination* of that source.  Segment creates a dataset with `identifies`, `tracks`, `pages`, ... and one table per event (e.g. `order_completed`).
5. Point dbt at it (no SQL changes needed):
   ```bash
   dbt build ... --vars '{segment_schema: "your_segment_dataset", segment_identifies_table: "identifies", segment_tracks_table: "tracks", segment_orders_table: "order_completed"}'
   ```
   Segment's real column names (`id`, `anonymous_id`, `user_id`, `timestamp`, `event`, `context_campaign_*`, `email`, trait `ga_client_id`) are what the staging models read.

## D. Tableau
Follow [05_tableau_guide.md](05_tableau_guide.md): connect to BigQuery (or load `exports/tableau/*.csv`), create two parameters, six calculated fields, five dashboards (about 2 hours).

## E. Working as a team in Git

* Branch per piece of work (`feat/identity-guard`, `fix/utm-normalisation`), small commits with an imperative subject: `feat(dbt): add RFM segments`, `test(identity): shared-device guard`, `docs: methodology`.
* A pull request is ready when `make test-fast` is green and, for model changes, `make demo` still ends with all dbt tests passing.
* CI (`.github/workflows/da-01.yml` at the repository root, run from `DA-01/`) runs the unit tests, the offline BigQuery SQL validation and the end-to-end pipeline on a tiny dataset.

## F. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `Table c360_ml.identity_nodes does not exist` | dbt stage 2 ran before the Python steps. Use `make demo` / `make bq-demo`, or run `make dbt-stage1 identity clv dbt-stage2` in that order |
| `IO Error: Could not set lock on file ... c360.duckdb` | another process holds the DuckDB file (Streamlit, a notebook, a second dbt run). Close it - DuckDB allows one writer |
| `Not found: Dataset ... in location EU` | datasets must be in `US` (public sample location). Recreate with `bq --location=US mk ...` and set `BQ_LOCATION=US` |
| `Access Denied: ... bigquery.jobs.create` | grant the account `BigQuery Job User` on your project |
| `Failed to authenticate with supplied credentials` | run `gcloud auth application-default login` or set `GOOGLE_APPLICATION_CREDENTIALS`; for service accounts also `DBT_BQ_METHOD=service-account` |
| dbt: `Could not find profile named 'customer360'` | run dbt from the repo root with `--project-dir dbt_project --profiles-dir dbt_project` (the Makefile does) |
| dbt error mentioning `protobuf` | `pip install "protobuf>=6,<7"` (dbt-common pins protobuf 6.x) |
| `Parser Error` in a `lambda` expression on DuckDB | DuckDB < 1.3 does not know the `lambda x: ...` syntax - `pip install -U duckdb` |
| `generate` complains about target | `generate` is DuckDB-only; for BigQuery use `generate-bq` |
| ROI rows with `spend` but 0 revenue | UTM naming mismatch between ads and sessions: `dbt test` warns via `assert_all_paid_campaigns_have_sessions`; fix the campaign name or add a mapping in the staging model |
| Many sessions classified `Other` | extend the `c360_channel_group` macro (warned by `assert_other_channel_share_is_small`) |

## G. Extending the project

* **New channel**: add a `when` branch to `c360_channel_group` (macro) + its Python twin `classify_channel` + a row in `seeds/channel_catalog.csv`.
* **New attribution model** (e.g. position-based): add a `credit_position_based` column in `int_attribution__paths.sql`, add the name to the `models` list in `fct_attribution_credits.sql`, `mart_attribution_comparison.sql` and `customer360/attribution.py`; the existing tests check that credits sum to 1.
* **Change the lookback / half-life / margin / Direct policy**: they are dbt vars (`attribution_lookback_days`, `time_decay_half_life_days`, `gross_margin_pct`, `direct_policy`) - override with `--vars` or edit `dbt_project.yml`.
* **Real CRM / ads data**: replace the `crm` and `ads` sources in `_sources.yml` (Fivetran/Airbyte schemas) and keep the staging models' output columns unchanged.
