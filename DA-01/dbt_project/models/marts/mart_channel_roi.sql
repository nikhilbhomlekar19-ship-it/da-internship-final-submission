{#- Same metrics as mart_campaign_roi, rolled up to channel (includes channels without spend: email, organic, direct ...). -#}
{% set margin = var('gross_margin_pct') %}
with spend as (
    select
        channel_group,
        sum(cost) as spend, sum(impressions) as impressions, sum(clicks) as clicks,
        sum(platform_conversions) as platform_conversions, sum(platform_conversion_value) as platform_revenue
    from {{ ref('stg_ads__spend') }}
    group by channel_group
),

credits as (
    select
        c.model,
        c.channel_group,
        sum(c.credit)                                                                                    as attributed_orders,
        sum(case when c.is_first_order then c.credit else 0 end)                                         as attributed_new_customers,
        sum(c.credited_revenue)                                                                          as attributed_revenue,
        sum(case when c.is_first_order then c.credit * coalesce(p.predicted_clv_12m_revenue, 0) else 0 end) as new_customer_clv_credit
    from {{ ref('fct_attribution_credits') }} c
    left join {{ ref('customer_profile') }} p on p.person_id = c.person_id
    group by c.model, c.channel_group
),

joined as (
    select
        cr.model,
        cr.channel_group,
        ch.channel_type,
        coalesce(ch.is_paid, false)                     as is_paid,
        ch.sort_order,
        ch.color_hex,
        coalesce(s.spend, 0)                            as spend,
        coalesce(s.impressions, 0)                      as impressions,
        coalesce(s.clicks, 0)                           as clicks,
        coalesce(s.platform_conversions, 0)             as platform_conversions,
        coalesce(s.platform_revenue, 0)                 as platform_revenue,
        cr.attributed_orders,
        cr.attributed_new_customers,
        cr.attributed_revenue,
        cr.new_customer_clv_credit
    from credits cr
    left join spend s on s.channel_group = cr.channel_group
    left join {{ ref('channel_catalog') }} ch on ch.channel_group = cr.channel_group
)

select
    *,
    attributed_revenue * {{ margin }}                                            as gross_profit,
    attributed_revenue * {{ margin }} - spend                                    as profit_after_spend,
    attributed_revenue / nullif(spend, 0)                                        as roas,
    (attributed_revenue * {{ margin }} - spend) / nullif(spend, 0)               as roi,
    spend / nullif(attributed_orders, 0)                                         as cpa,
    spend / nullif(attributed_new_customers, 0)                                  as cac_new_customer,
    new_customer_clv_credit / nullif(attributed_new_customers, 0)                as avg_new_customer_clv,
    (new_customer_clv_credit / nullif(attributed_new_customers, 0))
        / nullif(spend / nullif(attributed_new_customers, 0), 0)                 as ltv_to_cac,
    platform_revenue / nullif(spend, 0)                                          as platform_roas,
    platform_conversions / nullif(attributed_orders, 0)                          as platform_overclaim_ratio
from joined
