# Implementation guide

Follows the seven steps of the brief. Budget **half a day** for the local path if nothing goes wrong, plus 1-2 hours for Azure (ADF) and publishing.

## 0. Prerequisites

| Need | Notes |
|---|---|
| SQL Server 2019/2022 Developer or Express, **or** Docker (`docker compose up -d`) | Express works (no SQL Agent: use ADF or run `etl.usp_run_all` from Task Scheduler + `sqlcmd`) |
| `sqlcmd` | Windows: bundled with SSMS/ADS or `winget install Microsoft.Sqlcmd`; Linux/macOS: `mssql-tools18` |
| Power BI Desktop (Windows, current release) | *File → Options → Preview features*: enable **Power BI Project (.pbip)**, **TMDL** and **PBIR** if they are not already on |
| Python 3.10+ (optional) | only for `pytest`, generators and validators (`pip install -r requirements.txt`) |
| Azure subscription + Power BI Pro/PPU/Fabric trial (optional) | needed for ADF, publishing, RLS in the Service |

## 1. Dataset

```bash
./scripts/download_adventureworks.sh          # AdventureWorks2022.bak (~200 MB) + CSVs for the Python tests
```
Restore the `.bak` as database **AdventureWorks2022** (the scripts do this; manual route: SSMS → Databases → Restore Database → Device). It is Microsoft's MIT-licensed sample: 31,465 sales orders (121,317 lines, 2022-05-30 → 2025-06-29), 4,012 purchase orders, 290 employees, 104 vendors.

## 2. Star schema + Power Query

```bash
pwsh scripts/setup_local.ps1 -Server localhost            # or scripts/setup_local.sh with Docker (see README)
```
It runs, in order: `00_create_database` → `01_framework` → `02_staging` → `03_dw_schema` → `04_security` → `05_etl_dim_date` → `06_etl_dimensions` → `07_etl_facts` → `08_etl_orchestration` → `09_dq_checks` → `10_rpt_views` → `02b_source_synonyms` → `EXEC etl.usp_run_all` → tests.

**Expected result** (from the DuckDB reference run - your SQL Server counts must match):

| Table | Rows | | Table | Rows |
|---|---:|---|---|---:|
| fact_sales_line | 121,317 | | dim_product | 505 (504 + unknown) |
| fact_purchase_line | 8,845 | | dim_customer | 19,821 |
| fact_sales_quota | 489 | | dim_employee | 291 |
| fact_inventory | 1,069 | | dim_vendor | 105 |
| fact_headcount_monthly | 57,395 | | dim_territory | 11 |
| fact_payroll_monthly | 5,203 | | dim_date | one row per day, 2006-01-01 → 2025-10-31 |

Check: `SELECT TOP 5 * FROM etl.run_log ORDER BY run_id DESC;` (status SUCCEEDED) and `SELECT * FROM etl.dq_result ORDER BY result_id DESC;` (all PASS, one WARN row shows **64** sales lines costed with the current standard cost - expected, see assumptions).

**Power Query.** Open `powerbi/EnterpriseBI.pbip` in Power BI Desktop. Parameters `p_SqlServer` (default `localhost`) and `p_Database` (`AW_BI`) drive every query (*Transform data → Manage parameters*). Each table query = `Sql.Database` → navigate `rpt.vw_*` → rename to business names → trim text → replace nulls with "N/A" → set types. The same M is in `powerbi/power-query/*.pq` if you prefer to paste into *Advanced Editor*. Click **Refresh**; on the credentials prompt choose *Windows* (local) or *Database* (SQL login). Details of the shaping steps: `docs/data-model.md`.

## 3. Data movement

*No Azure:* in SSMS run `sql/11_sql_agent_job.sql` (SQL Server only). Job `AW_BI - nightly ETL` runs `etl.usp_run_all 'LOCAL'` at 02:00. Test: right-click the job → *Start Job at Step*.

*Azure:* see [etl-and-adf.md](etl-and-adf.md) (Key Vault secrets → self-hosted IR → `scripts/deploy_adf.ps1` → *Trigger now* → Monitor).

## 4. DAX measures

Already in the model (`_Measures` table, display folders Sales / Time Intelligence / Quota / Finance / Supply Chain / HR / Security). Reference with the formulas: [dax-reference.md](dax-reference.md). To add them by hand: Desktop → *DAX query view* → paste `powerbi/dax/measures_dax_query_view.dax` → *Update model: add new measures*.
Verify any measure in DAX query view, e.g. `EVALUATE ROW("FY25 YoY", CALCULATE([Net Sales YoY Growth %], 'Date'[Fiscal Year] = 2025))` → expect **0.2858**. The full list of 55 expected values is `tests/dax/test_cases.json`.

## 5. Executive pages + drill-through

Pages (8): Executive Overview · Sales Performance · Finance · Supply Chain · HR · *Product Detail* · *Customer Detail* · *Vendor Detail* (drill-through: right-click a product/customer/vendor in a table → *Drill through*). Page-by-page contents: [report-spec.md](report-spec.md). Import `powerbi/theme/EnterpriseBI-theme.json` (*View → Themes → Browse*). If the generated project fails to open, build from the spec (fallback section in that doc) - the model and measures are independent of the report.

## 6. Row-level security

Roles are in the model: **Region Manager** (dynamic) and **Global Executive**. Edit the mapping: `sec.user_territory_map` (replace the `@contoso.com` placeholders with real UPNs), re-run `EXEC etl.usp_run_all` (or just refresh the dataset - the map is a view). Test in Desktop: *Modeling → View as → Region Manager + Other user: `northwest.manager@contoso.com`* → Territories Visible = 1. Details and the 6 automated RLS tests: [security-rls.md](security-rls.md).

## 7. Publish, refresh, user guide

Follow [publish-and-refresh.md](publish-and-refresh.md): publish → set credentials/gateway → daily refresh 03:00 IST → add users to roles → create the app. One-page user guide: [user-guide.md](user-guide.md) / `user-guide.pdf`.

## 8. Collect your evidence (for the "test results" and presentation)

```bash
SQLPASSWORD=... ./scripts/run_sql_tests.sh              # or the PowerShell setup script (it stores the output)
pwsh tests/dax/run_dax_tests.ps1 -WorkspaceId <id> -DatasetId <id>      # 55 DAX tests incl. 6 RLS impersonation tests
pytest -q tests                                          # DuckDB transform tests + static checks
```
Fill in the timings in [test-plan-and-results.md](test-plan-and-results.md) (Power BI *Performance analyzer* for page load, `tests/sql/04_performance_report.sql` for ETL).
