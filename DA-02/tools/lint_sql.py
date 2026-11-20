"""Static T-SQL check: split every sql/*.sql file on GO and parse each batch with sqlglot (tsql dialect).
Reports how many batches fully parsed. This is a SYNTAX check only - it does not execute anything."""
import glob, os, re, sys, logging
import sqlglot
logging.getLogger("sqlglot").setLevel(logging.ERROR)
from sqlglot import exp
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def batches(text):
    return [b.strip() for b in re.split(r"^\s*GO\s*$", text, flags=re.M | re.I) if b.strip()]

def check_file(path):
    ok = cmd = bad = 0; errors = []
    for b in batches(open(path, encoding="utf-8").read()):
        if re.match(r"(GRANT|DENY|REVOKE)\b", re.sub(r"(?m)^\s*--.*$", "", b).strip(), re.I):
            cmd += 1; continue                       # valid T-SQL that sqlglot cannot parse (GRANT ... ON SCHEMA::x)
        b2 = re.sub(r"\$\(\w+\)", "SrcDb", b)           # sqlcmd variables
        try:
            tree = sqlglot.parse(b2, read="tsql")
            if any(isinstance(t, exp.Command) for t in tree if t is not None): cmd += 1
            else: ok += 1
        except Exception as e:
            bad += 1; errors.append((b[:70].replace("\n", " "), str(e).splitlines()[0][:110]))
    return ok, cmd, bad, errors

if __name__ == "__main__":
    tot = [0, 0, 0]
    for f in sorted(glob.glob(os.path.join(ROOT, "sql", "*.sql"))):
        ok, cmd, bad, errs = check_file(f)
        tot[0] += ok; tot[1] += cmd; tot[2] += bad
        print(f"{os.path.basename(f):28s} parsed={ok:3d} command-only={cmd:3d} errors={bad}")
        for e in errs: print("     ERR", e)
    print(f"TOTAL parsed={tot[0]} command-only={tot[1]} errors={tot[2]}")
    sys.exit(1 if tot[2] else 0)
