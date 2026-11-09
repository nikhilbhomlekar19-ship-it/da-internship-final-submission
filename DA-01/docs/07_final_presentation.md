# Final presentation - 10 minutes (+ 3 minutes Q&A)

Structure: **problem -> design -> challenges -> results -> next steps.**  Every number below comes from the reference run in this repo
(`reports/metrics.json`, `reports/findings.md`); re-run `make demo` and update them if your data differs.
Suggested split for a team of four: one presenter per block (slides 1-3, 4-5, 6-8, 9-10); the person who owned a component answers its questions.

| # | Time | Slide | Visual |
|---|---|---|---|
| 1 | 0:00-0:45 | The problem | one-line problem + 3 pain points |
| 2 | 0:45-1:45 | Solution and architecture | `docs/diagrams/architecture.png` |
| 3 | 1:45-3:00 | One customer, many devices (identity) | identity graph sketch + 3 numbers |
| 4 | 3:00-4:00 | Modelling and trust (dbt) | lineage screenshot (`make docs`) + test counts |
| 5 | 4:00-5:00 | Who are our customers? (RFM / CLV) | `04_rfm_segments.png`, `05_clv_backtest.png` |
| 6 | 5:00-6:30 | Four attribution models, four stories | `01_attribution_model_comparison.png`, `06_attribution_vs_truth.png` |
| 7 | 6:30-7:30 | What did each campaign really return? | `02_campaign_roas_by_model.png` |
| 8 | 7:30-8:45 | Where to move the budget | `03_budget_recommendation.png` (or Tableau Dashboard 5) |
| 9 | 8:45-9:30 | Challenges and lessons | 4 short stories |
| 10 | 9:30-10:00 | Next steps and the ask | 3 bullets |

---

## Slide 1 - The problem (0:00-0:45)
**Title:** *"We spend $28.8 k on ads. Which channel actually earns the revenue?"*
* Customer data lives in four places: website (GA4), app (Segment), CRM, ad platforms. Nobody can follow one person across them.
* Each ad platform says it drove the sale: **platform-reported ROAS is a median 2.9x** what a neutral model gives.
* Budget decisions on last-click are biased: last click credits whoever *closes*, not whoever *started* the journey.
* *Say once:* GA4 is the real public sample on BigQuery; CRM, Segment and ad spend are synthetic (generated with Faker/numpy) so we can also measure accuracy.

## Slide 2 - Solution and architecture (0:45-1:45)
Show the architecture diagram, walk left to right: **sources -> BigQuery -> dbt + Python -> Tableau**.
* dbt does the modelling (25 models, 83 tests); Python does what SQL is bad at (identity graph, CLV maths, optimisation).
* One dbt project runs on **BigQuery and DuckDB** (adapter macros) - that is how we test everything for free and in CI.
* Execution order is the one non-obvious design point: dbt staging -> Python identity -> Python CLV -> dbt marts -> Python budget plan.

## Slide 3 - One customer, many devices (1:45-3:00)
* A person has a laptop cookie, a phone browser and an app install. We link them with **deterministic evidence**: `identify()` calls (Segment) that also carry the GA4 client id, order matches (GA4 `transaction_id` = CRM order), CRM e-mail/phone (which also removes duplicate CRM records).
* The trap: **shared devices.** Naive connected components merge two people who used one laptop. Our guard links a device to a person only if it points to exactly one person.
* Numbers (measured against simulated ground truth): pairwise **precision 0.973 / recall 0.952**; **2 wrongly merged people vs 53** for the naive method; all **76 CRM duplicates merged**; **51 of 53** shared devices detected; 93.8 % of customers' sessions linked.

## Slide 4 - Modelling and trust (3:00-4:00)
* Sessions: GA4 `ga_session_id` for the web, a 30-minute rule for the app (Segment has no sessions). Orders: **CRM is the system of record**, reconciled with tracking.
* **95.9 %** of online CRM orders are found in tracking, **97.4 %** with exactly the same revenue; 25 double-fired GA4 purchase events removed.
* Quality gates: **80 dbt data tests, 3 dbt unit tests, 33 pytest tests**, SQL-vs-Python parity check ($0.0005), every compiled model parsed with the BigQuery dialect.
* Pipeline: about a minute, one command (`make demo`).

## Slide 5 - Who are our customers? (4:00-5:00)
* RFM grid -> 10 segments. 33 % of customers are *Hibernating* (one old order) but 24 % of revenue; **Champions + Loyal = 5.7 % of customers, 19.5 % of revenue**.
* CLV with BG/NBD x Gamma-Gamma: calibrated on history, **forecast the 92-day holdout: 417 repeat orders predicted vs 452 actual (-7.7 %)**, per-customer error 12 % better than a run-rate baseline.
* Action: **140 Platinum/Gold customers are At Risk or Churned - $31 k of historical revenue** -> win-back list for CRM (Tableau Dashboard 4).

## Slide 6 - Four attribution models, four stories (5:00-6:30)
* Same orders, same revenue, four models (first / last / linear / time-decay, 30-day lookback, Direct deprioritised).
* **Paid Search: 28.7 % of revenue under first touch, 39.9 % under last touch.** Email, Affiliate gain under last touch; Paid Social, Organic Search lose.
* Which one is right? Ground truth (simulation): **linear is closest** (channel-credit error 0.053; time-decay 0.060; first 0.129; last 0.118; a uniform guess 0.358) and **last-touch ranks campaigns almost at random (Spearman 0.29 vs 0.87 for linear)**.
* *Caveat to say out loud:* the truth is a simulation assumption; it shows why last-click misleads, not that linear wins on every real business.

## Slide 7 - What did each campaign return? (6:30-7:30)
* ROAS, ROI, CPA, CAC, LTV:CAC for every campaign and model. **Break-even ROAS on gross profit = 2.22** (45 % margin).
* **Meta prospecting is 20 % of spend (the biggest line) and sits below break-even in every model (ROAS 0.45-2.08)**; display prospecting is the weakest (0.29-1.80, CAC $73, LTV:CAC 0.96).
* Brand search, Bing brand, retargeting and coupon sites look great under last click (ROAS 3.6-7.0) - but they are *closers*; they harvest demand others created.
* Platforms claim 3.9-13.8x ROAS for the same campaigns.

## Slide 8 - Where to move the budget (7:30-8:45)
* Method in one sentence: fit a response curve per campaign and model, re-allocate the same budget to equalise marginal ROAS, **but only trust moves all models agree on**.
* **Robust moves (3):** scale *generic search* +35 % (ROAS 3.3, all models agree), *content-partner affiliates* +35 %, *Bing brand* +35 % (tiny, $0.6 k, borderline). Total moved: **$1.8 k = 6.1 % of budget -> +2.0 % to +2.9 % attributed revenue** depending on the model (worst case still positive).
* **Test first (7 campaigns):** last-touch ROAS is >2x or <0.5x first-touch ROAS, so attribution alone cannot decide. *Closers* (brand search, retargeting, remarketing, coupon sites): geo/holdout "pause" test. *Introducers* (TikTok, Meta prospecting, display prospecting): do **not** cut on last-click; run a geo-lift test.
* This is the honest answer: attribution tells you who gets credit, not what is incremental.

## Slide 9 - Challenges and lessons (8:45-9:30) - pick the 3 you owned
1. **A model that would not fit.** Our CLV model recovered r = 0.47 instead of 0.9. The likelihood was right - our *simulator* let customers churn before their first repeat purchase, which BG/NBD forbids. Fixing the generator (not the model) recovered the parameters. Lesson: when the model and the data disagree, check the data-generating story first.
2. **Identity at the edges.** Naive merging created 53 false customers; a shared-device guard cut it to 2. The remaining 2 are Gmail namesakes (dots are ignored by Gmail) - a documented trade-off.
3. **One project, two warehouses.** GA4's nested `UNNEST` vs DuckDB lists, timestamps, regex: solved with `adapter.dispatch` macros; found a rounding difference (`epoch` rounds in DuckDB, floors in BigQuery) because session keys did not match ground truth.
4. **Noisy response curves.** ~80 daily points per campaign -> wide uncertainty; used Poisson fitting, bootstrap standard errors and shrinkage instead of trusting raw slopes (elasticity error 0.14 on average).
5. **dbt <-> Python ordering.** The Python outputs are dbt sources; we use graph selectors (`+int_identity_edges`) to run the pipeline in the right order.

## Slide 10 - Next steps and the ask (9:30-10:00)
* Replace synthetic CRM/Segment/ads with real feeds; run the **geo-holdout tests** for the 7 flagged campaigns; add data-driven (Markov/Shapley) attribution and a small media-mix model as a cross-check.
* Productionise: incremental models for the full GA4 export, orchestration (Dagster/Airflow), CI is already in place.
* **Ask:** approve a 4-week incrementality test plan before any large budget move.

---

## Demo recording plan (3 minutes, screen + voice)
Record at 1080p; terminal font 18 pt; have the venv active and `data/` empty (or run on `app/demo.duckdb`).

| Time | Show | Say |
|---|---|---|
| 0:00 | terminal: `make demo` (speed up the middle) | "one command builds everything in about a minute: 25 models, 83 tests" |
| 0:30 | `reports/test_results.md` | "accuracy numbers: identity, attribution, CLV, reconciliation" |
| 0:50 | `streamlit run app/streamlit_app.py` -> *Attribution models* | "the same revenue under four models" |
| 1:20 | *Campaign ROI* -> switch model first <-> last touch | "watch the ranking reverse; the dotted line is break-even ROAS" |
| 1:50 | *Budget recommendation* | "three robust moves, seven campaigns that need a test" |
| 2:15 | *Customer 360* -> pick a top customer | "sessions across web and app stitched to one person, orders, CLV" |
| 2:45 | Tableau dashboards (or the figures) | "same marts feed Tableau" |

Deploy option: push to GitHub and deploy `app/streamlit_app.py` on Streamlit Community Cloud (it uses the 12 MB `app/demo.duckdb`, so no pipeline is needed).

## Likely questions - short answers
* **How do you know identities are right?** Simulator ground truth: pairwise precision/recall, wrongly merged people, duplicates found - and a naive baseline to compare.
* **Why Python for identity?** Connected components with guard rules are clearer and testable in Python; the evidence stays in SQL and is auditable.
* **Why is linear closest to the truth?** In *our* simulation credit is spread over several recency-weighted touches with an introducer bonus; linear/time-decay approximate that, first/last are extremes. On real data you must validate with experiments.
* **What is incrementality and why does it matter?** The revenue that would **not** have happened without the ad. Attribution assigns credit; only experiments (holdouts, geo-lift) measure incrementality. Brand search and retargeting are the usual victims of this confusion.
* **Why not cut Meta prospecting if ROAS < break-even?** It is an introducer: last-click undervalues it (ROAS 0.45 vs 2.08 first-touch). We recommend a geo-lift test, not a blind cut.
* **How reliable is the budget plan?** Moves are budget-neutral, limited to +/-35 % (+/-10 % when models disagree) and reported per model with the worst case; response-curve estimates are shrunk to a prior because the data are noisy.
* **Does it run on BigQuery?** Same models; SQL syntax is validated offline for the BigQuery dialect and the guide covers setup. The environment used to build this had no BigQuery credentials, so first-run fixes are possible.
