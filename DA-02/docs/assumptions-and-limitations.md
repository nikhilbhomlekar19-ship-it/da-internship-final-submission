# Assumptions and limitations (honest list)

## About the data (AdventureWorks is a sample, not a company)
1. **No general ledger.** "Finance" is derived: net sales, COGS (quantity × standard cost valid on the order date; 64 of 121,317 lines have no cost-history row and fall back to the current standard cost - reported by a WARN check), freight and tax billed, purchase spend, estimated payroll. Gross margin is **11.4%**, which is what the sample produces.
2. **Dates are shifted** (sales 2022-05-30 → 2025-06-29; purchase orders run to 2025-09-21; hires 2006-2013). The calendar spans 2006-01-01 → 2025-10-31. Calendar year 2025 is partial: compare **fiscal years** (FY2023-FY2025 are complete) or months.
3. **HR has no terminations, no events after 2013** → headcount rises from 2006 to 290 and is flat afterwards; "new hires" are zero in the sales window. Payroll is an **estimate** (rate × 173.33 h, no benefits/overtime, rates frozen after their last change).
4. **Region is derived**, not native, for HR (home-address territory: 277 of 290 employees are in Northwest) and purchasing (vendor main-office territory; vendors exist only in Northwest, Southwest, Central, Northeast, Southeast). Managers of Canada/Europe/Australia legitimately see no supply-chain or HR data.
5. **Inventory** is one undated snapshot, company-wide; it cannot be trended or region-secured.
6. **Quota** is quarterly per salesperson; it is spread evenly over the quarter's 3 months. Attainment compares sales of quota-carrying reps only. The first quarter (Apr-Jun 2022) contains only one month of sales (data starts 30 May 2022) so its attainment is distorted.
7. Purchase **on-time %** (99.9%) is high because the sample ship dates almost never exceed the due dates - the KPI works, the data is just benign.

## About the build
8. **Not executed on SQL Server / Power BI / ADF by the author.** Logic was verified in DuckDB on the real data; T-SQL syntax parsed; Power BI files validated against Microsoft's JSON schemas. Expect small first-run fixes (see [troubleshooting](troubleshooting.md)).
9. SCD type 1 only; facts are fully rebuilt each run (fine at 121k rows). Next steps: SCD2 for employee department/job title, incremental fact loads keyed on `etl.watermark`, columnstore indexes if volume grows, calculation groups for time intelligence, incremental refresh in Power BI.
10. Single currency (USD); `SalesOrderHeader.CurrencyRateID` is ignored.
11. The report uses default visuals (no custom visuals, no bookmarks/tooltips pages); the theme is a separate file you import.
12. RLS role *membership* and the app/audiences are Service-side steps; they cannot be stored in the repository.
