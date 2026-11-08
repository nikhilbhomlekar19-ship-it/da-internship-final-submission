{#- Executive KPI trend: one row per day. Blended ROAS (MER) and blended CAC use ALL revenue / new customers vs ALL ad spend. -#}
with sess as (
    select
        session_date                                              as kpi_date,
        count(*)                                                  as sessions,
        sum(case when source_system = 'ga4' then 1 else 0 end)    as web_sessions,
        sum(case when source_system = 'segment' then 1 else 0 end) as app_sessions
    from {{ ref('fct_sessions') }}
    group by session_date
),

ord as (
    select
        order_date                                                                  as kpi_date,
        sum(case when is_conversion then 1 else 0 end)                              as orders,
        sum(case when is_conversion then net_revenue else 0 end)                    as net_revenue,
        sum(case when is_conversion and is_first_order then 1 else 0 end)           as new_customers
    from {{ ref('fct_orders') }}
    where in_tracking_window
    group by order_date
),

spend as (
    select spend_date as kpi_date, sum(cost) as ad_spend, sum(clicks) as ad_clicks
    from {{ ref('stg_ads__spend') }}
    group by spend_date
)

select
    s.kpi_date,
    s.sessions,
    s.web_sessions,
    s.app_sessions,
    coalesce(o.orders, 0)                                       as orders,
    coalesce(o.net_revenue, 0)                                  as net_revenue,
    coalesce(o.new_customers, 0)                                as new_customers,
    coalesce(sp.ad_spend, 0)                                    as ad_spend,
    coalesce(sp.ad_clicks, 0)                                   as ad_clicks,
    coalesce(o.net_revenue, 0) / nullif(coalesce(o.orders, 0), 0)            as aov,
    coalesce(o.orders, 0) * 1.0 / nullif(s.sessions, 0)                      as conversion_rate,
    coalesce(o.net_revenue, 0) / nullif(coalesce(sp.ad_spend, 0), 0)         as blended_roas,
    coalesce(sp.ad_spend, 0) / nullif(coalesce(o.new_customers, 0), 0)       as blended_cac
from sess s
left join ord o on o.kpi_date = s.kpi_date
left join spend sp on sp.kpi_date = s.kpi_date
