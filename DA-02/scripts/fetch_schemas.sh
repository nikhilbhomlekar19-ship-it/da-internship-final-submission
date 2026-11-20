#!/usr/bin/env bash
# Fetches Microsoft's published PBIR / PBIP JSON schemas (used by tools/validate_model.py). ~4 MB sparse clone.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .cache && cd .cache
[ -d json-schemas ] || git clone -q --depth 1 --filter=blob:none --sparse https://github.com/microsoft/json-schemas.git
cd json-schemas && git sparse-checkout set fabric/item/report fabric/item/semanticModel fabric/gitIntegration fabric/pbip
echo "Schemas ready: export PBIR_SCHEMA_DIR=$(pwd)"
