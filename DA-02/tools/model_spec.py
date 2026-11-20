"""Single source of truth for the Enterprise BI Suite.
Everything else (staging DDL, DW DDL, ETL procs, rpt views, ADF config, Power Query,
TMDL semantic model, PBIR report, data dictionary) is generated from this file."""
import re

# --------------------------------------------------------------------------- staging
# "Col:type" or "Col:type=SourceCol" (rename). Source tables are in AdventureWorks2022 (OLTP).
# inc = (watermark column, [key columns]) -> incremental (upsert) load in ADF, else full reload.
STG = {
 "SalesOrderHeader": dict(src="Sales.SalesOrderHeader", inc=("ModifiedDate", ["SalesOrderID"]), cols=[
    "SalesOrderID:int","OrderDate:datetime","DueDate:datetime","ShipDate:datetime","Status:tinyint","OnlineOrderFlag:bit",
    "SalesOrderNumber:nvarchar(25)","CustomerID:int","SalesPersonID:int","TerritoryID:int","ShipMethodID:int",
    "SubTotal:money","TaxAmt:money","Freight:money","TotalDue:money","ModifiedDate:datetime"]),
 "SalesOrderDetail": dict(src="Sales.SalesOrderDetail", inc=("ModifiedDate", ["SalesOrderID","SalesOrderDetailID"]), cols=[
    "SalesOrderID:int","SalesOrderDetailID:int","OrderQty:smallint","ProductID:int","SpecialOfferID:int",
    "UnitPrice:money","UnitPriceDiscount:money","LineTotal:decimal(38,6)","ModifiedDate:datetime"]),
 "Customer": dict(src="Sales.Customer", cols=["CustomerID:int","PersonID:int","StoreID:int","TerritoryID:int"]),
 "Person": dict(src="Person.Person", cols=["BusinessEntityID:int","PersonType:nvarchar(2)","FirstName:nvarchar(50)","MiddleName:nvarchar(50)","LastName:nvarchar(50)"]),
 "Store": dict(src="Sales.Store", cols=["BusinessEntityID:int","Name:nvarchar(50)","SalesPersonID:int"]),
 "SalesTerritory": dict(src="Sales.SalesTerritory", cols=["TerritoryID:int","Name:nvarchar(50)","CountryRegionCode:nvarchar(3)","TerritoryGroup:nvarchar(50)=Group"]),
 "CountryRegion": dict(src="Person.CountryRegion", cols=["CountryRegionCode:nvarchar(3)","Name:nvarchar(50)"]),
 "SalesPerson": dict(src="Sales.SalesPerson", cols=["BusinessEntityID:int","TerritoryID:int"]),
 "SalesPersonQuotaHistory": dict(src="Sales.SalesPersonQuotaHistory", cols=["BusinessEntityID:int","QuotaDate:datetime","SalesQuota:money"]),
 "SpecialOffer": dict(src="Sales.SpecialOffer", cols=["SpecialOfferID:int","Description:nvarchar(255)","DiscountPct:decimal(9,4)","Type:nvarchar(50)","Category:nvarchar(50)","StartDate:datetime","EndDate:datetime","MinQty:int","MaxQty:int"]),
 "ShipMethod": dict(src="Purchasing.ShipMethod", cols=["ShipMethodID:int","Name:nvarchar(50)"]),
 "Product": dict(src="Production.Product", cols=[
    "ProductID:int","Name:nvarchar(50)","ProductNumber:nvarchar(25)","MakeFlag:bit","FinishedGoodsFlag:bit","Color:nvarchar(15)",
    "SafetyStockLevel:smallint","ReorderPoint:smallint","StandardCost:money","ListPrice:money","Size:nvarchar(5)","Weight:decimal(8,2)",
    "DaysToManufacture:int","ProductLine:nvarchar(2)","Class:nvarchar(2)","Style:nvarchar(2)","ProductSubcategoryID:int","ProductModelID:int",
    "SellStartDate:datetime","SellEndDate:datetime","DiscontinuedDate:datetime"]),
 "ProductSubcategory": dict(src="Production.ProductSubcategory", cols=["ProductSubcategoryID:int","ProductCategoryID:int","Name:nvarchar(50)"]),
 "ProductCategory": dict(src="Production.ProductCategory", cols=["ProductCategoryID:int","Name:nvarchar(50)"]),
 "ProductModel": dict(src="Production.ProductModel", cols=["ProductModelID:int","Name:nvarchar(50)"]),
 "ProductCostHistory": dict(src="Production.ProductCostHistory", cols=["ProductID:int","StartDate:datetime","EndDate:datetime","StandardCost:money"]),
 "ProductInventory": dict(src="Production.ProductInventory", cols=["ProductID:int","LocationID:smallint","Quantity:smallint"]),
 "Location": dict(src="Production.Location", cols=["LocationID:smallint","Name:nvarchar(50)","CostRate:decimal(9,4)","Availability:decimal(8,2)"]),
 "Employee": dict(src="HumanResources.Employee", cols=["BusinessEntityID:int","JobTitle:nvarchar(50)","HireDate:date","SalariedFlag:bit","CurrentFlag:bit"]),
 "Department": dict(src="HumanResources.Department", cols=["DepartmentID:smallint","Name:nvarchar(50)","GroupName:nvarchar(50)"]),
 "EmployeeDepartmentHistory": dict(src="HumanResources.EmployeeDepartmentHistory", cols=["BusinessEntityID:int","DepartmentID:smallint","StartDate:date","EndDate:date"]),
 "EmployeePayHistory": dict(src="HumanResources.EmployeePayHistory", cols=["BusinessEntityID:int","RateChangeDate:datetime","Rate:money"]),
 "BusinessEntityAddress": dict(src="Person.BusinessEntityAddress", cols=["BusinessEntityID:int","AddressID:int","AddressTypeID:int"]),
 "Address": dict(src="Person.Address", cols=["AddressID:int","StateProvinceID:int"]),
 "StateProvince": dict(src="Person.StateProvince", cols=["StateProvinceID:int","TerritoryID:int"]),
 "PurchaseOrderHeader": dict(src="Purchasing.PurchaseOrderHeader", inc=("ModifiedDate", ["PurchaseOrderID"]), cols=[
    "PurchaseOrderID:int","Status:tinyint","VendorID:int","ShipMethodID:int","OrderDate:datetime","ShipDate:datetime","SubTotal:money","TaxAmt:money","Freight:money","ModifiedDate:datetime"]),
 "PurchaseOrderDetail": dict(src="Purchasing.PurchaseOrderDetail", inc=("ModifiedDate", ["PurchaseOrderID","PurchaseOrderDetailID"]), cols=[
    "PurchaseOrderID:int","PurchaseOrderDetailID:int","DueDate:datetime","OrderQty:smallint","ProductID:int","UnitPrice:money","LineTotal:money","ReceivedQty:decimal(8,2)","RejectedQty:decimal(8,2)","StockedQty:decimal(9,2)","ModifiedDate:datetime"]),
 "Vendor": dict(src="Purchasing.Vendor", cols=["BusinessEntityID:int","AccountNumber:nvarchar(15)","Name:nvarchar(50)","CreditRating:tinyint","PreferredVendorStatus:bit","ActiveFlag:bit"]),
}

def stg_cols(t):
    """-> [(stg_name, sql_type, source_name)]"""
    out = []
    for c in STG[t]["cols"]:
        left, _, src = c.partition("=")
        n, _, ty = left.partition(":")
        out.append((n, ty, src or n))
    return out

# --------------------------------------------------------------------------- warehouse
class Col:
    def __init__(self, name, ty, display=None, desc="", hidden=False, nullable=True, sort_by=None,
                 fmt=None, fk=None, active=True, model=True, identity=False, pk=False):
        self.name, self.ty, self.desc = name, ty, desc
        self.display = display or self._disp(name)
        self.hidden, self.nullable, self.sort_by, self.fmt = hidden, nullable, sort_by, fmt
        self.fk, self.active, self.model, self.identity, self.pk = fk, active, model, identity, pk
    @staticmethod
    def _disp(n):
        w = [{"id": "ID", "pct": "%", "of": "of"}.get(x, x.capitalize()) for x in n.split("_")]
        return " ".join(w).replace(" %", " %")

class Table:
    def __init__(self, name, model, kind, desc, cols, grain="", nk=None, unknown=None, view=True, order=0):
        self.name, self.model, self.kind, self.desc = name, model, kind, desc
        self.cols, self.grain, self.nk, self.unknown, self.view, self.order = cols, grain, nk, unknown, view, order
    @property
    def key(self):  # surrogate key column of a dimension
        return self.cols[0].name
    def col(self, n):
        return next(c for c in self.cols if c.name == n)

def C(*a, **k): return Col(*a, **k)
INT, DATE, BIT = "int", "date", "bit"
M19 = "decimal(19,4)"; M196 = "decimal(19,6)"
FK = lambda t, a=True: dict(fk=f"{t}", active=a, hidden=True)

DIMS = [
 Table("dim_date", "Date", "dim", "Conformed calendar + fiscal calendar (fiscal year starts July; FY is named by the year it ends).", [
    C("date_key", INT, hidden=True, nullable=False, pk=True, desc="yyyymmdd surrogate key"),
    C("full_date", DATE, "Date", nullable=False, desc="Calendar date (marked as the model's date table key)"),
    C("day_of_month", INT), C("day_name", "nvarchar(10)", sort_by="day_of_week"), C("day_of_week", INT, hidden=True, desc="1 = Monday"),
    C("week_of_year", INT, desc="ISO week"), C("month_number", INT, hidden=True),
    C("month_name", "nvarchar(10)", sort_by="month_number"), C("month_short", "nvarchar(3)", sort_by="month_number"),
    C("year_month_label", "nvarchar(10)", "Year Month", sort_by="year_month_number", desc="e.g. Jul 2024"),
    C("year_month_number", INT, hidden=True, desc="yyyymm"), C("month_index", INT, hidden=True, desc="year*12+month-1; used for rolling windows"),
    C("quarter_number", INT, hidden=True), C("quarter_name", "nvarchar(2)", sort_by="quarter_number"),
    C("year_quarter_label", "nvarchar(8)", "Year Quarter", sort_by="year_quarter_number"), C("year_quarter_number", INT, hidden=True),
    C("calendar_year", INT), C("fiscal_year", INT, desc="Fiscal year number (Jul-Jun, named by ending year)"),
    C("fiscal_year_label", "nvarchar(8)", "Fiscal Year Label", sort_by="fiscal_year", desc="e.g. FY2025"),
    C("fiscal_quarter_number", INT, hidden=True),
    C("fiscal_quarter_label", "nvarchar(12)", sort_by="fiscal_quarter_sort", desc="e.g. FY2025 Q1"), C("fiscal_quarter_sort", INT, hidden=True),
    C("fiscal_month_number", INT, desc="1 = first month of the fiscal year"),
    C("day_type", "nvarchar(7)", desc="Weekday / Weekend"), C("is_month_end", INT, hidden=True, desc="1 on the last day of a month"),
    C("month_start_date", DATE, hidden=True), C("month_end_date", DATE, hidden=True)], grain="one row per calendar day", nk=["date_key"]),
 Table("dim_territory", "Territory", "dim", "Sales territory = the 'region' that row-level security is keyed on.", [
    C("territory_key", INT, hidden=True, identity=True, pk=True, nullable=False), C("territory_id", INT, hidden=True, nullable=False, desc="Source SalesTerritory.TerritoryID"),
    C("territory_name", "nvarchar(50)", "Territory", nullable=False), C("country_region_code", "nvarchar(3)", "Country Code"),
    C("country_region_name", "nvarchar(50)", "Country"), C("territory_group", "nvarchar(50)", "Territory Group")],
    grain="one row per sales territory (+ Unassigned)", nk=["territory_id"],
    unknown=dict(territory_id=-1, territory_name="'Unassigned'", country_region_code="'--'", country_region_name="'Unassigned'", territory_group="'Unassigned'")),
 Table("dim_product", "Product", "dim", "Product with subcategory, category and model (SCD type 1).", [
    C("product_key", INT, hidden=True, identity=True, pk=True, nullable=False), C("product_id", INT, hidden=True, nullable=False),
    C("product_number", "nvarchar(25)"), C("product_name", "nvarchar(50)", "Product"), C("product_model", "nvarchar(50)"),
    C("product_subcategory", "nvarchar(50)"), C("product_category", "nvarchar(50)"), C("color", "nvarchar(15)"), C("size", "nvarchar(5)"),
    C("weight", "decimal(8,2)"), C("product_line", "nvarchar(20)"), C("product_class", "nvarchar(20)"), C("product_style", "nvarchar(20)"),
    C("make_or_buy", "nvarchar(10)"), C("product_type", "nvarchar(25)", desc="Finished good vs component / material"),
    C("standard_cost", M19, fmt="\\$#,0.00", desc="Current standard cost (Product.StandardCost)"), C("list_price", M19, fmt="\\$#,0.00"),
    C("safety_stock_level", INT), C("reorder_point", INT), C("days_to_manufacture", INT),
    C("sell_start_date", DATE), C("sell_end_date", DATE), C("lifecycle_status", "nvarchar(15)")],
    grain="one row per product", nk=["product_id"],
    unknown=dict(product_id=-1, product_number="'N/A'", product_name="'Unknown product'", product_model="'N/A'", product_subcategory="'Unknown'",
                 product_category="'Unknown'", color="'N/A'", size="'N/A'", product_line="'N/A'", product_class="'N/A'", product_style="'N/A'",
                 make_or_buy="'N/A'", product_type="'N/A'", standard_cost=0, list_price=0, safety_stock_level=0, reorder_point=0, days_to_manufacture=0, lifecycle_status="'N/A'")),
 Table("dim_customer", "Customer", "dim", "Customer (individual or reseller store).", [
    C("customer_key", INT, hidden=True, identity=True, pk=True, nullable=False), C("customer_id", INT, hidden=True, nullable=False),
    C("customer_type", "nvarchar(12)"), C("customer_name", "nvarchar(120)", "Customer")],
    grain="one row per customer", nk=["customer_id"], unknown=dict(customer_id=-1, customer_type="'Unknown'", customer_name="'Unknown customer'")),
 Table("dim_salesperson", "Salesperson", "dim", "Sales representatives; -1 = online orders (no salesperson).", [
    C("salesperson_key", INT, hidden=True, identity=True, pk=True, nullable=False), C("business_entity_id", INT, hidden=True, nullable=False),
    C("salesperson_name", "nvarchar(120)", "Salesperson"), C("job_title", "nvarchar(50)"), C("territory_name", "nvarchar(50)", "Home Territory"),
    C("quota_status", "nvarchar(15)", desc="Quota-carrying if the rep has quota history")],
    grain="one row per salesperson (+ online)", nk=["business_entity_id"],
    unknown=dict(business_entity_id=-1, salesperson_name="'Online / no salesperson'", job_title="'N/A'", territory_name="'N/A'", quota_status="'No quota'")),
 Table("dim_employee", "Employee", "dim", "Employees. Data-minimised: no national ID, birth date, gender or pay rate is loaded.", [
    C("employee_key", INT, hidden=True, identity=True, pk=True, nullable=False), C("business_entity_id", INT, hidden=True, nullable=False),
    C("employee_name", "nvarchar(120)", "Employee"), C("job_title", "nvarchar(50)"), C("hire_date", DATE),
    C("salaried_status", "nvarchar(10)"), C("current_status", "nvarchar(10)"),
    C("territory_key", INT, hidden=True, model=False, fk="dim_territory.territory_key", desc="Region of the employee's home address (physical FK only)")],
    grain="one row per employee", nk=["business_entity_id"],
    unknown=dict(business_entity_id=-1, employee_name="'Unknown'", job_title="'N/A'", hire_date="'1900-01-01'", salaried_status="'N/A'", current_status="'N/A'", territory_key=-1)),
 Table("dim_department", "Department", "dim", "HR departments.", [
    C("department_key", INT, hidden=True, identity=True, pk=True, nullable=False), C("department_id", INT, hidden=True, nullable=False),
    C("department_name", "nvarchar(50)", "Department"), C("department_group", "nvarchar(50)")],
    grain="one row per department", nk=["department_id"], unknown=dict(department_id=-1, department_name="'Unknown'", department_group="'Unknown'")),
 Table("dim_vendor", "Vendor", "dim", "Suppliers; region = territory of the vendor's main-office address.", [
    C("vendor_key", INT, hidden=True, identity=True, pk=True, nullable=False), C("vendor_id", INT, hidden=True, nullable=False),
    C("vendor_name", "nvarchar(50)", "Vendor"), C("account_number", "nvarchar(15)"), C("credit_rating", INT, hidden=True),
    C("credit_rating_label", "nvarchar(20)", sort_by="credit_rating"), C("preferred_status", "nvarchar(10)"), C("active_status", "nvarchar(10)"),
    C("territory_key", INT, hidden=True, model=False, fk="dim_territory.territory_key", desc="Vendor region (physical FK only)")],
    grain="one row per vendor", nk=["vendor_id"],
    unknown=dict(vendor_id=-1, vendor_name="'Unknown vendor'", account_number="'N/A'", credit_rating=0, credit_rating_label="'N/A'", preferred_status="'N/A'", active_status="'N/A'", territory_key=-1)),
 Table("dim_special_offer", "Special Offer", "dim", "Sales promotions.", [
    C("special_offer_key", INT, hidden=True, identity=True, pk=True, nullable=False), C("special_offer_id", INT, hidden=True, nullable=False),
    C("offer_description", "nvarchar(255)", "Special Offer"), C("discount_pct", "decimal(9,4)", "Discount %", fmt="0%"), C("offer_type", "nvarchar(50)"),
    C("offer_category", "nvarchar(50)"), C("start_date", DATE), C("end_date", DATE), C("min_qty", INT), C("max_qty", INT)],
    grain="one row per special offer", nk=["special_offer_id"],
    unknown=dict(special_offer_id=-1, offer_description="'Unknown'", discount_pct=0, offer_type="'N/A'", offer_category="'N/A'")),
 Table("dim_ship_method", "Ship Method", "dim", "Shipping methods (sales and purchasing).", [
    C("ship_method_key", INT, hidden=True, identity=True, pk=True, nullable=False), C("ship_method_id", INT, hidden=True, nullable=False),
    C("ship_method_name", "nvarchar(50)", "Ship Method")],
    grain="one row per ship method", nk=["ship_method_id"], unknown=dict(ship_method_id=-1, ship_method_name="'Unknown'")),
 Table("dim_location", "Location", "dim", "Inventory locations (production areas).", [
    C("location_key", INT, hidden=True, identity=True, pk=True, nullable=False), C("location_id", INT, hidden=True, nullable=False),
    C("location_name", "nvarchar(50)", "Location"), C("cost_rate", "decimal(9,4)"), C("availability", "decimal(8,2)")],
    grain="one row per location", nk=["location_id"], unknown=dict(location_id=-1, location_name="'Unknown'", cost_rate=0, availability=0)),
]

D = lambda k, a=True: dict(fk=f"dim_date.date_key", active=a, hidden=True)
def dim(t, a=True): return dict(fk=f"{t}.{t.replace('dim_','')}_key", active=a, hidden=True)
S = dict(hidden=True)  # numeric fact columns are hidden; measures are the user-facing layer

FACTS = [
 Table("fact_sales_line", "Sales", "fact", "Sales order line (Sales.SalesOrderDetail) with cost and header-level freight/tax allocated by revenue share.", [
    C("sales_order_id", INT, hidden=True, nullable=False, pk=True), C("sales_order_detail_id", INT, hidden=True, nullable=False, pk=True),
    C("sales_order_number", "nvarchar(25)", "Sales Order Number"),
    C("order_date_key", INT, nullable=False, **D("")), C("ship_date_key", INT, **D("", False)), C("due_date_key", INT, **D("", False)),
    C("customer_key", INT, nullable=False, **dim("dim_customer")), C("product_key", INT, nullable=False, **dim("dim_product")),
    C("territory_key", INT, nullable=False, **dim("dim_territory")), C("salesperson_key", INT, nullable=False, **dim("dim_salesperson")),
    C("special_offer_key", INT, nullable=False, **dim("dim_special_offer")), C("ship_method_key", INT, nullable=False, **dim("dim_ship_method")),
    C("order_channel", "nvarchar(10)"), C("order_status", "nvarchar(20)"),
    C("order_quantity", INT, **S), C("unit_price", M19, **S), C("unit_price_discount_pct", "decimal(9,4)", **S),
    C("gross_sales_amount", M196, **S), C("discount_amount", M196, **S), C("net_sales_amount", M196, **S),
    C("standard_cost_amount", M196, **S), C("gross_margin_amount", M196, **S),
    C("allocated_freight_amount", M196, **S), C("allocated_tax_amount", M196, **S)],
    grain="one row per sales order line", nk=["sales_order_id", "sales_order_detail_id"]),
 Table("fact_sales_quota", "Quota", "fact", "Sales quota per salesperson per month (quarterly quota spread evenly over the quarter's 3 months).", [
    C("quota_month_key", INT, nullable=False, pk=True, **D("")), C("salesperson_key", INT, nullable=False, pk=True, **dim("dim_salesperson")),
    C("territory_key", INT, nullable=False, **dim("dim_territory")), C("quota_amount", M196, **S)],
    grain="one row per salesperson per month", nk=["quota_month_key", "salesperson_key"]),
 Table("fact_purchase_line", "Purchases", "fact", "Purchase order line with delivery performance; region = vendor region.", [
    C("purchase_order_id", INT, hidden=True, nullable=False, pk=True), C("purchase_order_detail_id", INT, hidden=True, nullable=False, pk=True),
    C("order_date_key", INT, nullable=False, **D("")), C("ship_date_key", INT, **D("", False)), C("due_date_key", INT, **D("", False)),
    C("vendor_key", INT, nullable=False, **dim("dim_vendor")), C("product_key", INT, nullable=False, **dim("dim_product")),
    C("ship_method_key", INT, nullable=False, **dim("dim_ship_method")), C("territory_key", INT, nullable=False, **dim("dim_territory")),
    C("order_status", "nvarchar(20)"),
    C("order_quantity", INT, **S), C("received_quantity", "decimal(9,2)", **S), C("rejected_quantity", "decimal(9,2)", **S), C("stocked_quantity", "decimal(9,2)", **S),
    C("unit_price", M19, **S), C("line_total_amount", M196, **S), C("allocated_freight_amount", M196, **S), C("allocated_tax_amount", M196, **S),
    C("shipped_flag", INT, **S), C("on_time_flag", INT, **S, desc="1 if shipped on or before the line due date"), C("days_late", INT, **S)],
    grain="one row per purchase order line", nk=["purchase_order_id", "purchase_order_detail_id"]),
 Table("fact_inventory", "Inventory", "fact", "Current on-hand inventory snapshot per product and location (AdventureWorks has no inventory history). Company-wide, not regional.", [
    C("product_key", INT, nullable=False, pk=True, **dim("dim_product")), C("location_key", INT, nullable=False, pk=True, **dim("dim_location")),
    C("quantity", INT, **S), C("inventory_value_amount", M19, **S)],
    grain="one row per product per location", nk=["product_key", "location_key"]),
 Table("fact_headcount_monthly", "Headcount", "fact", "Month-end employee snapshot (department as of month end). No pay data.", [
    C("month_end_date_key", INT, nullable=False, pk=True, **D("")), C("employee_key", INT, nullable=False, pk=True, **dim("dim_employee")),
    C("department_key", INT, nullable=False, **dim("dim_department")), C("territory_key", INT, nullable=False, **dim("dim_territory")),
    C("headcount_flag", INT, **S), C("new_hire_flag", INT, **S), C("tenure_months", INT, **S)],
    grain="one row per employee per month-end", nk=["month_end_date_key", "employee_key"]),
 Table("fact_payroll_monthly", "Payroll", "fact", "Estimated payroll cost aggregated to department x region x month (rate x 173.33 h). Aggregated so individual pay is not exposed.", [
    C("month_end_date_key", INT, nullable=False, pk=True, **D("")), C("department_key", INT, nullable=False, pk=True, **dim("dim_department")),
    C("territory_key", INT, nullable=False, pk=True, **dim("dim_territory")), C("employee_count", INT, **S), C("estimated_payroll_cost", M19, **S)],
    grain="one row per department x territory x month-end", nk=["month_end_date_key", "department_key", "territory_key"]),
]
# date FK convention: fk target of D() is dim_date.date_key
for t in FACTS:
    for c in t.cols:
        if c.fk == "dim_date.date_key" or c.fk == "":
            c.fk = "dim_date.date_key"

# role names for inactive/role-playing date relationships
ROLE = {"ship_date_key": "Ship Date", "due_date_key": "Due Date", "order_date_key": "Order Date",
        "quota_month_key": "Quota Month", "month_end_date_key": "Month End"}

SEC = Table("sec_user_territory", "Region Access", "sec", "Row-level-security map: which users may see which territory (Region Manager role).", [
    C("user_email", "nvarchar(256)", "User Email", nullable=False), C("territory_key", INT, hidden=True, nullable=False)],
    grain="one row per user per territory", view=False)

ALL = DIMS + FACTS
BY_NAME = {t.name: t for t in ALL}

def relationships():
    """(from_model_table, from_col_display, to_model_table, to_col_display, active, name)"""
    out = []
    for f in FACTS:
        for c in f.cols:
            if c.fk and c.model:
                d = BY_NAME[c.fk.split(".")[0]]
                dc = d.col(c.fk.split(".")[1])
                out.append((f, c, d, dc, c.active))
    return out

if __name__ == "__main__":
    print(len(DIMS), "dims", len(FACTS), "facts", sum(len(t.cols) for t in ALL), "columns", len(relationships()), "relationships")
