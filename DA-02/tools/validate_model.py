"""Static validation of the Power BI artifacts (no Power BI Desktop required):
 1. every PBIR/PBIP/.platform JSON file validates against Microsoft's published JSON schemas
 2. every DAX reference (Table[Column], [Measure]) in measures.dax / rls.dax exists in the generated model
 3. every field used by a report visual exists in the model
 4. TMDL files are tab-indented and reference only existing tables/columns
Schemas: set PBIR_SCHEMA_DIR to a clone of https://github.com/microsoft/json-schemas (see scripts/fetch_schemas.sh)."""
import os, re, sys, json, glob
import jsonschema
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7
import model_spec as ms
import gen_powerbi as gp

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIR = os.environ.get("PBIR_SCHEMA_DIR", os.path.join(ROOT, ".cache", "json-schemas"))
errors, warnings = [], []

def catalog():
    cat = {}
    for t in ms.ALL + [ms.SEC]: cat[t.model] = {c.display for c in t.cols}
    cat["_Measures"] = {m["name"] for m in gp.parse_measures()} | {"Placeholder"}
    return cat

# ---------------------------------------------------------------- 1. schemas
def validate_schemas():
    if not os.path.isdir(os.path.join(SCHEMA_DIR, "fabric")):
        warnings.append(f"schema dir not found ({SCHEMA_DIR}) - JSON schema validation SKIPPED"); return 0, 0
    def retrieve(uri):
        rel = uri.split("json-schemas/", 1)[1]
        return Resource.from_contents(json.load(open(os.path.join(SCHEMA_DIR, rel))), default_specification=DRAFT7)
    reg = Registry(retrieve=retrieve)
    ok = bad = 0
    files = [f for pat in ("**/*.json", "**/*.pbir", "**/*.pbism", "**/*.pbip", "**/.platform") for f in glob.glob(os.path.join(ROOT, "powerbi", pat), recursive=True)]
    for f in sorted(set(files)):
        if "/theme/" in f.replace("\\", "/"): continue
        doc = json.load(open(f))
        sch_url = doc.get("$schema", "")
        if "json-schemas/" not in sch_url: continue
        try:
            sch = json.load(open(os.path.join(SCHEMA_DIR, sch_url.split("json-schemas/", 1)[1])))
        except FileNotFoundError:
            warnings.append(f"schema not cached for {os.path.relpath(f, ROOT)}: {sch_url}"); continue
        v = jsonschema.validators.validator_for(sch, default=jsonschema.Draft7Validator)(sch, registry=reg)
        errs = sorted(v.iter_errors(doc), key=lambda e: list(e.path))
        if errs:
            bad += 1; errors.append(f"SCHEMA {os.path.relpath(f, ROOT)}: {errs[0].message[:160]} at {list(errs[0].path)[:6]}")
        else: ok += 1
    return ok, bad

# ---------------------------------------------------------------- 2. DAX references
REF = re.compile(r"(?:'([^']+)'|\b([A-Za-z_][A-Za-z0-9_]*))\[([^\]]+)\]")
BARE = re.compile(r"(?<![\w'\]])\[([^\]]+)\]")

def check_dax(cat, label, expr, measures):
    for t1, t2, c in REF.findall(expr):
        t = t1 or t2
        if t not in cat: errors.append(f"DAX {label}: unknown table '{t}' in {t}[{c}]")
        elif c not in cat[t]: errors.append(f"DAX {label}: unknown column/measure {t}[{c}]")
    stripped = REF.sub("", expr)
    for c in BARE.findall(stripped):
        if c not in measures: errors.append(f"DAX {label}: unknown measure [{c}]")

def validate_dax(cat):
    meas = gp.parse_measures(); names = [m["name"] for m in meas]
    if len(set(names)) != len(names): errors.append("duplicate measure names")
    for m in meas:
        check_dax(cat, m["name"], m["expr"], set(names))
        if not m["folder"]: errors.append(f"measure {m['name']} has no folder")
    rls = open(os.path.join(ROOT, "powerbi/dax/rls.dax")).read()
    check_dax(cat, "rls.dax", "\n".join(l for l in rls.splitlines() if not l.startswith("//")), set(names))
    return len(meas)

# ---------------------------------------------------------------- 3. report fields
def validate_report(cat):
    n = 0
    for f in glob.glob(os.path.join(ROOT, gp.REPORT_DIR, "definition/pages/**/*.json"), recursive=True):
        txt = open(f).read()
        for m in re.finditer(r'"(Column|Measure)": \{\s*"Expression": \{\s*"SourceRef": \{\s*"Entity": "([^"]+)"\s*\}\s*\},\s*"Property": "([^"]+)"', txt):
            kind, ent, prop = m.groups(); n += 1
            if ent not in cat or prop not in cat[ent]: errors.append(f"REPORT {os.path.relpath(f, ROOT)}: unknown {kind} {ent}[{prop}]")
            if kind == "Measure" and ent != "_Measures": errors.append(f"REPORT measure not in _Measures: {ent}[{prop}]")
    return n

# ---------------------------------------------------------------- 4. TMDL structure
def validate_tmdl(cat):
    n = 0
    for f in glob.glob(os.path.join(ROOT, gp.MODEL_DIR, "definition/**/*.tmdl"), recursive=True):
        for i, line in enumerate(open(f, encoding="utf-8").read().splitlines(), 1):
            if line.startswith(" "): errors.append(f"TMDL {os.path.relpath(f, ROOT)}:{i}: line starts with spaces (TMDL needs tabs)")
        n += 1
    rel = open(os.path.join(ROOT, gp.MODEL_DIR, "definition/relationships.tmdl")).read()
    for side, tbl, c in re.findall(r"(fromColumn|toColumn): ('[^']+'|[\w]+)\.('[^']+'|[\w]+)", rel):
        tbl, c = tbl.strip("'"), c.strip("'")
        if tbl not in cat or c not in cat[tbl]: errors.append(f"TMDL relationship refers to unknown {tbl}.{c}")
    for t in ms.ALL:
        for c in t.cols:
            if c.sort_by and t.col(c.sort_by).display not in cat[t.model]: errors.append(f"sortBy missing {t.name}.{c.name}")
    return n

if __name__ == "__main__":
    cat = catalog()
    ok, bad = validate_schemas()
    nm = validate_dax(cat); nf = validate_report(cat); nt = validate_tmdl(cat)
    print(f"JSON schema: {ok} files valid, {bad} invalid")
    print(f"DAX: {nm} measures checked | report field references checked: {nf} | TMDL files checked: {nt}")
    for w_ in warnings: print("WARN", w_)
    for e in errors[:40]: print("ERROR", e)
    print("RESULT:", "FAIL" if errors else "OK", f"({len(errors)} errors)")
    sys.exit(1 if errors else 0)
