-- Whatever the model, total credited revenue must reconcile to the revenue of the conversions it attributes.
with expected as (
    select sum(net_revenue) as total from {{ ref('fct_orders') }} where is_conversion and in_tracking_window
),
actual as (
    select model, sum(credited_revenue) as total from {{ ref('fct_attribution_credits') }} group by model
)
select a.model, a.total as credited, e.total as expected
from actual a cross join expected e
where abs(a.total - e.total) > 0.01
