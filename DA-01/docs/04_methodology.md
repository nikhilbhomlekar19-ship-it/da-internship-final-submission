# Methodology

All formulas below are what the code does; file names point to the implementation.

## 1. Window, units, assumptions
* Tracking window **2020-11-01 .. 2021-01-31** (92 days) = the date range of the public GA4 sample; `as_of_date` (= window end) is "today" for recency and lifecycle.
* CRM order history starts 2019-11-01 (12 months before the window) so RFM/CLV have depth; only orders inside the window can be attributed.
* Currency USD; gross margin 45 % (`gross_margin_pct`) - break-even ROAS = 1 / 0.45 = 2.22.

## 2. Sessions
* **GA4 (web)**: `session_key = user_pseudo_id || '.' || ga_session_id`. Source / medium / campaign = first event in the session carrying the `source/medium/campaign` event params, else the user's first-touch `traffic_source`. Landing page = first `page_view`. (`int_ga4__sessions.sql`)
* **Segment (app)**: Segment has no sessions, so events are sessionised per `anonymous_id`: a new session starts after **30 minutes** of inactivity (`LAG` + cumulative sum). `session_key = anonymous_id || '.' || epoch(first event)`. Campaign context = first event with `context.campaign.*`; none = Direct. (`int_segment__sessions.sql`)
* **Channel** = simplified GA4 default channel grouping on (source, medium): Paid Search, Paid Social, Display, Affiliate, Email, App Push, Organic Search, Organic Social, Referral, Direct, Other (`c360_channel_group`). **campaign_key** = `lower(source)|lower(medium)|lower(campaign)` joins sessions to ad spend.

## 3. Identity resolution (`int_identity_edges.sql`, `identity.py`)
Nodes are typed identifiers: `crm:`, `email:`, `phone:` (person keys) and `ga:`, `sa:` (devices). E-mail normalisation: lower-case, trim, remove `+tag`, remove dots for Gmail, `googlemail.com` -> `gmail.com`; phone = last 10 digits.

| Edge class | Evidence | Rule |
|---|---|---|
| person | CRM record <-> normalised e-mail / phone | always merged -> **CRM de-duplication** |
| device_device | Segment `anonymous_id` <-> GA client id (identify trait) | always merged (same browser) |
| device_person | Segment `identify(user_id / email)`, GA4 `user_id`, **order match** (GA4 `transaction_id` or Segment `order_id` = CRM `external_ref`) | joins the device group to a person only if it points to **one** person |

Algorithm: (1) union-find over person edges -> persons; (2) union-find over device edges -> device groups; (3) accumulate weighted evidence per (device group, person): order match 3, identify(user) 2, identify(email) 1, GA4 user_id 1; (4) one candidate -> assign; several -> `is_shared_device`, assign to the highest evidence (ties: most recent), **never merge the people**; (5) `person_id = 'P' || md5(smallest crm node)[:12]`, stable across runs.
Sessions of unlinked devices stay `anon:<device>`.
Baseline for comparison: naive connected components over all edges (`identity_nodes_naive`).

## 4. Orders (`fct_orders.sql`)
* CRM orders are the system of record. `net_revenue = max(gross - discount - refund, 0)`.
* **Conversion** = `status = 'completed'` inside the tracking window. Returned / cancelled orders are kept (counted, reconciled) but carry no revenue credit.
* Tracking evidence is attached by `external_ref`: GA4 purchases (de-duplicated by `transaction_id`) for web, Segment `Order Completed` for app (mapped to the app session containing it).
* `is_first_order` = the person's first completed order ever (so only customers acquired in the window are "new").

## 5. RFM (`customer_rfm.sql`)
* R = days from last completed order to `as_of_date`; F = number of completed orders; M = net revenue.
* R and M scores 1-5 by `percent_rank` (`least(5, floor(pr*5)+1)`) - tied customers get the same score; F score = `min(orders, 5)` (a small integer with heavy ties would otherwise split identical customers).
* Segments = the standard R x F grid: Champions (R5 F4-5), Loyal (R3-4 F4-5), Potential Loyalists (R4-5 F2-3), New (R5 F1), Promising (R4 F1), Need Attention (R3 F3), About To Sleep (R3 F1-2), At Risk (R1-2 F3-4), Can't Lose Them (R1-2 F5), Hibernating (R1-2 F1-2).

## 6. Customer lifetime value (`clv.py`)
**BG/NBD** (Fader, Hardie, Lee 2005): each customer buys at rate lambda ~ Gamma(r, alpha) while alive; after each repeat purchase they drop out with probability p ~ Beta(a, b). Inputs per customer: x = repeat transactions, t_x = weeks first -> last purchase, T = weeks first purchase -> end of calibration. Parameters by maximum likelihood (L-BFGS-B on log-parameters).
* Forecast: `E[purchases in next t weeks | x, t_x, T]` (closed form with the Gauss hypergeometric function); `P(alive)`.
* **Gamma-Gamma** (Fader & Hardie 2013): order value; `E[M | x, mean] = w*population_mean + (1-w)*observed_mean` with `w = (q-1)/(p*x + q - 1)`; customers with no repeat purchase get the population mean.
* **12-month CLV** = `sum over months m=1..12 of (E[Y(m)] - E[Y(m-1)]) / (1+10%)^(m/12) x predicted order value`; profit CLV = revenue x margin.
* **Back-test**: calibrate on orders <= 2020-10-31, forecast the 92 days of the window, compare with what happened and with a naive run-rate baseline (`frequency / T x horizon`). The test suite also recovers known parameters on data simulated from the BG/NBD generative story.
* Segmentation: `clv_tier` from the percentile of `historical + predicted` revenue among buyers (Platinum >= 95th, Gold >= 80th, Silver >= 50th, Bronze); `lifecycle_stage`: Prospect (no orders), New (first order <= 30 days), Active (recency <= 90 d and P(alive) >= 0.5), At Risk (<= 180 d and P(alive) >= 0.25), Churned.

## 7. Attribution (`int_attribution__paths.sql`)
For every conversion O at time t_O of person P: touchpoints = all sessions of P (web + app, any device linked to P) with `t_O - 30 days <= start <= t_O`.
`Direct` sessions are dropped when the path has any other channel (`direct_policy = deprioritize`; `include` keeps them). With n eligible touches ordered by time, position k = 1..n, h_k = hours before the order:

| Model | credit of touch k |
|---|---|
| first touch | 1 if k = 1 |
| last touch | 1 if k = n |
| linear | 1 / n |
| time decay | `0.5^(h_k / (7*24)) / sum_j 0.5^(h_j / (7*24))` (half-life 7 days) |

Orders with no eligible touch get 100 % on the pseudo-channel `Unattributed`, so credits always sum to 1 per order and credited revenue reconciles to order revenue (enforced by two singular tests).
`credited_revenue = credit x net_revenue`. Paths are left-censored at the window start (earlier touches were not tracked).
`customer360/attribution.py` re-implements this in pandas; `evaluate` checks the two agree.

## 8. ROI metrics (`mart_campaign_roi.sql`, `mart_channel_roi.sql`)
```
ROAS            = attributed_revenue / spend
gross_profit    = attributed_revenue x margin
ROI             = (gross_profit - spend) / spend
CPA             = spend / attributed_orders
CAC             = spend / attributed_new_customers          (first completed orders, fractional credit)
LTV:CAC         = (sum of credit x 12-month CLV of newly acquired customers / attributed_new_customers) / CAC
platform ROAS   = platform_reported_conversion_value / spend; over-claim ratio = platform conversions / attributed orders
```
All metrics exist for each of the four models, so the spread between models is visible next to the platform's own claim.

## 9. Budget recommendation (`recommend.py`)
1. **Response curve** per (campaign, model): `revenue_d = k * spend_d^beta` on daily data, revenue dated by the touch. Quasi-Poisson likelihood (zero-revenue days allowed), 40 bootstrap resamples for the standard error; the last 14 days are excluded (their orders are not yet observed). Estimates are shrunk to a prior `beta0 = 0.65, sd 0.15` with precision weights, so noisy fits do not drive decisions. `beta < 1` = diminishing returns; marginal ROAS = `beta x ROAS`.
2. **Allocation**: maximise `mean over the 4 models of sum_c A_mc x_c^beta_mc` subject to `sum x = current total` and per-campaign bands (+/-35 %); solved by water-filling on the Lagrange multiplier (concave problem).
3. **Model-risk guard**: if `ROAS_last / ROAS_first > 2` (closer) or `< 0.5` (introducer) the campaign's band shrinks to +/-10 % and the action becomes *Test incrementality*.
4. Outputs per campaign: action, confidence, current/recommended spend, per-model "if you only trusted this model" spend, and projected revenue change per model (worst model reported).

## 10. Evaluation design (`evaluate.py`)
The simulator keeps the truth: person of every session, CRM duplicates, shared devices, the real channel of each session, the true incrementality weight of each campaign (`truth_w`) and the true spend elasticity of each paid campaign.

| Question | Metric |
|---|---|
| Are people stitched correctly? | pairwise precision/recall/F1 of "same person" over sessions of CRM customers; wrongly merged people; CRM duplicates found; shared devices flagged |
| Is the channel logic right? | dbt `channel_group` vs the channel really sent (accuracy) |
| Which attribution model is closest to the truth? | **truth credit** per order = `truth_w x exp(-hours/168) x (1.5 if first touch)` normalised over the touches the pipeline could see and that really belong to the buyer; compare revenue shares with total-variation distance (channel and campaign level) and campaign-ROAS rank correlation |
| Does SQL = Python? | max abs difference of the two attribution implementations |
| Is CLV calibrated? | holdout orders predicted vs actual, per-customer MAE vs naive, decile calibration |
| Are response curves right? | |estimated elasticity - true elasticity| |
| Do sources reconcile? | CRM orders found in GA4/Segment, exact revenue matches, duplicate purchase events |

**Caveat**: truth credit is a *simulation assumption* (U-shaped, recency-weighted, incrementality-weighted). It shows the machinery works and illustrates classic biases (last click over-credits closers); it does not prove linear attribution beats last click on your real data.

## 11. Known limitations
* Gmail-dot normalisation can merge namesakes (2 of 3,376 CRM records in the demo) - add a second matching attribute if that matters.
* A device is only linked once it identifies or buys; cookie resets and cross-device journeys without a login stay anonymous.
* BG/NBD assumes independent customers and no seasonality; Gamma-Gamma assumes spend is independent of frequency.
* Attribution cannot measure incrementality (brand search, retargeting, coupon sites look great in click-based models). Use geo/holdout tests for the flagged campaigns.
* Response curves from ~80 daily points per campaign are noisy; the shrinkage and the +/-35 % bands exist for that reason.
