# Test results and accuracy numbers

_Generated 2026-11-08T10:37:09 on target **duckdb** by `python -m customer360 evaluate`._

## 1. dbt build

- models built: **25**, seeds: 1
- data tests: **80 passed**, 0 warnings, 0 failures
- dbt unit tests: **3 passed**, 0 failures

## 2. Reconciliation: tracking vs CRM (system of record)

| check | result |
|---|---|
| online CRM orders in window found in GA4 / Segment | 2,123 of 2,213 = **95.9%** |
| web orders found in GA4 | 95.1% |
| matched orders with exactly equal revenue | 97.4% (mean abs gap $0.14) |
| double-fired GA4 purchase events removed | 25 of 1,762 |
| revenue attributed to a real channel (rest = Unattributed) | 95.0% |

## 3. SQL vs Python parity (attribution)

Independent pandas re-implementation vs the dbt models over 44 (model x channel) cells: max revenue difference **$0.0005**, max order difference 1e-05.

## 4. Identity resolution vs simulator ground truth

Pairwise precision / recall over 12,592 sessions of CRM customers; 93.8% of those sessions were linked to a person.

| approach | precision | recall | F1 | wrongly merged people | CRM duplicates found |
|---|---|---|---|---|---|
| **guarded graph (this project)** | 0.973 | 0.952 | 0.962 | 2 | 100% of 76 |
| naive connected components | 0.966 | 0.956 | 0.961 | 53 | 100% |

- shared devices (two people, one browser): 51 of 53 detected, precision 1.00
- channel classification (dbt macro vs what was actually sent): **100.0%**; session keys reproducible from source data: 100.0%

## 5. Attribution models vs simulated ground truth

1,945 orders. TVD = total-variation distance between the model's revenue shares and the true shares (0 = perfect). A uniform guess scores 0.358.

| model | channel TVD | campaign TVD | campaign-ROAS rank correlation (Spearman) | top-3 campaigns found |
|---|---|---|---|---|
| first touch | 0.129 | 0.148 | 0.74 | 2 of 3 |
| last touch | 0.118 | 0.264 | 0.29 | 1 of 3 |
| linear | 0.053 | 0.103 | 0.87 | 2 of 3 |
| time decay | 0.060 | 0.121 | 0.72 | 2 of 3 |

Effect of the Direct-traffic policy (channel TVD, deprioritise -> include): first touch 0.129 -> 0.111, last touch 0.118 -> 0.141, linear 0.053 -> 0.061, time decay 0.060 -> 0.062

## 6. Response-curve (elasticity) recovery

Estimated spend elasticity vs the true value used to simulate costs: mean absolute error **0.143**, max 0.287; 6 of 11 campaigns within +/-0.15.

## 7. CLV back-test (BG/NBD x Gamma-Gamma)

Calibrated on orders to 2020-10-31, forecast the next 92 days for 1,178 customers.

| metric | value |
|---|---|
| repeat orders predicted vs actual | 417 vs 452 (-7.7%) |
| per-customer MAE: model vs naive run-rate | 0.495 vs 0.562 (11.9% better) |
| correlation predicted vs actual | 0.36 |
| order-value MAPE: Gamma-Gamma vs population mean | 54.9% vs 57.5% |

## 8. Budget recommendation

Budget moved: $1,758 (6.1% of $28,787); projected attributed-revenue change by model: first touch +2.9%, last touch +2.0%, linear +2.6%, time decay +2.6%.

## 9. Performance (single CPU)

| step | seconds |
|---|---|
| generate | 31.7 |
| dbt_seed | 9.5 |
| dbt_stage1_staging_and_identity_edges | 7.4 |
| python_identity_resolution | 1.2 |
| python_clv_bgnbd | 1.9 |
| dbt_stage2_marts_and_tests | 9.3 |
| python_budget_recommendation | 3.5 |
| python_evaluate | 2.0 |
| python_report | 3.7 |
| python_export_tableau | 0.8 |
| total | 71.0 |

## 10. Data volumes (local demo)

| table | rows |
|---|---|
| persons | 6,000 |
| crm_customers | 3,376 |
| crm_orders | 4,755 |
| orders_in_window | 2,237 |
| online_orders_in_window | 2,213 |
| online_orders_tracked | 2,123 |
| sessions_web | 60,429 |
| sessions_app | 1,995 |
| ga4_events | 265,437 |
| segment_tracks | 8,774 |
| segment_identifies | 3,226 |
| paid_spend | 28787.03 |
| online_net_revenue | 97875.9 |
| ga4_events_loaded | 265,437 |
