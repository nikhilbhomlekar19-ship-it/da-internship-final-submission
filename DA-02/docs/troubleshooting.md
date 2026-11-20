# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `Could not find stored procedure 'etl.usp_extract_local'` / `Invalid object name 'src.…'` | Synonyms missing | Run `sql/02b_source_synonyms.sql` with `-v SourceDb=<your AdventureWorks DB name>` |
| `RESTORE … logical file 'AdventureWorks2022' not found` | Different logical names in your .bak | `RESTORE FILELISTONLY FROM DISK='…'` and use those names in the `MOVE` clauses |
| `Msg 51000 Data-quality gate failed` | An ERROR check failed | `SELECT * FROM etl.dq_result WHERE status='FAIL' ORDER BY result_id DESC` - fix the cause; WARN rows never fail the run |
| Violation of PRIMARY KEY on a fact | Duplicate grain (e.g. overlapping cost-history ranges after you changed data) | Run the grain check in `etl.dq_check`; inspect the join in `sql/transforms/<table>.sql` |
| `TRUNCATE … cannot be truncated because it is being referenced by a FOREIGN KEY` | A fact FK points *to* the table you truncate | Only facts are truncated; never add FKs that reference a fact |
| Azure SQL: `USE statement is not supported` | You ran a script with `USE` | The scripts use none - connect with `-d AW_BI` instead; skip `00_create_database.sql`, `02b`, `11` |
| `GO` is not recognised | Script run from a tool that is not sqlcmd/SSMS/ADS | Use sqlcmd, SSMS or Azure Data Studio |
| ADF Copy fails on `upsert` keys | `key_columns` has spaces or the stg table has no PK | Keep `key_columns` comma-separated without spaces; `02_staging.sql` creates the PKs |
| ADF: *Self-hosted IR is offline* | IR service stopped | Restart "Integration Runtime" Windows service; check outbound 443 |
| Power BI Desktop: PBIP will not open / "unsupported property" | Schema version newer than your Desktop, or a preview switch is off | Update Desktop; enable the PBIP/TMDL/PBIR preview features; otherwise build from [report-spec.md](report-spec.md) (model + measures are independent of the report) |
| Visuals show "Can't display the visual" for one field | A column renamed in M but not in the model | Re-run `python tools/build_repo.py`; check `python tools/validate_model.py` |
| `Region Manager` sees everything | You are testing as workspace admin/member | Use *View as* / *Test as role*, or sign in as a Viewer |
| `Region Manager` sees nothing | UPN not in `sec.user_territory_map` (deny by default) or case/e-mail alias mismatch | Insert the exact UPN, refresh the dataset |
| Refresh fails "Cannot connect" in the Service | Parameter or gateway mismatch | Server/database text must match exactly between the gateway data source and the parameters |
| YoY looks wrong (−50%) | Partial calendar year selected | Use fiscal year or month granularity |
| Numbers differ from the baseline by cents | Fixed-decimal rounding (Power BI stores 4 decimals) | The DAX tests allow ±0.50 on totals |
