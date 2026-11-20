#!/usr/bin/env bash
# Downloads (1) the AdventureWorks2022 .bak (to restore into SQL Server) and (2) the OLTP CSV install script
# (only needed for the Python tests: tools/ + tests/test_pipeline.py). MIT-licensed sample from Microsoft.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
BASE="https://github.com/Microsoft/sql-server-samples/releases/download/adventureworks"
if [ -z "${SKIP_BAK:-}" ] && [ ! -f data/AdventureWorks2022.bak ]; then
  echo "Downloading AdventureWorks2022.bak (~200 MB)..."; curl -fL -o data/AdventureWorks2022.bak "$BASE/AdventureWorks2022.bak"
fi
if [ ! -f data/aw_oltp_csv/instawdb.sql ]; then
  echo "Downloading OLTP CSV install script (~15 MB)..."
  curl -fL -o data/aw_oltp.zip "$BASE/AdventureWorks-oltp-install-script.zip"
  mkdir -p data/aw_oltp_csv && unzip -q -o data/aw_oltp.zip -d data/aw_oltp_csv && rm data/aw_oltp.zip
fi
echo "Done. data/AdventureWorks2022.bak and data/aw_oltp_csv/ are ready."
