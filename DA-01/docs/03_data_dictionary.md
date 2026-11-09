# Data dictionary

Grain, purpose and the important columns of every layer.  A generated, always-correct column listing (names + types) is appended at the bottom
(`python scripts/generate_data_dictionary.py`).  Model descriptions and tests also live in the dbt `_schema.yml` files (`make docs`).

## 1. Raw sources (`c360_raw`; GA4 stays in the public dataset on BigQuery)

| Table | Grain | Key columns |
|---|---|---|
| `ga4_events` / `events_*` | one GA4 event | `event_date` (STRING yyyymmdd), `event_timestamp` (micros), `event_name`, `user_pseudo_id`, `user_id`, `event_params[]` (`ga_session_id`, `source`, `medium`, `campaign`, `page_location`, ...), `traffic_source.*` (first-user), `device`, `geo`, `ecommerce.*` |
| `segment_identifies` | one identify() call | `anonymous_id`, `user_id` (= CRM customer id), `email`, `ga_client_id` (trait), `timestamp`, `context_library_name` |
| `segment_tracks` | one track() call | `anonymous_id`, `user_id`, `event`, `timestamp`, `context_campaign_{source,medium,name}`, `context_device_type` |
| `segment_order_completed` | one order event | `order_id` (= CRM `external_ref`), `total`, `revenue`, `currency`, `coupon` |
| `crm_customers` | one CRM record (duplicates possible) | `customer_id`, `first_name`, `last_name`, `email` (messy), `phone` (messy), `country`, `created_at`, `marketing_opt_in`, `loyalty_tier`, `self_reported_source` |
| `crm_orders` | one order | `order_id`, `customer_id`, `ordered_at`, `order_channel` (web/app/store), `status`, `order_total` (before discount), `discount_amount`, `refund_amount`, `external_ref` (= GA4 `transaction_id` / Segment `order_id`) |
| `ads_spend_daily` | campaign x day | `date`, `platform`, `campaign_id`, `utm_source/medium/campaign`, `impressions`, `clicks`, `cost`, `platform_conversions`, `platform_conversion_value` |

## 2. Staging / intermediate (summary)

| Model | Grain | Notes |
|---|---|---|
| `stg_ga4__events` | event | event_params flattened; filtered to the window (`_table_suffix` pruning on BigQuery) |
| `stg_ga4__purchases` | transaction | de-duplicated by `transaction_id` |
| `stg_segment__identifies / tracks / orders` | message | renamed + typed |
| `stg_crm__customers` | CRM record | `email_norm`, `email_hash` (md5), `phone_norm` |
| `stg_crm__orders` | order | `paid_amount`, `net_revenue` |
| `stg_ads__spend` | campaign-day | `campaign_key`, `channel_group` |
| `int_ga4__sessions`, `int_segment__sessions` | session | same 21 columns so they can be unioned |
| `int_identity_edges` | evidence edge | `node_a`, `node_b`, `edge_type`, `edge_class`, `first/last_seen_at`, `evidence_count` |
| `int_attribution__paths` | order x touchpoint | positions, hours before order, four credit columns |
| `int_customer__orders` | person | order counts / revenue / first and last order |

## 3. Marts (`c360_marts`) - what Tableau reads

### `fct_sessions` - one row per web or app session
`session_key` (PK), `source_system` (ga4 | segment), `device_id`, **`person_id`** (resolved; `anon:<device>` if unlinked), `is_identified`, `is_shared_device`, `session_date`, `session_start_ts`, `session_end_ts`, `duration_seconds`,
`utm_source/medium/campaign`, **`channel_group`**, **`campaign_key`**, `platform` (device category / OS), `country`, `landing_page`, `event_count`, `page_views`, `item_views`, `has_add_to_cart`, `has_checkout`, `purchases`, `session_revenue` (tracker revenue), `person_session_number`.

### `fct_orders` - one row per CRM order
`order_id` (PK), `person_id`, `crm_customer_id`, `ordered_at`, `order_date`, `order_channel`, `status`, `gross_amount`, `discount_amount`, `paid_amount`, `refund_amount`, **`net_revenue`**, `external_ref`,
`converting_session_key`, `is_tracked_online` (found in GA4/Segment), `tracker_revenue`, `revenue_gap_vs_tracker`, **`is_conversion`** (completed), `in_tracking_window`, `customer_order_number`, **`is_first_order`**, `days_since_prev_order`.

### `customer_profile` - Customer 360, one row per resolved person in the CRM
* identity: `person_id`, `primary_crm_customer_id`, `crm_record_count` (>1 = duplicates merged), `email_hash`, `first_name`, `country_code`, `city`, `signup_at`, `marketing_opt_in`, `loyalty_tier`, `self_reported_source`, `signup_channel`
* behaviour: `total_sessions`, `web_sessions`, `app_sessions`, `distinct_devices`, `first_session_at`, `last_session_at`, `is_app_user`, `is_multi_device`, `uses_shared_device`
* commerce: `order_count`, `return_count`, `avg_order_value`, `first_order_at`, `last_order_at`, `web_orders`, `app_orders`, `store_orders`, `recency_days`, `days_since_first_order`, `historical_clv_revenue`, `historical_clv_profit`
* acquisition: `acquisition_channel` (channel of the first linked session; `Pre-tracking (existing customer)` if the first order predates the window), `first_session_campaign_key`
* segments: `r_score`, `f_score`, `m_score`, `rfm_code`, **`rfm_segment`**, `monetary_tier`, **`clv_tier`**, **`lifecycle_stage`**
* forecast: `p_alive`, `predicted_orders_12m`, `predicted_aov`, `predicted_clv_12m_revenue`, `predicted_clv_12m_profit`, `total_clv_revenue` (historical + predicted), `clv_percentile`

### `customer_rfm` - one row per customer with >= 1 completed order
`recency_days`, `frequency`, `monetary`, `r_score`, `f_score`, `m_score`, `rfm_code`, `rfm_segment`, `monetary_tier`.

### `fct_attribution_credits` - long format, one row per (model, order, touchpoint)
`model` (first_touch | last_touch | linear | time_decay), `order_id`, `person_id`, `ordered_at`, `touch_ts`, `touch_date`, `credit_date`, `session_key`, `source_system`, `channel_group`, `campaign_key`, `touch_position`, `touch_count`, `hours_before_conversion`, **`credit`**, `net_revenue`, **`credited_revenue`**, `is_first_order`.

### Reporting marts
| Mart | Grain | Key columns |
|---|---|---|
| `mart_attribution_by_channel` | model x channel | `attributed_orders`, `attributed_new_customers`, `attributed_revenue`, `revenue_share`, `order_share`, `revenue_rank`, `channel_type`, `is_paid`, `color_hex` |
| `mart_attribution_comparison` | channel | `revenue_/share_/rank_` x 4 models, `share_spread_pp`, `rank_swing`, `first_minus_last_share` |
| `mart_campaign_roi` | campaign_key x model | `spend`, `impressions`, `clicks`, `attributed_*`, `new_customer_clv_credit`, `gross_profit`, `profit_after_spend`, `roas`, `roi`, `cpa`, `cac_new_customer`, `avg_new_customer_clv`, `ltv_to_cac`, `platform_conversions`, `platform_revenue`, `platform_roas`, `platform_overclaim_ratio`, `cpc`, `ctr`, `click_to_order_rate`, `is_paid` |
| `mart_channel_roi` | channel x model | same metrics at channel level (includes unpaid channels) |
| `mart_campaign_daily` | day x campaign x model | `spend`, `clicks`, `attributed_revenue` (credit dated by touch) |
| `mart_daily_kpis` | day | `sessions`, `orders`, `net_revenue`, `new_customers`, `ad_spend`, `aov`, `conversion_rate`, `blended_roas`, `blended_cac` |
| `mart_sessions_by_channel_daily` | day x channel x web/app | `sessions`, `add_to_cart_sessions`, `checkout_sessions`, `purchasing_sessions`, `tracker_revenue` |

## 4. ML outputs (`c360_ml`, written by Python)

| Table | Grain | Columns |
|---|---|---|
| `identity_nodes` | identifier | `node_key` (`crm:`, `email:`, `phone:`, `ga:`, `sa:`), `node_type`, `node_value`, `person_id`, `link_method` (evidence types), `confidence` (high/medium/low), `is_shared_device`, `group_size` |
| `identity_nodes_naive` | identifier | naive connected-components baseline (evaluation only) |
| `clv_forecast` | person | `n_orders`, `frequency`, `recency_weeks`, `T_weeks`, `avg_repeat_value`, `first_order_value`, `p_alive`, `predicted_orders_12m`, `predicted_aov`, `clv_12m_revenue`, `as_of_date`, `model_version` |
| `budget_recommendations` | paid campaign | `action`, `confidence`, `current_spend`, `recommended_spend`, `change_pct`, `roas_<model>`, `roas_median`, `beta_median`, `mroas_median`, `last_vs_first_touch_ratio`, `model_dependent`, `direction_agreement`, `spend_if_only_<model>`, `note` |
| `response_curves` | campaign x model | `n_days`, `beta_fit`, `beta_se`, `beta` (shrunk), `fit_quality`, `spend`, `attributed_revenue`, `roas`, `mroas` |

## 5. Seeds, variables, macros
* Seed `channel_catalog`: channel -> type (Paid/Owned/Earned/Direct), `is_paid`, `sort_order`, `color_hex` (keeps Tableau colours consistent).
* dbt vars: `start_date`, `end_date`, `as_of_date`, `use_public_ga4`, `session_timeout_minutes` (30), `attribution_lookback_days` (30), `time_decay_half_life_days` (7), `direct_policy` (deprioritize | include), `gross_margin_pct` (0.45), optional `segment_schema`, `segment_*_table`.
* Environment variables: see `.env.example`.

---

## Appendix: column listing (generated from the warehouse)

### Raw sources - `c360_raw`

<details><summary><code>ads_spend_daily</code> (14 columns)</summary>

| column | type |
|---|---|
| `date` | DATE |
| `platform` | VARCHAR |
| `account_id` | VARCHAR |
| `campaign_id` | VARCHAR |
| `campaign_name` | VARCHAR |
| `utm_source` | VARCHAR |
| `utm_medium` | VARCHAR |
| `utm_campaign` | VARCHAR |
| `impressions` | BIGINT |
| `clicks` | BIGINT |
| `cost` | DOUBLE |
| `currency` | VARCHAR |
| `platform_conversions` | DOUBLE |
| `platform_conversion_value` | DOUBLE |

</details>

<details><summary><code>crm_customers</code> (13 columns)</summary>

| column | type |
|---|---|
| `customer_id` | VARCHAR |
| `first_name` | VARCHAR |
| `last_name` | VARCHAR |
| `email` | VARCHAR |
| `phone` | VARCHAR |
| `country` | VARCHAR |
| `city` | VARCHAR |
| `created_at` | TIMESTAMP |
| `marketing_opt_in` | BOOLEAN |
| `loyalty_tier` | VARCHAR |
| `self_reported_source` | VARCHAR |
| `signup_channel` | VARCHAR |
| `updated_at` | TIMESTAMP |

</details>

<details><summary><code>crm_orders</code> (12 columns)</summary>

| column | type |
|---|---|
| `order_id` | VARCHAR |
| `customer_id` | VARCHAR |
| `ordered_at` | TIMESTAMP |
| `order_channel` | VARCHAR |
| `status` | VARCHAR |
| `order_total` | DOUBLE |
| `discount_amount` | DOUBLE |
| `refund_amount` | DOUBLE |
| `currency` | VARCHAR |
| `external_ref` | VARCHAR |
| `coupon_code` | VARCHAR |
| `items_count` | BIGINT |

</details>

<details><summary><code>ga4_events</code> (13 columns)</summary>

| column | type |
|---|---|
| `event_date` | VARCHAR |
| `event_timestamp` | BIGINT |
| `event_name` | VARCHAR |
| `event_params` | STRUCT("key" VARCHAR, "value" STRUCT(string_value VARCHAR, int_value BIGINT, float_value DOUBLE, double_value DOUBLE))[] |
| `user_id` | VARCHAR |
| `user_pseudo_id` | VARCHAR |
| `user_first_touch_timestamp` | BIGINT |
| `device` | STRUCT(category VARCHAR, operating_system VARCHAR, web_info STRUCT(browser VARCHAR)) |
| `geo` | STRUCT(country VARCHAR, region VARCHAR, city VARCHAR) |
| `traffic_source` | STRUCT("name" VARCHAR, medium VARCHAR, "source" VARCHAR) |
| `ecommerce` | STRUCT(total_item_quantity BIGINT, purchase_revenue_in_usd DOUBLE, purchase_revenue DOUBLE, unique_items BIGINT, transaction_id VARCHAR) |
| `platform` | VARCHAR |
| `stream_id` | VARCHAR |

</details>

<details><summary><code>segment_identifies</code> (8 columns)</summary>

| column | type |
|---|---|
| `id` | VARCHAR |
| `anonymous_id` | VARCHAR |
| `user_id` | VARCHAR |
| `timestamp` | TIMESTAMP |
| `received_at` | TIMESTAMP |
| `email` | VARCHAR |
| `ga_client_id` | VARCHAR |
| `context_library_name` | VARCHAR |

</details>

<details><summary><code>segment_order_completed</code> (12 columns)</summary>

| column | type |
|---|---|
| `id` | VARCHAR |
| `anonymous_id` | VARCHAR |
| `user_id` | VARCHAR |
| `timestamp` | TIMESTAMP |
| `order_id` | VARCHAR |
| `total` | DOUBLE |
| `revenue` | DOUBLE |
| `currency` | VARCHAR |
| `coupon` | VARCHAR |
| `context_campaign_source` | VARCHAR |
| `context_campaign_medium` | VARCHAR |
| `context_campaign_name` | VARCHAR |

</details>

<details><summary><code>segment_tracks</code> (13 columns)</summary>

| column | type |
|---|---|
| `id` | VARCHAR |
| `anonymous_id` | VARCHAR |
| `user_id` | VARCHAR |
| `event` | VARCHAR |
| `event_text` | VARCHAR |
| `timestamp` | TIMESTAMP |
| `received_at` | TIMESTAMP |
| `context_campaign_source` | VARCHAR |
| `context_campaign_medium` | VARCHAR |
| `context_campaign_name` | VARCHAR |
| `context_device_type` | VARCHAR |
| `context_os_name` | VARCHAR |
| `context_library_name` | VARCHAR |

</details>

### Staging (views / tables) - `c360_staging`

<details><summary><code>channel_catalog</code> (5 columns)</summary>

| column | type |
|---|---|
| `channel_group` | VARCHAR |
| `channel_type` | VARCHAR |
| `is_paid` | BOOLEAN |
| `sort_order` | INTEGER |
| `color_hex` | VARCHAR |

</details>

<details><summary><code>stg_ads__spend</code> (15 columns)</summary>

| column | type |
|---|---|
| `spend_date` | DATE |
| `platform` | VARCHAR |
| `account_id` | VARCHAR |
| `campaign_id` | VARCHAR |
| `campaign_name` | VARCHAR |
| `utm_source` | VARCHAR |
| `utm_medium` | VARCHAR |
| `utm_campaign` | VARCHAR |
| `campaign_key` | VARCHAR |
| `channel_group` | VARCHAR |
| `impressions` | BIGINT |
| `clicks` | BIGINT |
| `cost` | DOUBLE |
| `platform_conversions` | DOUBLE |
| `platform_conversion_value` | DOUBLE |

</details>

<details><summary><code>stg_crm__customers</code> (13 columns)</summary>

| column | type |
|---|---|
| `customer_id` | VARCHAR |
| `first_name` | VARCHAR |
| `last_name` | VARCHAR |
| `email_norm` | VARCHAR |
| `email_hash` | VARCHAR |
| `phone_norm` | VARCHAR |
| `country_code` | VARCHAR |
| `city` | VARCHAR |
| `created_at` | TIMESTAMP |
| `marketing_opt_in` | BOOLEAN |
| `loyalty_tier` | VARCHAR |
| `self_reported_source` | VARCHAR |
| `signup_channel` | VARCHAR |

</details>

<details><summary><code>stg_crm__orders</code> (14 columns)</summary>

| column | type |
|---|---|
| `order_id` | VARCHAR |
| `customer_id` | VARCHAR |
| `ordered_at` | TIMESTAMP |
| `order_channel` | VARCHAR |
| `status` | VARCHAR |
| `gross_amount` | DOUBLE |
| `discount_amount` | DOUBLE |
| `refund_amount` | DOUBLE |
| `external_ref` | VARCHAR |
| `coupon_code` | VARCHAR |
| `items_count` | BIGINT |
| `order_date` | DATE |
| `paid_amount` | DOUBLE |
| `net_revenue` | DOUBLE |

</details>

<details><summary><code>stg_ga4__events</code> (22 columns)</summary>

| column | type |
|---|---|
| `event_date` | DATE |
| `event_ts` | TIMESTAMP |
| `event_name` | VARCHAR |
| `user_pseudo_id` | VARCHAR |
| `user_id` | VARCHAR |
| `ga_session_id` | BIGINT |
| `ga_session_number` | BIGINT |
| `page_location` | VARCHAR |
| `param_source` | VARCHAR |
| `param_medium` | VARCHAR |
| `param_campaign` | VARCHAR |
| `engagement_time_msec` | BIGINT |
| `first_user_source` | VARCHAR |
| `first_user_medium` | VARCHAR |
| `first_user_campaign` | VARCHAR |
| `device_category` | VARCHAR |
| `device_os` | VARCHAR |
| `country` | VARCHAR |
| `city` | VARCHAR |
| `transaction_id` | VARCHAR |
| `purchase_revenue` | DOUBLE |
| `item_quantity` | BIGINT |

</details>

<details><summary><code>stg_ga4__purchases</code> (7 columns)</summary>

| column | type |
|---|---|
| `transaction_id` | VARCHAR |
| `user_pseudo_id` | VARCHAR |
| `user_id` | VARCHAR |
| `session_key` | VARCHAR |
| `purchase_ts` | TIMESTAMP |
| `purchase_revenue` | DOUBLE |
| `item_quantity` | BIGINT |

</details>

<details><summary><code>stg_segment__identifies</code> (7 columns)</summary>

| column | type |
|---|---|
| `message_id` | VARCHAR |
| `anonymous_id` | VARCHAR |
| `user_id` | VARCHAR |
| `event_ts` | TIMESTAMP |
| `email_norm` | VARCHAR |
| `ga_client_id` | VARCHAR |
| `context_library_name` | VARCHAR |

</details>

<details><summary><code>stg_segment__orders</code> (9 columns)</summary>

| column | type |
|---|---|
| `message_id` | VARCHAR |
| `anonymous_id` | VARCHAR |
| `user_id` | VARCHAR |
| `event_ts` | TIMESTAMP |
| `order_id` | VARCHAR |
| `revenue` | DOUBLE |
| `total` | DOUBLE |
| `currency` | VARCHAR |
| `coupon` | VARCHAR |

</details>

<details><summary><code>stg_segment__tracks</code> (10 columns)</summary>

| column | type |
|---|---|
| `message_id` | VARCHAR |
| `anonymous_id` | VARCHAR |
| `user_id` | VARCHAR |
| `event_name` | VARCHAR |
| `event_ts` | TIMESTAMP |
| `campaign_source` | VARCHAR |
| `campaign_medium` | VARCHAR |
| `campaign_name` | VARCHAR |
| `device_type` | VARCHAR |
| `os_name` | VARCHAR |

</details>

### Intermediate - `c360_intermediate`

<details><summary><code>int_attribution__paths</code> (19 columns)</summary>

| column | type |
|---|---|
| `order_id` | VARCHAR |
| `person_id` | VARCHAR |
| `ordered_at` | TIMESTAMP |
| `order_date` | DATE |
| `net_revenue` | DOUBLE |
| `is_first_order` | BOOLEAN |
| `session_key` | VARCHAR |
| `session_start_ts` | TIMESTAMP |
| `touch_date` | DATE |
| `channel_group` | VARCHAR |
| `campaign_key` | VARCHAR |
| `source_system` | VARCHAR |
| `touch_position` | BIGINT |
| `touch_count` | BIGINT |
| `hours_before_conversion` | DOUBLE |
| `credit_first_touch` | DOUBLE |
| `credit_last_touch` | DOUBLE |
| `credit_linear` | DOUBLE |
| `credit_time_decay` | DOUBLE |

</details>

<details><summary><code>int_customer__orders</code> (11 columns)</summary>

| column | type |
|---|---|
| `person_id` | VARCHAR |
| `first_order_at` | TIMESTAMP |
| `last_order_at` | TIMESTAMP |
| `order_count` | HUGEINT |
| `return_count` | HUGEINT |
| `cancel_count` | HUGEINT |
| `net_revenue` | DOUBLE |
| `avg_order_value` | DOUBLE |
| `web_orders` | HUGEINT |
| `app_orders` | HUGEINT |
| `store_orders` | HUGEINT |

</details>

<details><summary><code>int_ga4__sessions</code> (21 columns)</summary>

| column | type |
|---|---|
| `session_key` | VARCHAR |
| `source_system` | VARCHAR |
| `device_id` | VARCHAR |
| `session_start_ts` | TIMESTAMP |
| `session_end_ts` | TIMESTAMP |
| `utm_source` | VARCHAR |
| `utm_medium` | VARCHAR |
| `utm_campaign` | VARCHAR |
| `channel_group` | VARCHAR |
| `campaign_key` | VARCHAR |
| `platform` | VARCHAR |
| `country` | VARCHAR |
| `landing_page` | VARCHAR |
| `event_count` | BIGINT |
| `page_views` | HUGEINT |
| `item_views` | HUGEINT |
| `has_add_to_cart` | INTEGER |
| `has_checkout` | INTEGER |
| `purchases` | BIGINT |
| `session_revenue` | DOUBLE |
| `user_id_in_session` | VARCHAR |

</details>

<details><summary><code>int_identity_edges</code> (7 columns)</summary>

| column | type |
|---|---|
| `node_a` | VARCHAR |
| `node_b` | VARCHAR |
| `edge_type` | VARCHAR |
| `edge_class` | VARCHAR |
| `first_seen_at` | TIMESTAMP |
| `last_seen_at` | TIMESTAMP |
| `evidence_count` | BIGINT |

</details>

<details><summary><code>int_segment__sessions</code> (21 columns)</summary>

| column | type |
|---|---|
| `session_key` | VARCHAR |
| `source_system` | VARCHAR |
| `device_id` | VARCHAR |
| `session_start_ts` | TIMESTAMP |
| `session_end_ts` | TIMESTAMP |
| `utm_source` | VARCHAR |
| `utm_medium` | VARCHAR |
| `utm_campaign` | VARCHAR |
| `channel_group` | VARCHAR |
| `campaign_key` | VARCHAR |
| `platform` | VARCHAR |
| `country` | VARCHAR |
| `landing_page` | VARCHAR |
| `event_count` | BIGINT |
| `page_views` | HUGEINT |
| `item_views` | HUGEINT |
| `has_add_to_cart` | INTEGER |
| `has_checkout` | INTEGER |
| `purchases` | HUGEINT |
| `session_revenue` | DOUBLE |
| `user_id_in_session` | VARCHAR |

</details>

### Marts (what Tableau reads) - `c360_marts`

<details><summary><code>customer_profile</code> (50 columns)</summary>

| column | type |
|---|---|
| `person_id` | VARCHAR |
| `primary_crm_customer_id` | VARCHAR |
| `crm_record_count` | BIGINT |
| `email_hash` | VARCHAR |
| `first_name` | VARCHAR |
| `country_code` | VARCHAR |
| `city` | VARCHAR |
| `signup_at` | TIMESTAMP |
| `marketing_opt_in` | BOOLEAN |
| `loyalty_tier` | VARCHAR |
| `self_reported_source` | VARCHAR |
| `signup_channel` | VARCHAR |
| `total_sessions` | BIGINT |
| `web_sessions` | HUGEINT |
| `app_sessions` | HUGEINT |
| `distinct_devices` | BIGINT |
| `first_session_at` | TIMESTAMP |
| `last_session_at` | TIMESTAMP |
| `is_app_user` | BOOLEAN |
| `is_multi_device` | BOOLEAN |
| `uses_shared_device` | BOOLEAN |
| `order_count` | HUGEINT |
| `return_count` | HUGEINT |
| `historical_clv_revenue` | DOUBLE |
| `historical_clv_profit` | DOUBLE |
| `avg_order_value` | DOUBLE |
| `first_order_at` | TIMESTAMP |
| `last_order_at` | TIMESTAMP |
| `web_orders` | HUGEINT |
| `app_orders` | HUGEINT |
| `store_orders` | HUGEINT |
| `recency_days` | BIGINT |
| `days_since_first_order` | BIGINT |
| `acquisition_channel` | VARCHAR |
| `first_session_campaign_key` | VARCHAR |
| `r_score` | BIGINT |
| `f_score` | BIGINT |
| `m_score` | BIGINT |
| `rfm_code` | VARCHAR |
| `rfm_segment` | VARCHAR |
| `monetary_tier` | VARCHAR |
| `p_alive` | DOUBLE |
| `predicted_orders_12m` | DOUBLE |
| `predicted_aov` | DOUBLE |
| `predicted_clv_12m_revenue` | DOUBLE |
| `predicted_clv_12m_profit` | DOUBLE |
| `total_clv_revenue` | DOUBLE |
| `clv_percentile` | DOUBLE |
| `clv_tier` | VARCHAR |
| `lifecycle_stage` | VARCHAR |

</details>

<details><summary><code>customer_rfm</code> (12 columns)</summary>

| column | type |
|---|---|
| `person_id` | VARCHAR |
| `first_order_at` | TIMESTAMP |
| `last_order_at` | TIMESTAMP |
| `recency_days` | BIGINT |
| `frequency` | HUGEINT |
| `monetary` | DOUBLE |
| `r_score` | BIGINT |
| `f_score` | BIGINT |
| `m_score` | BIGINT |
| `rfm_code` | VARCHAR |
| `rfm_segment` | VARCHAR |
| `monetary_tier` | VARCHAR |

</details>

<details><summary><code>fct_attribution_credits</code> (19 columns)</summary>

| column | type |
|---|---|
| `model` | VARCHAR |
| `order_id` | VARCHAR |
| `person_id` | VARCHAR |
| `ordered_at` | TIMESTAMP |
| `order_date` | DATE |
| `touch_ts` | TIMESTAMP |
| `touch_date` | DATE |
| `credit_date` | DATE |
| `session_key` | VARCHAR |
| `source_system` | VARCHAR |
| `channel_group` | VARCHAR |
| `campaign_key` | VARCHAR |
| `touch_position` | BIGINT |
| `touch_count` | BIGINT |
| `hours_before_conversion` | DOUBLE |
| `credit` | DOUBLE |
| `net_revenue` | DOUBLE |
| `credited_revenue` | DOUBLE |
| `is_first_order` | BOOLEAN |

</details>

<details><summary><code>fct_orders</code> (22 columns)</summary>

| column | type |
|---|---|
| `order_id` | VARCHAR |
| `person_id` | VARCHAR |
| `crm_customer_id` | VARCHAR |
| `ordered_at` | TIMESTAMP |
| `order_date` | DATE |
| `order_channel` | VARCHAR |
| `status` | VARCHAR |
| `gross_amount` | DOUBLE |
| `discount_amount` | DOUBLE |
| `paid_amount` | DOUBLE |
| `refund_amount` | DOUBLE |
| `net_revenue` | DOUBLE |
| `external_ref` | VARCHAR |
| `converting_session_key` | VARCHAR |
| `is_tracked_online` | BOOLEAN |
| `tracker_revenue` | DOUBLE |
| `is_conversion` | BOOLEAN |
| `in_tracking_window` | BOOLEAN |
| `customer_order_number` | BIGINT |
| `is_first_order` | BOOLEAN |
| `days_since_prev_order` | BIGINT |
| `revenue_gap_vs_tracker` | DOUBLE |

</details>

<details><summary><code>fct_sessions</code> (26 columns)</summary>

| column | type |
|---|---|
| `session_key` | VARCHAR |
| `source_system` | VARCHAR |
| `device_id` | VARCHAR |
| `person_id` | VARCHAR |
| `is_identified` | BOOLEAN |
| `is_shared_device` | BOOLEAN |
| `session_date` | DATE |
| `session_start_ts` | TIMESTAMP |
| `session_end_ts` | TIMESTAMP |
| `duration_seconds` | BIGINT |
| `utm_source` | VARCHAR |
| `utm_medium` | VARCHAR |
| `utm_campaign` | VARCHAR |
| `channel_group` | VARCHAR |
| `campaign_key` | VARCHAR |
| `platform` | VARCHAR |
| `country` | VARCHAR |
| `landing_page` | VARCHAR |
| `event_count` | BIGINT |
| `page_views` | HUGEINT |
| `item_views` | HUGEINT |
| `has_add_to_cart` | INTEGER |
| `has_checkout` | INTEGER |
| `purchases` | HUGEINT |
| `session_revenue` | DOUBLE |
| `person_session_number` | BIGINT |

</details>

<details><summary><code>mart_attribution_by_channel</code> (12 columns)</summary>

| column | type |
|---|---|
| `model` | VARCHAR |
| `channel_group` | VARCHAR |
| `channel_type` | VARCHAR |
| `is_paid` | BOOLEAN |
| `sort_order` | INTEGER |
| `color_hex` | VARCHAR |
| `attributed_orders` | DOUBLE |
| `attributed_new_customers` | DOUBLE |
| `attributed_revenue` | DOUBLE |
| `revenue_share` | DOUBLE |
| `order_share` | DOUBLE |
| `revenue_rank` | BIGINT |

</details>

<details><summary><code>mart_attribution_comparison</code> (16 columns)</summary>

| column | type |
|---|---|
| `channel_group` | VARCHAR |
| `revenue_first_touch` | DOUBLE |
| `share_first_touch` | DOUBLE |
| `rank_first_touch` | BIGINT |
| `revenue_last_touch` | DOUBLE |
| `share_last_touch` | DOUBLE |
| `rank_last_touch` | BIGINT |
| `revenue_linear` | DOUBLE |
| `share_linear` | DOUBLE |
| `rank_linear` | BIGINT |
| `revenue_time_decay` | DOUBLE |
| `share_time_decay` | DOUBLE |
| `rank_time_decay` | BIGINT |
| `share_spread_pp` | DOUBLE |
| `rank_swing` | BIGINT |
| `first_minus_last_share` | DOUBLE |

</details>

<details><summary><code>mart_campaign_daily</code> (9 columns)</summary>

| column | type |
|---|---|
| `spend_date` | DATE |
| `campaign_key` | VARCHAR |
| `channel_group` | VARCHAR |
| `model` | VARCHAR |
| `spend` | DOUBLE |
| `clicks` | HUGEINT |
| `impressions` | HUGEINT |
| `attributed_orders` | DOUBLE |
| `attributed_revenue` | DOUBLE |

</details>

<details><summary><code>mart_campaign_roi</code> (28 columns)</summary>

| column | type |
|---|---|
| `campaign_key` | VARCHAR |
| `model` | VARCHAR |
| `channel_group` | VARCHAR |
| `platform` | VARCHAR |
| `campaign_name` | VARCHAR |
| `is_paid` | BOOLEAN |
| `spend` | DOUBLE |
| `impressions` | HUGEINT |
| `clicks` | HUGEINT |
| `platform_conversions` | DOUBLE |
| `platform_revenue` | DOUBLE |
| `attributed_orders` | DOUBLE |
| `attributed_new_customers` | DOUBLE |
| `attributed_revenue` | DOUBLE |
| `new_customer_clv_credit` | DOUBLE |
| `gross_profit` | DOUBLE |
| `profit_after_spend` | DOUBLE |
| `roas` | DOUBLE |
| `roi` | DOUBLE |
| `cpa` | DOUBLE |
| `cac_new_customer` | DOUBLE |
| `avg_new_customer_clv` | DOUBLE |
| `ltv_to_cac` | DOUBLE |
| `platform_roas` | DOUBLE |
| `platform_overclaim_ratio` | DOUBLE |
| `cpc` | DOUBLE |
| `ctr` | DOUBLE |
| `click_to_order_rate` | DOUBLE |

</details>

<details><summary><code>mart_channel_roi</code> (25 columns)</summary>

| column | type |
|---|---|
| `model` | VARCHAR |
| `channel_group` | VARCHAR |
| `channel_type` | VARCHAR |
| `is_paid` | BOOLEAN |
| `sort_order` | INTEGER |
| `color_hex` | VARCHAR |
| `spend` | DOUBLE |
| `impressions` | HUGEINT |
| `clicks` | HUGEINT |
| `platform_conversions` | DOUBLE |
| `platform_revenue` | DOUBLE |
| `attributed_orders` | DOUBLE |
| `attributed_new_customers` | DOUBLE |
| `attributed_revenue` | DOUBLE |
| `new_customer_clv_credit` | DOUBLE |
| `gross_profit` | DOUBLE |
| `profit_after_spend` | DOUBLE |
| `roas` | DOUBLE |
| `roi` | DOUBLE |
| `cpa` | DOUBLE |
| `cac_new_customer` | DOUBLE |
| `avg_new_customer_clv` | DOUBLE |
| `ltv_to_cac` | DOUBLE |
| `platform_roas` | DOUBLE |
| `platform_overclaim_ratio` | DOUBLE |

</details>

<details><summary><code>mart_daily_kpis</code> (13 columns)</summary>

| column | type |
|---|---|
| `kpi_date` | DATE |
| `sessions` | BIGINT |
| `web_sessions` | HUGEINT |
| `app_sessions` | HUGEINT |
| `orders` | HUGEINT |
| `net_revenue` | DOUBLE |
| `new_customers` | HUGEINT |
| `ad_spend` | DOUBLE |
| `ad_clicks` | HUGEINT |
| `aov` | DOUBLE |
| `conversion_rate` | DOUBLE |
| `blended_roas` | DOUBLE |
| `blended_cac` | DOUBLE |

</details>

<details><summary><code>mart_sessions_by_channel_daily</code> (8 columns)</summary>

| column | type |
|---|---|
| `session_date` | DATE |
| `channel_group` | VARCHAR |
| `source_system` | VARCHAR |
| `sessions` | BIGINT |
| `add_to_cart_sessions` | HUGEINT |
| `checkout_sessions` | HUGEINT |
| `purchasing_sessions` | HUGEINT |
| `tracker_revenue` | DOUBLE |

</details>

### ML outputs (written by Python) - `c360_ml`

<details><summary><code>budget_recommendations</code> (28 columns)</summary>

| column | type |
|---|---|
| `campaign_key` | VARCHAR |
| `channel_group` | VARCHAR |
| `platform` | VARCHAR |
| `campaign_name` | VARCHAR |
| `platform_roas` | DOUBLE |
| `ltv_to_cac_time_decay` | DOUBLE |
| `roas_first_touch` | DOUBLE |
| `roas_last_touch` | DOUBLE |
| `roas_linear` | DOUBLE |
| `roas_time_decay` | DOUBLE |
| `beta_median` | DOUBLE |
| `mroas_median` | DOUBLE |
| `roas_median` | DOUBLE |
| `last_vs_first_touch_ratio` | DOUBLE |
| `model_dependent` | BOOLEAN |
| `current_spend` | DOUBLE |
| `recommended_spend` | DOUBLE |
| `change_pct` | DOUBLE |
| `change_amount` | DOUBLE |
| `spend_if_only_first_touch` | DOUBLE |
| `spend_if_only_last_touch` | DOUBLE |
| `spend_if_only_linear` | DOUBLE |
| `spend_if_only_time_decay` | DOUBLE |
| `direction_agreement` | DOUBLE |
| `low_fit_models` | BIGINT |
| `action` | VARCHAR |
| `confidence` | VARCHAR |
| `note` | VARCHAR |

</details>

<details><summary><code>clv_forecast</code> (13 columns)</summary>

| column | type |
|---|---|
| `person_id` | VARCHAR |
| `n_orders` | BIGINT |
| `frequency` | DOUBLE |
| `recency_weeks` | DOUBLE |
| `T_weeks` | DOUBLE |
| `avg_repeat_value` | DOUBLE |
| `first_order_value` | DOUBLE |
| `p_alive` | DOUBLE |
| `predicted_orders_12m` | DOUBLE |
| `predicted_aov` | DOUBLE |
| `clv_12m_revenue` | DOUBLE |
| `as_of_date` | TIMESTAMP_S |
| `model_version` | VARCHAR |

</details>

<details><summary><code>identity_nodes</code> (8 columns)</summary>

| column | type |
|---|---|
| `node_key` | VARCHAR |
| `node_type` | VARCHAR |
| `node_value` | VARCHAR |
| `person_id` | VARCHAR |
| `link_method` | VARCHAR |
| `confidence` | VARCHAR |
| `is_shared_device` | BOOLEAN |
| `group_size` | BIGINT |

</details>

<details><summary><code>identity_nodes_naive</code> (8 columns)</summary>

| column | type |
|---|---|
| `node_key` | VARCHAR |
| `node_type` | VARCHAR |
| `node_value` | VARCHAR |
| `person_id` | VARCHAR |
| `link_method` | VARCHAR |
| `confidence` | VARCHAR |
| `is_shared_device` | BOOLEAN |
| `group_size` | BIGINT |

</details>

<details><summary><code>response_curves</code> (11 columns)</summary>

| column | type |
|---|---|
| `campaign_key` | VARCHAR |
| `model` | VARCHAR |
| `n_days` | BIGINT |
| `beta_fit` | DOUBLE |
| `beta_se` | DOUBLE |
| `beta` | DOUBLE |
| `fit_quality` | VARCHAR |
| `spend` | DOUBLE |
| `attributed_revenue` | DOUBLE |
| `roas` | DOUBLE |
| `mroas` | DOUBLE |

</details>
