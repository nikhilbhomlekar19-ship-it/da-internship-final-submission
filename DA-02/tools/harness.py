"""Executes the *same* T-SQL transform SELECTs that ship in sql/transforms/ against the real
AdventureWorks data in DuckDB (via sqlglot tsql->duckdb transpilation). This verifies join logic,
grain, key lookups and reconciliations without needing SQL Server. It does NOT verify T-SQL
wrapper code (DDL, procs, MERGE-free upserts) - run tests/sql/ on SQL Server for that."""
import os, re, sys, datetime as dt
import duckdb, pandas as pd, sqlglot
sys.path.insert(0, os.path.dirname(__file__))
import model_spec as ms
from aw_loader import AW
from dim_date import date_rows

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DDB = lambda ty: ("BIGINT" if re.match(r"(int|smallint|tinyint|bigint)$", ty) else "SMALLINT" if ty == "bit" else
                  "DECIMAL(19,4)" if ty == "money" else ty.upper() if ty.startswith("decimal") else
                  "TIMESTAMP" if ty == "datetime" else "DATE" if ty == "date" else "VARCHAR")

def tsql_to_duck(sql):
    return sqlglot.transpile(sql, read="tsql", write="duckdb")[0]

def load_staging(con, aw):
    con.execute("CREATE SCHEMA IF NOT EXISTS stg")
    for t, spec in ms.STG.items():
        df = aw.load(t)
        cols = ms.stg_cols(t)
        out = pd.DataFrame()
        for n, ty, src in cols:
            s = df[src]
            if re.match(r"(int|smallint|tinyint|bit)$", ty): s = pd.to_numeric(s).astype("Int64")
            elif ty in ("money",) or ty.startswith("decimal"): s = pd.to_numeric(s)
            elif ty in ("datetime", "date"): s = pd.to_datetime(s)
            out[n] = s
        con.register("tmp_df", out)
        ddl = ", ".join(f'"{n}" {DDB(ty)}' for n, ty, _ in cols)
        con.execute(f"CREATE TABLE stg.{t} ({ddl})")
        con.execute(f"INSERT INTO stg.{t} SELECT * FROM tmp_df")
        con.unregister("tmp_df")

def create_dw(con):
    con.execute("CREATE SCHEMA IF NOT EXISTS dw")
    for t in ms.ALL:
        ddl = ", ".join(f'"{c.name}" {DDB(c.ty)}' for c in t.cols)
        con.execute(f"CREATE TABLE dw.{t.name} ({ddl})")

def date_window(con):
    q = """SELECT MIN(d), MAX(d) FROM (
      SELECT OrderDate d FROM stg.SalesOrderHeader UNION ALL SELECT DueDate FROM stg.SalesOrderHeader UNION ALL SELECT ShipDate FROM stg.SalesOrderHeader
      UNION ALL SELECT OrderDate FROM stg.PurchaseOrderHeader UNION ALL SELECT ShipDate FROM stg.PurchaseOrderHeader UNION ALL SELECT DueDate FROM stg.PurchaseOrderDetail
      UNION ALL SELECT QuotaDate FROM stg.SalesPersonQuotaHistory UNION ALL SELECT CAST(HireDate AS TIMESTAMP) FROM stg.Employee) x"""
    lo, hi = con.execute(q).fetchall()[0]
    lo, hi = lo.date(), hi.date()
    nxt = (hi.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return dt.date(lo.year, 1, 1), nxt - dt.timedelta(days=1)

def load_dw(con):
    start, end = date_window(con)
    rows = date_rows(start, end)
    cols = [c.name for c in ms.BY_NAME["dim_date"].cols]
    con.register("tmp_dates", pd.DataFrame(rows)[cols])
    con.execute(f"INSERT INTO dw.dim_date SELECT * FROM tmp_dates")
    con.unregister("tmp_dates")
    stats = {"date_range": (str(start), str(end))}
    for t in ms.DIMS:
        if t.name == "dim_date": continue
        sel = tsql_to_duck(open(os.path.join(ROOT, "sql/transforms", t.name + ".sql")).read())
        names = [c.name for c in t.cols[1:]]
        unk = t.unknown
        cols_sql = ", ".join([t.key] + list(unk))
        vals = ", ".join(["-1"] + [str(v) for v in unk.values()])
        con.execute(f"INSERT INTO dw.{t.name} ({cols_sql}) VALUES ({vals})")
        nk = t.nk[0]
        con.execute(f"INSERT INTO dw.{t.name} ({t.key}, {', '.join(names)}) "
                    f"SELECT ROW_NUMBER() OVER (ORDER BY q.{nk}), {', '.join('q.'+n for n in names)} FROM ({sel}) q")
        stats[t.name] = con.execute(f"SELECT COUNT(*) FROM dw.{t.name}").fetchall()[0][0]
    for t in ms.FACTS:
        sel = tsql_to_duck(open(os.path.join(ROOT, "sql/transforms", t.name + ".sql")).read())
        names = [c.name for c in t.cols]
        con.execute(f"INSERT INTO dw.{t.name} ({', '.join(names)}) {sel}")
        stats[t.name] = con.execute(f"SELECT COUNT(*) FROM dw.{t.name}").fetchall()[0][0]
    return stats

def build(aw_folder):
    con = duckdb.connect(":memory:")
    aw = AW(aw_folder)
    load_staging(con, aw)
    create_dw(con)
    stats = load_dw(con)
    return con, stats

if __name__ == "__main__":
    con, st = build(sys.argv[1])
    for k, v in st.items(): print(k, v)
