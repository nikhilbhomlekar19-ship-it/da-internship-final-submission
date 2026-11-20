# ETL and Azure Data Factory

## Design

```
pl_master_daily  (trigger tr_daily_0200, 02:00 India Standard Time)
 ├─ Extract to staging     = pl_extract_to_staging
 │    Lookup etl.source_table_config  →  ForEach (4 in parallel)
 │      FULL:        Copy  (preCopyScript TRUNCATE TABLE stg.X)
 │      INCREMENTAL: Lookup old watermark → Lookup new watermark → Copy delta (upsert on key_columns) → usp_update_watermark
 ├─ Transform and test     = pl_transform_and_test  →  EXEC etl.usp_run_all @extract_mode='ADF'   (dims → facts → 52 DQ checks)
 ├─ Refresh Power BI dataset (optional)  POST …/datasets/{id}/refreshes  with the factory's managed identity
 └─ Alert on failure (optional)          POST to a Teams/Logic App webhook
```
* **Metadata-driven:** adding a table = one row in `etl.source_table_config` (generated from `tools/model_spec.py`, so staging DDL, config and the local extract proc can never disagree).
* **Incremental tables** (4): SalesOrderHeader/Detail, PurchaseOrderHeader/Detail on `ModifiedDate`. AdventureWorks never changes, so after the first run the delta is empty - to *demo* incremental, `UPDATE Sales.SalesOrderHeader SET ModifiedDate = GETDATE() WHERE SalesOrderID = 43659` in the source and re-run: one header row is upserted.
* **Idempotent & atomic:** facts are rebuilt in a transaction; the DQ gate runs last and fails the pipeline on any ERROR check.
* **Retry:** copy/lookup activities retry twice (30 s), the transform once.

## Deploy (≈45 min first time)

1. **Resources:** Resource group → Data Factory, Key Vault, Azure SQL Database `AW_BI` (free offer is enough). Run `sql/01…10` against it (skip `00`, `02b`, `11`).
2. **Self-hosted IR** (only if the source SQL Server is not reachable from Azure): ADF → Manage → Integration runtimes → *Self-hosted* → install on the machine that can see the source. Name it `ir-selfhosted` (or pass `-SelfHostedIrName`).
3. **Secrets:** Key Vault secrets `sql-source-password`, `sql-dw-password`; give the factory's managed identity *Key Vault Secrets User*. Create least-privilege SQL users: `etl_reader` (db_datareader on the source), `etl_loader` (db_owner on `AW_BI`, or: EXECUTE on `etl`, INSERT/DELETE/ALTER on `stg`).
4. `pwsh scripts/deploy_adf.ps1 -ResourceGroup … -FactoryName … -KeyVaultName … -SourceServer … -SourceUser etl_reader -DwServer <srv>.database.windows.net -DwUser etl_loader`
5. ADF Studio → *Monitor* → pipeline `pl_master_daily` → **Add trigger → Trigger now**. Optional parameters: `pbiWorkspaceId`, `pbiDatasetId`, `alertWebhookUrl`. For the Power BI call add the factory's managed identity to a security group allowed under *Tenant settings → Developer settings → Service principals can use Fabric APIs* and as **Member** of the workspace.
6. Start the schedule: re-run the script with `-StartTrigger` (or ADF → Manage → Triggers → Start).

> The self-hosted IR + SQL Server source variant uses linked-service type `SqlServer`; if your source is an Azure SQL DB/Managed Instance, change `ls_sql_source.type` to `AzureSqlDatabase`/`SqlServer` and remove `connectVia`.

## No Azure? Scheduled SQL jobs

`sql/11_sql_agent_job.sql` creates `AW_BI - nightly ETL` (SQL Server Agent, daily 02:00). It calls `etl.usp_run_all @extract_mode='LOCAL'`, which first runs `etl.usp_extract_local` (TRUNCATE + INSERT…SELECT from `src.*` synonyms that point to the AdventureWorks database on the same instance). SQL Express (no Agent): create a Windows Task Scheduler task running `sqlcmd -S .\SQLEXPRESS -E -d AW_BI -b -Q "EXEC etl.usp_run_all"`.

## Monitoring queries

```sql
SELECT TOP 10 * FROM etl.run_log ORDER BY run_id DESC;                         -- run history
SELECT step_name, rows_affected, DATEDIFF(ms, started_at, finished_at) AS ms FROM etl.step_log WHERE run_id = (SELECT MAX(run_id) FROM etl.run_log) ORDER BY step_id;
SELECT * FROM etl.dq_result WHERE status = 'FAIL' ORDER BY result_id DESC;     -- failed checks
```
