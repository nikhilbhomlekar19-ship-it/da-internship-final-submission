#!/usr/bin/env python
"""Append an always-correct column listing (read from the live warehouse) to docs/03_data_dictionary.md.
   python scripts/generate_data_dictionary.py   (after `make demo`)"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from customer360 import config as cfg  # noqa: E402
from customer360.warehouse import Warehouse  # noqa: E402

SCHEMAS = [("Raw sources", cfg.RAW_SCHEMA), ("Staging (views / tables)", cfg.dbt_schema("staging")),
           ("Intermediate", cfg.dbt_schema("intermediate")), ("Marts (what Tableau reads)", cfg.dbt_schema("marts")),
           ("ML outputs (written by Python)", cfg.ML_SCHEMA)]
with Warehouse(read_only=True) as wh:
    out = ["", "---", "", "## Appendix: column listing (generated from the warehouse)", ""]
    for title, schema in SCHEMAS:
        df = wh.query(f"select table_name, column_name, data_type from information_schema.columns where table_schema = '{schema}' order by table_name, ordinal_position")
        out += [f"### {title} - `{schema}`", ""]
        for t, g in df.groupby("table_name", sort=True):
            out.append(f"<details><summary><code>{t}</code> ({len(g)} columns)</summary>\n")
            out.append("| column | type |\n|---|---|")
            out += [f"| `{r.column_name}` | {r.data_type} |" for r in g.itertuples()]
            out.append("\n</details>\n")
doc = ROOT / "docs" / "03_data_dictionary.md"
text = doc.read_text()
marker = "\n---\n\n## Appendix: column listing"
if marker in text:
    text = text.split(marker)[0]
doc.write_text(text.rstrip() + "\n" + "\n".join(out))
print("updated", doc)
