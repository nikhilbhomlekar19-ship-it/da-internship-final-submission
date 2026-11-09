# Tableau parameters and calculated fields (copy / paste)

Create these once on the data sources described in [`docs/05_tableau_guide.md`](../docs/05_tableau_guide.md).

## Parameters
| Name | Type | Values | Default |
|---|---|---|---|
| `Attribution Model` | String list | `first_touch`, `last_touch`, `linear`, `time_decay` (display: First touch / Last touch / Linear / Time decay) | `time_decay` |
| `Gross Margin` | Float | 0.45 | 0.45 |
| `Min Spend` | Float | 0 - 10000 | 0 |

## Calculated fields on `mart_campaign_roi` / `mart_channel_roi` (one row per model!)
These tables repeat each campaign/channel once per model. Always filter first: **Data source filter or context filter `Model Match = TRUE`** - otherwise spend is counted four times.
```
// Model Match
[model] = [Attribution Model]

// Model Label
CASE [model] WHEN 'first_touch' THEN 'First touch' WHEN 'last_touch' THEN 'Last touch'
             WHEN 'linear' THEN 'Linear' WHEN 'time_decay' THEN 'Time decay' END

// ROAS
SUM([attributed_revenue]) / SUM([spend])

// Break-even ROAS
1 / [Gross Margin]

// ROAS vs break-even   (use for colour: >0 green, <0 red)
[ROAS] - [Break-even ROAS]

// ROI %
(SUM([attributed_revenue]) * [Gross Margin] - SUM([spend])) / SUM([spend])

// CPA
SUM([spend]) / SUM([attributed_orders])

// CAC (new customer)
SUM([spend]) / SUM([attributed_new_customers])

// 12-month CLV of acquired customers
SUM([new_customer_clv_credit]) / SUM([attributed_new_customers])

// LTV:CAC
[12-month CLV of acquired customers] / [CAC (new customer)]

// Platform over-claim (x)
SUM([platform_conversions]) / SUM([attributed_orders])

// Profit after spend
SUM([attributed_revenue]) * [Gross Margin] - SUM([spend])
```

## Calculated fields on `mart_attribution_by_channel`
```
// Credited revenue (selected model)          -> use as the measure on the channel bar chart
IF [model] = [Attribution Model] THEN [attributed_revenue] END

// Share (selected model)
IF [model] = [Attribution Model] THEN [revenue_share] END
```
`mart_attribution_comparison` is one row per channel with all four shares: use it as-is for the slope chart / heat map (`share_first_touch`, `share_last_touch`, `share_linear`, `share_time_decay`, `share_spread_pp`).

## Calculated fields on `customer_profile`
```
// Customers
COUNTD([person_id])

// Win-back priority flag
IF [clv_tier] IN ('Platinum','Gold') AND [lifecycle_stage] IN ('At Risk','Churned') THEN 'Win back' ELSE 'Other' END

// Revenue at risk (12m)
IF [lifecycle_stage] IN ('At Risk','Churned') THEN [predicted_clv_12m_revenue] END

// Multi-channel customer
IF [web_sessions] > 0 AND [app_sessions] > 0 THEN 'Web + app' ELSEIF [app_sessions] > 0 THEN 'App only' ELSE 'Web only' END
```

## Calculated fields on `budget_recommendations`
```
// Spend change ($)
[recommended_spend] - [current_spend]

// Action colour key
[action]          // Scale up = green, Cut / reallocate = red, Maintain = grey, Test incrementality = amber (#FF9F1C)
```
