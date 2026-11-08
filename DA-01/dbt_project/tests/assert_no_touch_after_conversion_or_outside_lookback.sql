-- Touchpoints must precede the order and fall inside the lookback window.
select model, order_id, touch_ts, ordered_at
from {{ ref('fct_attribution_credits') }}
where touch_ts is not null
  and (touch_ts > ordered_at or touch_ts < {{ c360_ts_sub_days('ordered_at', var('attribution_lookback_days')) }})
