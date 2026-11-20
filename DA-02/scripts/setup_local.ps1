<# Windows one-shot build against a local SQL Server (Developer/Express) using Windows authentication.
   Prereqs: SQL Server + sqlcmd (https://learn.microsoft.com/sql/tools/sqlcmd), AdventureWorks2022.bak downloaded (see docs).
   pwsh scripts/setup_local.ps1 -Server localhost -BackupPath C:\data\AdventureWorks2022.bak #>
param([string]$Server = "localhost", [string]$SourceDb = "AdventureWorks2022", [string]$BackupPath = "$PSScriptRoot\..\data\AdventureWorks2022.bak")
$ErrorActionPreference = 'Stop'; Set-Location "$PSScriptRoot\.."
function Sql([string]$file, [string]$db = "", [string]$vars = "") {
  Write-Host ">> $file"; $a = @("-S", $Server, "-E", "-C", "-b", "-i", $file); if ($db) { $a += @("-d", $db) }; if ($vars) { $a += @("-v", $vars) }
  & sqlcmd @a; if ($LASTEXITCODE) { throw "sqlcmd failed on $file" } }
if (-not (Test-Path $BackupPath)) { Write-Host "Downloading AdventureWorks2022.bak ..."; New-Item -ItemType Directory -Force -Path (Split-Path $BackupPath) | Out-Null
  Invoke-WebRequest "https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks/AdventureWorks2022.bak" -OutFile $BackupPath }
$exists = & sqlcmd -S $Server -E -C -h -1 -Q "SET NOCOUNT ON; SELECT COUNT(*) FROM sys.databases WHERE name = N'$SourceDb'"
if ([int]($exists | Select-Object -First 1) -eq 0) {
  $bak = (Resolve-Path $BackupPath).Path
  $dp = (& sqlcmd -S $Server -E -C -h -1 -W -Q "SET NOCOUNT ON; SELECT CONVERT(nvarchar(260), SERVERPROPERTY('InstanceDefaultDataPath'))" | Select-Object -First 1).Trim()
  $lp = (& sqlcmd -S $Server -E -C -h -1 -W -Q "SET NOCOUNT ON; SELECT CONVERT(nvarchar(260), SERVERPROPERTY('InstanceDefaultLogPath'))" | Select-Object -First 1).Trim()
  & sqlcmd -S $Server -E -C -b -Q "RESTORE DATABASE [$SourceDb] FROM DISK = N'$bak' WITH MOVE 'AdventureWorks2022' TO N'$dp$SourceDb.mdf', MOVE 'AdventureWorks2022_log' TO N'$lp${SourceDb}_log.ldf', REPLACE"
  if ($LASTEXITCODE) { Write-Warning "Automatic RESTORE failed; restore the .bak in SSMS (Databases > Restore Database) as '$SourceDb', then re-run."; throw "restore failed" } }
Sql sql\00_create_database.sql
foreach ($f in "01_framework","02_staging","03_dw_schema","04_security","05_etl_dim_date","06_etl_dimensions","07_etl_facts","08_etl_orchestration","09_dq_checks","10_rpt_views") { Sql "sql\$f.sql" "AW_BI" }
Sql sql\02b_source_synonyms.sql "AW_BI" "SourceDb=$SourceDb"
Write-Host ">> running ETL"; & sqlcmd -S $Server -E -C -b -d AW_BI -Q "EXEC etl.usp_run_all @extract_mode = 'LOCAL', @triggered_by = N'setup_local.ps1';"; if ($LASTEXITCODE) { throw "ETL failed" }
New-Item -ItemType Directory -Force -Path tests\results | Out-Null; $out = "tests\results\sql_tests_$(Get-Date -Format yyyyMMdd_HHmmss).txt"
foreach ($t in "01_integrity","02_kpi_baselines","03_source_reconciliation","04_performance_report") {
  "=== $t" | Tee-Object -FilePath $out -Append; & sqlcmd -S $Server -E -C -d AW_BI -b -W -s "|" -i "tests\sql\$t.sql" 2>&1 | Tee-Object -FilePath $out -Append }
Write-Host "Done. Results: $out"
