"""Static checks that need neither SQL Server nor Power BI Desktop nor the AdventureWorks data."""
import os, sys, json, glob, copy, pytest, logging
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
logging.getLogger("sqlglot").setLevel(logging.ERROR)
import build_repo, validate_model as vm, lint_sql
SCHEMAS = os.path.isdir(os.path.join(vm.SCHEMA_DIR, "fabric"))

def test_generated_files_are_up_to_date():
    before = build_repo.snapshot(); build_repo.build(); after = build_repo.snapshot()
    assert before == after, sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))[:10]

def test_sql_files_parse():
    bad = []
    for f in glob.glob(os.path.join(ROOT, "sql", "*.sql")) + glob.glob(os.path.join(ROOT, "tests", "sql", "*.sql")):
        ok, cmd, nbad, errs = lint_sql.check_file(f)
        if nbad: bad.append((os.path.basename(f), errs[0]))
    assert not bad, bad

def test_power_bi_model_is_consistent():
    vm.errors.clear(); cat = vm.catalog()
    vm.validate_dax(cat); vm.validate_report(cat); vm.validate_tmdl(cat)
    assert not vm.errors, vm.errors[:5]

def test_dax_linter_detects_unknown_column_and_measure():
    vm.errors.clear(); cat = vm.catalog()
    vm.check_dax(cat, "t", "SUM ( Sales[No Such Column] ) + [Missing Measure]", {"Net Sales"})
    assert any("No Such Column" in e for e in vm.errors) and any("Missing Measure" in e for e in vm.errors)
    vm.errors.clear()

@pytest.mark.skipif(not SCHEMAS, reason="run scripts/fetch_schemas.sh and set PBIR_SCHEMA_DIR")
def test_pbir_files_validate_against_microsoft_schemas():
    vm.errors.clear(); vm.warnings.clear(); ok, bad = vm.validate_schemas()
    assert bad == 0 and ok > 50, vm.errors[:3]

@pytest.mark.skipif(not SCHEMAS, reason="needs schemas")
def test_schema_validation_rejects_a_broken_visual(tmp_path):
    import jsonschema
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT7
    f = glob.glob(os.path.join(ROOT, "powerbi", "EnterpriseBI.Report", "definition", "pages", "*", "visuals", "*", "visual.json"))[0]
    doc = json.load(open(f)); del doc["position"]                       # position is required by the schema
    sch = json.load(open(os.path.join(vm.SCHEMA_DIR, doc["$schema"].split("json-schemas/", 1)[1])))
    reg = Registry(retrieve=lambda uri: Resource.from_contents(json.load(open(os.path.join(vm.SCHEMA_DIR, uri.split("json-schemas/", 1)[1]))), default_specification=DRAFT7))
    assert list(jsonschema.Draft7Validator(sch, registry=reg).iter_errors(doc))

def test_adf_references_resolve():
    def load(folder): return {os.path.basename(p)[:-5]: json.load(open(p)) for p in glob.glob(os.path.join(ROOT, "adf", folder, "*.json"))}
    ls, ds, pl, tr = load("linkedService"), load("dataset"), load("pipeline"), load("trigger")
    refs = []
    def walk(o):
        if isinstance(o, dict):
            if "referenceName" in o and "type" in o: refs.append((o["type"], o["referenceName"]))
            for v in o.values(): walk(v)
        elif isinstance(o, list):
            for v in o: walk(v)
    for d in (ls, ds, pl, tr): walk(d)
    known = {"LinkedServiceReference": set(ls), "DatasetReference": set(ds), "PipelineReference": set(pl), "IntegrationRuntimeReference": {"{{SELF_HOSTED_IR_NAME}}"}}
    missing = [r for r in refs if r[1] not in known.get(r[0], set())]
    assert not missing, missing
    for name, p in pl.items():                                  # dependsOn must point to sibling activities
        def check(acts):
            names = {a["name"] for a in acts}
            for a in acts:
                for dep in a.get("dependsOn", []): assert dep["activity"] in names, (name, a["name"], dep)
                tp = a.get("typeProperties", {})
                for k in ("activities", "ifTrueActivities", "ifFalseActivities"):
                    if k in tp: check(tp[k])
        check(p["properties"]["activities"])

PATTERNS = ("Account" + "Key=", "SharedAccess" + "Signature", "BEGIN PRIVATE" + " KEY", "Password=" + "'")

def test_no_secrets_committed():
    bad = []
    for dp, _, fs in os.walk(ROOT):
        if any(x in dp for x in (".git", ".cache", "data")): continue
        for f in fs:
            if f.endswith((".sql", ".json", ".ps1", ".sh", ".md", ".py", ".tmdl", ".yml")):
                t = open(os.path.join(dp, f), errors="ignore").read()
                if any(p in t for p in PATTERNS): bad.append(f)
    assert not bad, bad
