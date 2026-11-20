# 10-minute final presentation - script and slide plan

Eight slides, ≈75 seconds each; the live demo replaces slides 5-6 if you prefer (then budget 3 min for the demo and cut slide 7 to 30 s). **Replace every `⟦…⟧` with your own measured value** - do not present a number you have not measured.

| # | Slide | Time | Say / show |
|---|---|---|---|
| 1 | **Problem** | 0:45 | A multi-region company has sales, finance, HR and supply-chain data in separate systems; managers wait days for numbers and everyone sees everything or nothing. Goal: one governed report, each region manager sees only their region, refreshed nightly. |
| 2 | **Architecture** | 1:15 | Show `docs/assets/architecture.png`. Source → ADF (or SQL Agent fallback) → `stg` → star schema → DQ gate → `rpt` views → Power BI model (DAX + RLS) → Service. Mention: logic in tested SQL, shaping in Power Query, one KPI definition in DAX. |
| 3 | **Data design** | 1:15 | Show `docs/assets/erd.svg`: 11 dimensions, 6 facts, conformed Date; region copied into every fact so one RLS rule secures everything; privacy by design (no pay rates, IDs, birth dates). Say which decisions you owned. |
| 4 | **Pipeline & quality** | 1:15 | Metadata-driven ADF: add a table = add a row; full + watermark upsert; idempotent atomic loads; **52 automated checks gate every run** (grain, orphan keys, reconciliation to source). Show an `etl.dq_result` screenshot. |
| 5 | **DAX & report** *(demo)* | 1:45 | Executive Overview → YoY, rolling 3M, margin %, quota attainment, semi-additive headcount. Show one non-trivial measure (`Net Sales Rolling 3M Avg`: why Month Index instead of DATESINPERIOD). Drill through Product Detail. |
| 6 | **Security** *(demo)* | 1:00 | *View as* Northwest manager (1 territory) vs Europe director (3) vs Global Executive; unmapped user sees nothing. |
| 7 | **Results** | 1:15 | Accuracy: all 49 KPI baselines match an independent calculation ⟦your SQL Server result: __/49⟧; DAX tests ⟦__/55⟧; reconciliation to source ⟦ties to $0.00⟧. Performance: ETL ⟦__ s⟧, dataset refresh ⟦__ s⟧, slowest page ⟦__ s⟧ (Performance analyzer). Headline numbers from the sample: net sales $109.8M, gross margin 11.4%, FY2025 YoY +28.6%. |
| 8 | **Challenges & next steps** | 1:00 | Challenges (pick yours): no GL in AdventureWorks → derived finance; HR/purchasing have no region → derived; DATESINPERIOD end-of-month quirk; making RLS deny-by-default; first-time ADF upsert keys. Next: SCD2, incremental fact loads, calculation groups, incremental refresh, Fabric Lakehouse/Direct Lake, alerts via Data Activator. |

**Likely questions (prepare answers):** Why Import and not DirectQuery? · Why derive logic in SQL, not Power Query? · How do you know the numbers are right? (baselines + reconciliation) · What happens if a manager is missing from the map? · How would this scale to 100× data? (columnstore, incremental loads, incremental refresh, partitioning) · What did *you* build vs generate/reuse?
