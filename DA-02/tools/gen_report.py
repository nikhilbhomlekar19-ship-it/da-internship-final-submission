"""Generates the PBIR report (PBIP report folder): 5 executive pages + 3 drill-through pages.
Visuals are declared compactly below and expanded to Power BI's PBIR JSON. Validated against Microsoft's JSON schemas by validate_model.py."""
import os, json, uuid, shutil
import model_spec as ms
from gen_powerbi import REPORT_DIR, MODEL_DIR, guid, w, ROOT

SCH = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
V_REPORT, V_PAGE, V_VISUAL, V_PAGES, V_VERSION = "3.0.0", "2.0.0", "2.5.0", "1.0.0", "1.0.0"
M = "_Measures"

# ---- field helpers ------------------------------------------------------------------------------
def disp(table, name):
    t = next(t for t in ms.ALL + [ms.SEC] if t.model == table)
    return next(c for c in t.cols if c.name == name).display

def col(table, colname):
    p = colname if " " in colname or colname[0].isupper() else disp(table, colname)
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": p}}, table, p

def meas(name):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": M}}, "Property": name}}, M, name

def proj(f):
    field, ent, prop = f
    return {"field": field, "queryRef": f"{ent}.{prop}", "nativeQueryRef": prop}

lit = lambda v: {"expr": {"Literal": {"Value": v}}}
C = lambda t, c: col(t, c)
Mm = meas

# ---- visuals --------------------------------------------------------------------------------------
class Page:
    def __init__(self, key, title, drill=None):
        self.key, self.title, self.drill, self.visuals, self.z = key, title, drill, [], 0
    def add(self, vtype, x, y, w_, h, roles=None, title=None, sort=None, sync=None, objects=None):
        self.z += 1
        name = uuid.uuid5(uuid.UUID("11111111-2222-3333-4444-555555555555"), f"{self.key}.{self.z}").hex[:20]
        v = {"visualType": vtype}
        if roles:
            qs = {r: {"projections": [proj(f) for f in fs]} for r, fs in roles.items()}
            v["query"] = {"queryState": qs}
            if sort: v["query"]["sortDefinition"] = {"sort": [{"field": sort[0][0], "direction": sort[1]}], "isDefaultSort": True}
        if objects: v["objects"] = objects
        if title: v["visualContainerObjects"] = {"title": [{"properties": {"show": lit("true"), "text": lit("'" + title.replace("'", "''") + "'")}}]}
        v["drillFilterOtherVisuals"] = True
        d = {"$schema": f"{SCH}/visualContainer/{V_VISUAL}/schema.json", "name": name,
             "position": {"x": x, "y": y, "z": self.z * 100, "height": h, "width": w_, "tabOrder": self.z * 100}, "visual": v}
        if sync: d["visual"]["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}
        self.visuals.append((name, d))
    # shortcuts
    def slicer(self, x, y, w_, h, f, title, sync):
        self.add("slicer", x, y, w_, h, {"Values": [f]}, title, sync=sync, objects={"data": [{"properties": {"mode": lit("'Dropdown'")}}]})
    def card(self, x, y, w_, h, m, title=None): self.add("card", x, y, w_, h, {"Values": [Mm(m)]}, title or m)
    def cards(self, ms_, y=84, h=92, x0=16, total=1248, gap=8):
        n = len(ms_); w_ = (total - gap * (n - 1)) // n
        for i, m in enumerate(ms_): self.card(x0 + i * (w_ + gap), y, w_, h, m)
    def line(self, x, y, w_, h, cat, ys, title, series=None):
        roles = {"Category": [cat], "Y": [Mm(m) for m in ys]}
        if series: roles["Series"] = [series]
        self.add("lineChart", x, y, w_, h, roles, title)
    def column(self, x, y, w_, h, cat, ys, title, series=None, sort=None):
        roles = {"Category": [cat], "Y": [Mm(m) for m in ys]}
        if series: roles["Series"] = [series]
        self.add("clusteredColumnChart", x, y, w_, h, roles, title, sort=sort)
    def bar(self, x, y, w_, h, cat, ys, title, sort_measure=None):
        self.add("clusteredBarChart", x, y, w_, h, {"Category": [cat], "Y": [Mm(m) for m in ys]}, title,
                 sort=(Mm(sort_measure or ys[0]), "Descending"))
    def table(self, x, y, w_, h, cols, title): self.add("tableEx", x, y, w_, h, {"Values": cols}, title)
    def matrix(self, x, y, w_, h, rows, vals, title): self.add("pivotTable", x, y, w_, h, {"Rows": rows, "Values": [Mm(m) for m in vals]}, title)

def build_pages():
    pages = []
    DATE_FY, TERR = C("Date", "fiscal_year_label"), C("Territory", "territory_name")
    def header(p, extra=None):
        p.slicer(16, 16, 200, 56, DATE_FY, "Fiscal Year", "sync_fy")
        p.slicer(228, 16, 200, 56, TERR, "Territory", "sync_territory")
        if extra: p.slicer(440, 16, 200, 56, extra[0], extra[1], extra[2])
        p.card(900, 16, 364, 56, "Data Through", "Data")
    # 1 Executive overview
    p = Page("exec", "Executive Overview"); header(p)
    p.cards(["Net Sales", "Net Sales YoY Growth %", "Gross Margin %", "Quota Attainment %", "Purchase Spend", "On-Time Delivery %", "Headcount"])
    p.line(16, 188, 760, 262, C("Date", "year_month_label"), ["Net Sales", "Net Sales Rolling 3M Avg", "Net Sales PY"], "Net Sales - monthly, rolling 3M average and prior year")
    p.bar(788, 188, 476, 262, C("Territory", "territory_name"), ["Net Sales"], "Net Sales by Territory")
    p.column(16, 462, 600, 242, C("Product", "product_category"), ["Net Sales", "Gross Margin"], "Net Sales and Gross Margin by Category")
    p.table(628, 462, 636, 242, [C("Territory", "territory_name"), Mm("Net Sales"), Mm("Net Sales YoY Growth %"), Mm("Gross Margin %"), Mm("Quota Attainment %"), Mm("Purchase Spend")], "Territory scorecard")
    pages.append(p)
    # 2 Sales
    p = Page("sales", "Sales Performance"); header(p, (C("Sales", "order_channel"), "Channel", "sync_channel"))
    p.cards(["Net Sales", "Orders", "Units Sold", "Avg Order Value", "Active Customers", "Discount %"])
    p.line(16, 188, 620, 250, C("Date", "year_month_label"), ["Net Sales"], "Net Sales by month and channel", series=C("Sales", "order_channel"))
    p.bar(648, 188, 616, 250, C("Product", "product_subcategory"), ["Net Sales"], "Net Sales by Product Subcategory")
    p.matrix(16, 450, 620, 254, [C("Product", "product_category"), C("Product", "product_subcategory")], ["Net Sales", "Net Sales YoY Growth %", "Gross Margin %"], "Category / subcategory (expand with the +)")
    p.table(648, 450, 616, 254, [C("Product", "product_name"), Mm("Net Sales"), Mm("Units Sold"), Mm("Gross Margin %")], "Products - right-click a product > Drill through > Product Detail")
    pages.append(p)
    # 3 Finance
    p = Page("finance", "Finance"); header(p)
    p.cards(["Net Sales", "COGS", "Gross Margin", "Gross Margin %", "Total Billed", "Est. Payroll Cost"])
    p.line(16, 188, 620, 250, C("Date", "year_month_label"), ["Gross Margin %", "Gross Margin % PY"], "Gross Margin % - current vs prior year")
    p.column(648, 188, 616, 250, C("Date", "fiscal_year_label"), ["Net Sales", "COGS", "Gross Margin"], "Net Sales, COGS and Gross Margin by fiscal year")
    p.table(16, 450, 760, 254, [C("Territory", "territory_name"), Mm("Net Sales"), Mm("COGS"), Mm("Gross Margin"), Mm("Gross Margin %"), Mm("Freight Billed"), Mm("Sales Tax Billed"), Mm("Total Billed")], "P&L by territory")
    p.column(788, 450, 476, 254, C("Date", "fiscal_year_label"), ["Purchase Spend", "Est. Payroll Cost", "Gross Margin after Payroll (est.)"], "Spend and payroll vs margin")
    pages.append(p)
    # 4 Supply chain
    p = Page("supply", "Supply Chain"); header(p, (C("Vendor", "preferred_status"), "Vendor status", "sync_vendor_status"))
    p.cards(["Purchase Spend", "PO Lines", "Active Vendors", "On-Time Delivery %", "Receipt Fill Rate %", "Reject Rate %", "Inventory Value", "Products Below Reorder Point"])
    p.line(16, 188, 620, 250, C("Date", "year_month_label"), ["Purchase Spend"], "Purchase spend by month")
    p.column(648, 188, 616, 250, C("Vendor", "credit_rating_label"), ["On-Time Delivery %", "Reject Rate %"], "Delivery and quality by vendor credit rating")
    p.bar(16, 450, 460, 254, C("Vendor", "vendor_name"), ["Purchase Spend"], "Purchase spend by vendor")
    p.table(488, 450, 776, 254, [C("Vendor", "vendor_name"), C("Vendor", "credit_rating_label"), Mm("Purchase Spend"), Mm("On-Time Delivery %"), Mm("Avg Days Late"), Mm("Reject Rate %")], "Vendors - right-click a vendor > Drill through > Vendor Detail")
    pages.append(p)
    # 5 HR
    p = Page("hr", "HR"); header(p, (C("Department", "department_name"), "Department", "sync_dept"))
    p.cards(["Headcount", "New Hires", "Avg Tenure (Years)", "Est. Payroll Cost", "Avg Monthly Cost per Employee", "Headcount YoY Growth %"])
    p.line(16, 188, 760, 250, C("Date", "year_month_label"), ["Headcount"], "Headcount by month")
    p.bar(788, 188, 476, 250, C("Department", "department_name"), ["Headcount"], "Headcount by department")
    p.column(16, 450, 620, 254, C("Date", "calendar_year"), ["New Hires"], "New hires by calendar year")
    p.table(648, 450, 616, 254, [C("Department", "department_name"), Mm("Headcount"), Mm("Avg Tenure (Years)"), Mm("Est. Payroll Cost"), Mm("Avg Monthly Cost per Employee")], "Departments")
    pages.append(p)
    # drill-through pages
    p = Page("d_product", "Product Detail", drill=("Product", "product_name"))
    p.cards(["Net Sales", "Units Sold", "Gross Margin %", "Orders"], y=16)
    p.line(16, 124, 760, 280, C("Date", "year_month_label"), ["Net Sales", "Net Sales Rolling 3M Avg"], "Net Sales by month")
    p.bar(788, 124, 476, 280, C("Territory", "territory_name"), ["Net Sales"], "Net Sales by territory")
    p.table(16, 416, 1248, 288, [C("Customer", "customer_name"), C("Customer", "customer_type"), Mm("Net Sales"), Mm("Units Sold"), Mm("Gross Margin %")], "Customers who bought this product")
    pages.append(p)
    p = Page("d_customer", "Customer Detail", drill=("Customer", "customer_name"))
    p.cards(["Net Sales", "Orders", "Avg Order Value", "Gross Margin %"], y=16)
    p.line(16, 124, 760, 280, C("Date", "year_month_label"), ["Net Sales"], "Net Sales by month")
    p.bar(788, 124, 476, 280, C("Product", "product_category"), ["Net Sales"], "Net Sales by category")
    p.table(16, 416, 1248, 288, [C("Sales", "sales_order_number"), C("Date", "full_date"), C("Product", "product_name"), Mm("Units Sold"), Mm("Net Sales")], "Orders")
    pages.append(p)
    p = Page("d_vendor", "Vendor Detail", drill=("Vendor", "vendor_name"))
    p.cards(["Purchase Spend", "PO Lines", "On-Time Delivery %", "Reject Rate %"], y=16)
    p.line(16, 124, 760, 280, C("Date", "year_month_label"), ["Purchase Spend"], "Purchase spend by month")
    p.bar(788, 124, 476, 280, C("Product", "product_name"), ["Purchase Spend"], "Spend by product")
    p.table(16, 416, 1248, 288, [C("Product", "product_name"), C("Purchases", "order_status"), Mm("Ordered Qty"), Mm("Received Qty"), Mm("Rejected Qty"), Mm("Avg Days Late"), Mm("Purchase Spend")], "Purchase order lines")
    pages.append(p)
    return pages

def page_json(p):
    name = "p_" + uuid.uuid5(uuid.UUID("11111111-2222-3333-4444-555555555555"), p.key).hex[:18]
    d = {"$schema": f"{SCH}/page/{V_PAGE}/schema.json", "name": name, "displayName": p.title, "displayOption": "FitToPage", "height": 720, "width": 1280}
    if p.drill:
        t, c = p.drill; f, ent, prop = col(t, c)
        fname = "f_" + name[2:]
        d["filterConfig"] = {"filters": [{"name": fname, "field": f, "type": "Categorical", "howCreated": "Drillthrough"}]}
        d["pageBinding"] = {"name": "b_" + name[2:], "type": "Drillthrough", "acceptsFilterContext": "Default",
                            "parameters": [{"name": "pm_" + name[2:], "boundFilter": fname, "fieldExpr": f}]}
    return name, d

def run():
    base = REPORT_DIR
    shutil.rmtree(os.path.join(ROOT, base), ignore_errors=True)
    wj = lambda path, obj: w(path, json.dumps(obj, indent=2) + "\n")
    wj(f"{base}/definition.pbir", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
                                   "version": "4.0", "datasetReference": {"byPath": {"path": "../EnterpriseBI.SemanticModel"}}})
    wj(f"{base}/.platform", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                              "metadata": {"type": "Report", "displayName": "Enterprise BI Suite"}, "config": {"version": "2.0", "logicalId": guid("report")}})
    wj(f"{base}/definition/version.json", {"$schema": f"{SCH}/versionMetadata/{V_VERSION}/schema.json", "version": "2.0.0"})
    wj(f"{base}/definition/report.json", {"$schema": f"{SCH}/report/{V_REPORT}/schema.json", "themeCollection": {}})
    pages = build_pages(); order = []
    for p in pages:
        name, d = page_json(p); order.append(name)
        wj(f"{base}/definition/pages/{name}/page.json", d)
        for vname, vd in p.visuals:
            wj(f"{base}/definition/pages/{name}/visuals/{vname}/visual.json", vd)
    wj(f"{base}/definition/pages/pages.json", {"$schema": f"{SCH}/pagesMetadata/{V_PAGES}/schema.json", "pageOrder": order, "activePageName": order[0]})
    return pages
