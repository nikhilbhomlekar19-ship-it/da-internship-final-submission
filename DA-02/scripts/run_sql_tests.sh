#!/usr/bin/env bash
# Runs tests/sql/*.sql against AW_BI and stores the output in tests/results/sql_tests_<timestamp>.txt
set -uo pipefail
cd "$(dirname "$0")/.."
SERVER="${SQLSERVER:-localhost,1433}"; USER="${SQLUSER:-sa}"; PASS="${SQLPASSWORD:?set SQLPASSWORD}"
OUT="tests/results/sql_tests_$(date +%Y%m%d_%H%M%S).txt"; mkdir -p tests/results; rc=0
for f in tests/sql/01_integrity.sql tests/sql/02_kpi_baselines.sql tests/sql/03_source_reconciliation.sql tests/sql/04_performance_report.sql; do
  echo "=== $f" | tee -a "$OUT"
  sqlcmd -S "$SERVER" -U "$USER" -P "$PASS" -C -d AW_BI -b -W -s "|" -i "$f" 2>&1 | tee -a "$OUT" || rc=1
done
echo "Results saved to $OUT"; exit $rc
