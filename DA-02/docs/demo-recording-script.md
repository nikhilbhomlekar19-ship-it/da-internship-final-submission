# Demo recording script (6-8 minutes, screen + voice)

Tools: Power BI Service in a browser (or Desktop), OBS Studio or Xbox Game Bar (Win+G) / Teams "record". 1080p, mic check first, hide personal tabs/e-mail, zoom the browser to 110%.

| Min | Show | Say |
|---|---|---|
| 0:00 | Title + `docs/assets/architecture.png` | One sentence per layer. |
| 0:45 | SSMS/ADS: `SELECT TOP 5 * FROM etl.run_log`, `etl.dq_result` (all ERROR checks PASS; the one WARN lists the 64 fallback-cost lines), row counts | "Every night the pipeline loads 6 facts / 11 dims and 52 checks must pass." |
| 1:30 | ADF Monitor (or SQL Agent history): last successful `pl_master_daily` run, expand the ForEach | "Metadata-driven; incremental tables use a watermark." |
| 2:15 | Service → app → **Executive Overview**; change Fiscal Year to FY2025; hover the trend line | Read three KPIs aloud: Net Sales, YoY, Gross Margin %. |
| 3:30 | **Sales** → expand a category (+) → right-click a product → **Drill through → Product Detail** → back | "Same measures at every level." |
| 4:30 | **Finance**, **Supply Chain** (vendor table → Vendor Detail), **HR** (headcount trend) | One insight each (e.g. top vendor, rejected %, headcount by department). |
| 5:45 | Dataset → Security → **Test as role**: Northwest manager → show Territories Visible = 1; then Global Executive | "Same report, different rows - enforced in the model." |
| 6:45 | Dataset → Refresh history (03:00 daily), `tests/results` (55/55 DAX tests) | "Refreshed nightly; tests prove accuracy." |
| 7:30 | Close: what you owned, what's next | 20 seconds. |

Export as MP4, name `demo.mp4`, upload to OneDrive/YouTube (unlisted) and link it from the README.
