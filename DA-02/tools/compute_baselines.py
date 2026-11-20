"""Independent (pandas) re-implementation of the KPI definitions, computed straight from the raw
AdventureWorks CSV files. Output: tests/baselines/expected_kpis.json. Used to cross-check the SQL
transforms (tests/test_pipeline.py) and the DAX measures (tests/dax/run_dax_tests.ps1)."""
import sys, os, json, datetime as dt
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
from aw_loader import AW

RATE_HOURS = 173.3333

def fy(d):  # fiscal year, July start, named by ending year
    return d.year + (1 if d.month >= 7 else 0)

def compute(folder):
    aw = AW(folder); L = aw.load
    num = lambda s: pd.to_numeric(s)
    h = L("SalesOrderHeader"); d = L("SalesOrderDetail"); p = L("Product"); ch = L("ProductCostHistory")
    h["OrderDate"] = pd.to_datetime(h.OrderDate)
    for c in ["OrderQty", "UnitPrice", "LineTotal", "SalesOrderID"]: d[c] = num(d[c])
    p["StandardCost"] = num(p.StandardCost); ch["StandardCost"] = num(ch.StandardCost)
    ch["StartDate"] = pd.to_datetime(ch.StartDate); ch["EndDate"] = pd.to_datetime(ch.EndDate)
    h["SalesOrderID"] = num(h.SalesOrderID); h["SalesPersonID"] = pd.to_numeric(h.SalesPersonID)
    s = d.merge(h[["SalesOrderID", "OrderDate", "TerritoryID", "SalesPersonID", "Freight", "SubTotal", "TaxAmt"]], on="SalesOrderID")
    s["ProductID"] = num(s.ProductID)
    c = ch.assign(ProductID=num(ch.ProductID))
    m = s.reset_index().merge(c, on="ProductID", how="left")
    m = m[(m.OrderDate >= m.StartDate) & (m.EndDate.isna() | (m.OrderDate <= m.EndDate))].set_index("index")
    s["hist_cost"] = m["StandardCost"]
    s = s.merge(p[["ProductID", "StandardCost"]].assign(ProductID=lambda x: num(x.ProductID)), on="ProductID", how="left", suffixes=("", "_cur"))
    s["unit_cost"] = s.hist_cost.fillna(s.StandardCost)
    s["cogs"] = s.OrderQty * s.unit_cost
    s["fy"] = s.OrderDate.map(fy); s["ym"] = s.OrderDate.dt.year * 100 + s.OrderDate.dt.month
    s["TerritoryID"] = num(s.TerritoryID)
    terr = L("SalesTerritory").set_index(num(L("SalesTerritory").TerritoryID))["Name"]
    net = s.LineTotal.sum(); cogs = s.cogs.sum()
    out = {"meta": {"source": "AdventureWorks OLTP CSV (AdventureWorks-oltp-install-script.zip)", "computed_by": "tools/compute_baselines.py", "rate_hours_per_month": RATE_HOURS}}
    sales = {"net_sales_total": net, "cogs_total": cogs, "gross_margin_total": net - cogs, "gross_margin_pct": (net - cogs) / net,
             "orders": int(s.SalesOrderID.nunique()), "lines": int(len(s)), "lines_without_cost_history": int(s.hist_cost.isna().sum()),
             "order_date_min": str(s.OrderDate.min().date()), "order_date_max": str(s.OrderDate.max().date())}
    by_fy = s.groupby("fy").LineTotal.sum().to_dict(); sales["net_sales_by_fiscal_year"] = {f"FY{k}": v for k, v in by_fy.items()}
    sales["net_sales_by_territory"] = {terr[k]: v for k, v in s.groupby("TerritoryID").LineTotal.sum().items()}
    sales["yoy_fy2025"] = by_fy[2025] / by_fy[2024] - 1
    sales["yoy_fy2024"] = by_fy[2024] / by_fy[2023] - 1
    ym = s.groupby("ym").LineTotal.sum()
    sales["net_sales_by_month"] = {str(k): v for k, v in ym.items()}
    sales["net_sales_fiscal_ytd_202412"] = s[(s.OrderDate >= "2024-07-01") & (s.OrderDate <= "2024-12-31")].LineTotal.sum()
    sales["rolling_3m_avg_202506"] = float(sum(ym[k] for k in (202504, 202505, 202506)) / 3)
    sales["gross_margin_pct_fy2024"] = float(1 - s[s.fy == 2024].cogs.sum() / s[s.fy == 2024].LineTotal.sum())
    sales["freight_allocated_total"] = float((s.Freight.astype(float) * s.LineTotal / s.SubTotal.astype(float)).sum())
    sales["freight_header_total"] = float(h[h.SalesOrderID.isin(s.SalesOrderID)].Freight.astype(float).sum())
    sales["online_orders"] = int(num(h.OnlineOrderFlag).sum())
    sales["total_billed"] = float(num(h.TotalDue).sum())
    sales["freight_billed"] = float(num(h.Freight).sum())
    sales["tax_billed"] = float(num(h.TaxAmt).sum())
    out["sales"] = sales
    # quota
    q = L("SalesPersonQuotaHistory"); q["QuotaDate"] = pd.to_datetime(q.QuotaDate); q["SalesQuota"] = num(q.SalesQuota)
    q["fy_months"] = None
    rows = []
    for _, r in q.iterrows():
        qn = (r.QuotaDate.month - 1) // 3
        for k in range(3):
            mo = qn * 3 + k + 1; dd = dt.date(r.QuotaDate.year, mo, 1)
            rows.append((int(r.BusinessEntityID), dd, r.SalesQuota / 3.0))
    qm = pd.DataFrame(rows, columns=["sp", "month", "amt"]); qm["fy"] = qm.month.map(fy)
    qsp = set(qm.sp)
    qfy = qm.groupby("fy").amt.sum().to_dict()
    sp_sales = s[s.SalesPersonID.isin(qsp)].groupby("fy").LineTotal.sum().to_dict()
    out["quota"] = {"quota_total": float(qm.amt.sum()), "quota_fy2024": float(qfy[2024]), "net_sales_quota_reps_fy2024": float(sp_sales[2024]),
                    "attainment_fy2024": float(sp_sales[2024] / qfy[2024]), "rows": int(len(qm))}
    # purchasing
    ph = L("PurchaseOrderHeader"); pdt = L("PurchaseOrderDetail")
    ph["ShipDate"] = pd.to_datetime(ph.ShipDate); pdt["DueDate"] = pd.to_datetime(pdt.DueDate)
    for c in ["LineTotal", "OrderQty", "ReceivedQty", "RejectedQty"]: pdt[c] = num(pdt[c])
    po = pdt.merge(ph[["PurchaseOrderID", "ShipDate", "VendorID", "OrderDate"]], on="PurchaseOrderID")
    po["OrderDate"] = pd.to_datetime(po.OrderDate)
    on_time = ((po.ShipDate <= po.DueDate) & po.ShipDate.notna()).sum(); shipped = po.ShipDate.notna().sum()
    ba, ad, sp_, vend = L("BusinessEntityAddress"), L("Address"), L("StateProvince"), L("Vendor")
    x = ba.merge(ad, on="AddressID").merge(sp_[["StateProvinceID", "TerritoryID"]], on="StateProvinceID")
    x["AddressTypeID"] = num(x.AddressTypeID); x["AddressID"] = num(x.AddressID); x["BusinessEntityID"] = num(x.BusinessEntityID)
    vt = x.sort_values(["BusinessEntityID", "AddressTypeID", "AddressID"]).drop_duplicates("BusinessEntityID").set_index(num(x.sort_values(["BusinessEntityID", "AddressTypeID", "AddressID"]).drop_duplicates("BusinessEntityID").BusinessEntityID))["TerritoryID"]
    po["VendorID"] = num(po.VendorID); po["terr"] = po.VendorID.map(vt).astype(int)
    out["purchasing"] = {"spend_total": float(po.LineTotal.sum()), "lines": int(len(po)), "on_time_pct": float(on_time / shipped),
                         "fill_rate": float(po.ReceivedQty.sum() / po.OrderQty.sum()), "reject_rate": float(po.RejectedQty.sum() / po.ReceivedQty.sum()),
                         "spend_by_territory": {terr[k]: float(v) for k, v in po.groupby("terr").LineTotal.sum().items()},
                         "order_date_max": str(po.OrderDate.max().date()), "vendors_with_orders": int(po.VendorID.nunique())}
    # inventory
    inv = L("ProductInventory"); inv["Quantity"] = num(inv.Quantity); inv["ProductID"] = num(inv.ProductID)
    pp = p.assign(ProductID=num(p.ProductID), ReorderPoint=num(p.ReorderPoint))
    iv = inv.merge(pp[["ProductID", "StandardCost", "ReorderPoint"]], on="ProductID")
    per = iv.groupby("ProductID").agg(q=("Quantity", "sum"), rp=("ReorderPoint", "first"))
    out["inventory"] = {"inventory_value": float((iv.Quantity * iv.StandardCost).sum()), "on_hand_qty": int(iv.Quantity.sum()),
                        "products_below_reorder_point": int((per.q < per.rp).sum()), "rows": int(len(inv))}
    # HR
    e = L("Employee"); e["HireDate"] = pd.to_datetime(e.HireDate); e["BusinessEntityID"] = num(e.BusinessEntityID)
    pay = L("EmployeePayHistory"); pay["RateChangeDate"] = pd.to_datetime(pay.RateChangeDate); pay["Rate"] = num(pay.Rate); pay["BusinessEntityID"] = num(pay.BusinessEntityID)
    def hc(date):
        date = pd.Timestamp(date); act = e[e.HireDate <= date]
        tot = 0.0
        for b in act.BusinessEntityID:
            pr = pay[(pay.BusinessEntityID == b) & (pay.RateChangeDate <= date)]
            if len(pr): tot += pr.sort_values("RateChangeDate").Rate.iloc[-1] * RATE_HOURS
        return len(act), tot
    n10, c10 = hc("2010-12-31"); n25, c25 = hc("2025-06-30")
    out["hr"] = {"headcount_201012": n10, "headcount_202506": n25, "payroll_cost_201012": float(c10), "payroll_cost_202506": float(c25),
                 "hire_date_min": str(e.HireDate.min().date()), "hire_date_max": str(e.HireDate.max().date()), "employees": int(len(e))}
    tmap = x[x.BusinessEntityID.isin(e.BusinessEntityID)].sort_values(["BusinessEntityID", "AddressTypeID", "AddressID"]).drop_duplicates("BusinessEntityID")
    out["hr"]["headcount_by_territory"] = {terr[k]: int(v) for k, v in tmap.groupby(num(tmap.TerritoryID)).size().items()}
    return out

if __name__ == "__main__":
    res = compute(sys.argv[1])
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tests", "baselines", "expected_kpis.json")
    json.dump(res, open(path, "w"), indent=2, default=float)
    print("wrote", path)
    print(json.dumps({k: res[k] for k in ("sales",)}, indent=1, default=float)[:1500])
