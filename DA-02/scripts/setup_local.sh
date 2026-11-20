#!/usr/bin/env bash
# One-shot local build on Linux/macOS/WSL against SQL Server (docker compose up -d) or any reachable instance.
# Restores AdventureWorks2022, creates AW_BI, runs the ETL and the SQL test suite.
#   SQLSERVER=localhost,1433  SQLUSER=sa  SQLPASSWORD='YourStrong!Passw0rd'  ./scripts/setup_local.sh
set -euo pipefail
cd "$(dirname "$0")/.."
SERVER="${SQLSERVER:-localhost,1433}"; USER="${SQLUSER:-sa}"; PASS="${SQLPASSWORD:?set SQLPASSWORD}"; SRC_DB="${SOURCE_DB:-AdventureWorks2022}"
SQLCMD="sqlcmd -S $SERVER -U $USER -P $PASS -C -b"          # -C trusts the dev certificate
run() { echo ">> $1"; $SQLCMD ${2:-} -i "$1" ${3:-}; }
./scripts/download_adventureworks.sh
if ! $SQLCMD -Q "SET NOCOUNT ON; SELECT 1 FROM sys.databases WHERE name = N'$SRC_DB'" -h -1 | grep -q 1; then
  echo ">> restoring $SRC_DB (docker path /var/opt/mssql/backup/AdventureWorks2022.bak; mount ./data there or edit RESTORE path)"
  $SQLCMD -Q "RESTORE DATABASE [$SRC_DB] FROM DISK = N'/var/opt/mssql/backup/AdventureWorks2022.bak' WITH MOVE 'AdventureWorks2022' TO '/var/opt/mssql/data/$SRC_DB.mdf', MOVE 'AdventureWorks2022_log' TO '/var/opt/mssql/data/${SRC_DB}_log.ldf', REPLACE"
fi
run sql/00_create_database.sql
for f in 01_framework 02_staging 03_dw_schema 04_security 05_etl_dim_date 06_etl_dimensions 07_etl_facts 08_etl_orchestration 09_dq_checks 10_rpt_views; do run sql/$f.sql "-d AW_BI"; done
run sql/02b_source_synonyms.sql "-d AW_BI" "-v SourceDb=$SRC_DB"
echo ">> running ETL"; $SQLCMD -d AW_BI -Q "EXEC etl.usp_run_all @extract_mode = 'LOCAL', @triggered_by = N'setup_local.sh';"
./scripts/run_sql_tests.sh
