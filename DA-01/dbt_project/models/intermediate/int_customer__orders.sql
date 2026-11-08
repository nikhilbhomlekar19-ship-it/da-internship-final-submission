{#- Person-level order summary (completed orders are the "real" sales; returns/cancellations are counted separately). -#}
select
    person_id,
    min(case when is_conversion then ordered_at end)                                  as first_order_at,
    max(case when is_conversion then ordered_at end)                                  as last_order_at,
    sum(case when is_conversion then 1 else 0 end)                                    as order_count,
    sum(case when status = 'returned' then 1 else 0 end)                              as return_count,
    sum(case when status = 'cancelled' then 1 else 0 end)                             as cancel_count,
    sum(case when is_conversion then net_revenue else 0 end)                          as net_revenue,
    sum(case when is_conversion then net_revenue else 0 end)
        / nullif(sum(case when is_conversion then 1 else 0 end), 0)                   as avg_order_value,
    sum(case when is_conversion and order_channel = 'web' then 1 else 0 end)          as web_orders,
    sum(case when is_conversion and order_channel = 'app' then 1 else 0 end)          as app_orders,
    sum(case when is_conversion and order_channel = 'store' then 1 else 0 end)        as store_orders
from {{ ref('fct_orders') }}
group by person_id
