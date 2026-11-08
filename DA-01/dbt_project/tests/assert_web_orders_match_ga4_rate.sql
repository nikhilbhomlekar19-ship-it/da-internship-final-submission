{{ config(severity='warn') }}
-- Data-quality alert (warn): at least 85% of in-window web CRM orders should be found in GA4 purchases
-- (consent denial / ad blockers explain the rest).
with w as (
    select count(*) as n, sum(case when is_tracked_online then 1 else 0 end) as matched
    from {{ ref('fct_orders') }}
    where order_channel = 'web' and in_tracking_window
)
select n, matched, matched * 1.0 / nullif(n, 0) as match_rate
from w
where matched * 1.0 / nullif(n, 0) < 0.85
