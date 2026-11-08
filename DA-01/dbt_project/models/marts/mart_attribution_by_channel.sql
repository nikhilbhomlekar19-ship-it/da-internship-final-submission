{#- Channel-level result of each attribution model (long format - ideal for a Tableau "Attribution model" parameter). -#}
with by_channel as (
    select
        model,
        channel_group,
        sum(credit)                                                         as attributed_orders,
        sum(case when is_first_order then credit else 0 end)                as attributed_new_customers,
        sum(credited_revenue)                                               as attributed_revenue
    from {{ ref('fct_attribution_credits') }}
    group by model, channel_group
),

totals as (
    select model, sum(attributed_revenue) as total_revenue, sum(attributed_orders) as total_orders
    from by_channel group by model
)

select
    b.model,
    b.channel_group,
    ch.channel_type,
    coalesce(ch.is_paid, false)                                             as is_paid,
    ch.sort_order,
    ch.color_hex,
    b.attributed_orders,
    b.attributed_new_customers,
    b.attributed_revenue,
    b.attributed_revenue / nullif(t.total_revenue, 0)                       as revenue_share,
    b.attributed_orders / nullif(t.total_orders, 0)                         as order_share,
    rank() over (partition by b.model order by b.attributed_revenue desc)   as revenue_rank
from by_channel b
join totals t on t.model = b.model
left join {{ ref('channel_catalog') }} ch on ch.channel_group = b.channel_group
