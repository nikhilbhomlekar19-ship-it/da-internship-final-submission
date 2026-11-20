"""Regenerates every derived artifact. Usage:  python tools/build_repo.py [--check]
--check regenerates and fails if any committed generated file changed (CI drift check)."""
import os, sys, hashlib, logging
sys.path.insert(0, os.path.dirname(__file__))
logging.getLogger("sqlglot").setLevel(logging.ERROR)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GENERATED = ["sql", "adf", "powerbi", "docs", "tests/sql", "tests/dax"]

def snapshot():
    h = {}
    for d in GENERATED:
        for dp, _, fs in os.walk(os.path.join(ROOT, d)):
            for f in fs:
                p = os.path.join(dp, f); h[os.path.relpath(p, ROOT)] = hashlib.sha1(open(p, "rb").read()).hexdigest()
    return h

def build():
    import gen_sql, gen_powerbi, gen_report, gen_adf, gen_tests, gen_docs
    gen_sql.run(); gen_powerbi.run(); gen_report.run(); gen_adf.run(); gen_tests.run(); gen_docs.run()

if __name__ == "__main__":
    before = snapshot(); build(); after = snapshot()
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    if "--check" in sys.argv:
        if changed: print("generated files out of date:\n  " + "\n  ".join(changed[:20])); sys.exit(1)
        print("generated files are up to date")
    else:
        print(f"built; {len(changed)} files changed")
