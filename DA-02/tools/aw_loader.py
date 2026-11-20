"""Load the official AdventureWorks OLTP CSV files (from AdventureWorks-oltp-install-script.zip)
into pandas DataFrames. Column order is parsed from the DDL inside instawdb.sql, so it is
always consistent with the CSVs. Used by compute_baselines.py and the pytest harness."""
import re, os
import pandas as pd


def parse_ddl(sql_text):
    """Return {(schema, table): [col, ...]} in physical order (computed columns included)."""
    out = {}
    for m in re.finditer(r"CREATE TABLE \[(\w+)\]\.\[(\w+)\]\((.*?)\n\)", sql_text, re.S):
        schema, table, body = m.groups()
        cols = []
        for line in body.splitlines():
            line = line.strip()
            c = re.match(r"\[(\w+)\]\s", line)
            if c and not line.upper().startswith(("CONSTRAINT", "PRIMARY", "UNIQUE", "FOREIGN", "CHECK")):
                cols.append(c.group(1))
        out[(schema, table)] = cols
    return out


def _unesc(v):
    v = v.replace("\\\\", "\\")
    return {"0x0a": "\n"}.get(v, v.replace("\\t", "\t").replace("\\n", "\n").replace("\\r", "\r"))


def parse_bulk(sql_text):
    """Return {table: (field_terminator, row_terminator)}"""
    res = {}
    for m in re.finditer(r"BULK INSERT \[(\w+)\]\.\[(\w+)\] FROM '[^']*?(\w+)\.csv'\s*WITH \((.*?)\);", sql_text, re.S):
        schema, table, _, opts = m.groups()
        ft = re.search(r"FIELDTERMINATOR\s*=\s*'([^']*)'", opts).group(1)
        rt = re.search(r"ROWTERMINATOR\s*=\s*'([^']*)'", opts).group(1)
        res[table] = (_unesc(ft), _unesc(rt))
    return res


class AW:
    def __init__(self, folder):
        self.folder = folder
        txt = open(os.path.join(folder, "instawdb.sql"), encoding="utf-8-sig").read()
        self.ddl = parse_ddl(txt)
        self.bulk = parse_bulk(txt)
        self.schema_of = {t: s for (s, t) in self.ddl}

    def load(self, table):
        cols = self.ddl[(self.schema_of[table], table)]
        ft, rt = self.bulk[table]
        raw = open(os.path.join(self.folder, f"{table}.csv"), encoding="utf-8", errors="replace", newline="").read()
        rows = [r for r in raw.split(rt) if r != ""]
        recs = [r.split(ft) for r in rows]
        bad = [i for i, r in enumerate(recs) if len(r) != len(cols)]
        if bad:
            raise ValueError(f"{table}: {len(bad)} rows have != {len(cols)} fields (first bad {bad[0]}: {len(recs[bad[0]])})")
        return pd.DataFrame(recs, columns=cols).replace({"": None})
