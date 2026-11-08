{#- Campaign ROI / ROAS / CPA / CAC / LTV:CAC for every attribution model, next to what the ad platform claims.
    Costs come from the (synthetic) ad-spend table; revenue from the attribution credits; margin from var gross_margin_pct. -#}
{% set margin = var('gross_margin_pct') %}
with spend as (
    select
        campaign_key,
        max(channel_group)              as channel_group,
        max(platform)                   as platform,
        max(campaign_name)              as campaign_name,
        sum(cost)                       as spend,
        sum(impressions)                as impressions,
        sum(clicks)                     as clicks,
        sum(platform_conversions)       as platform_conversions,
        sum(platform_conversion_value)  as platform_revenue
    from {{ ref('stg_ads__spend') }}
    group by campaign_key
),

credits as (
    select
        c.model,
        c.campaign_key,
        max(c.channel_group)                                                                             as channel_group,
        sum(c.credit)                                                                                    as attributed_orders,
        sum(case when c.is_first_order then c.credit else 0 end)                                         as attributed_new_customers,
        sum(c.credited_revenue)                                                                          as attributed_revenue,
        sum(case when c.is_first_order then c.credit * coalesce(p.predicted_clv_12m_revenue, 0) else 0 end) as new_customer_clv_credit
    from {{ ref('fct_attribution_credits') }} c
    left join {{ ref('customer_profile') }} p on p.person_id = c.person_id
    group by c.model, c.campaign_key
),

keys as (
    select distinct campaign_key from (
        select campaign_key from spend
        union all
        select campaign_key from credits
    ) k
),

models as (
    select distinct model from credits
),

joined as (
    select
        k.campaign_key,
        m.model,
        coalesce(s.channel_group, cr.channel_group)          as channel_group,
        s.platform,
        s.campaign_name,
        (s.campaign_key is not null)                         as is_paid,
        coalesce(s.spend, 0)                                 as spend,
        coalesce(s.impressions, 0)                           as impressions,
        coalesce(s.clicks, 0)                                as clicks,
        coalesce(s.platform_conversions, 0)                  as platform_conversions,
        coalesce(s.platform_revenue, 0)                      as platform_revenue,
        coalesce(cr.attributed_orders, 0)                    as attributed_orders,
        coalesce(cr.attributed_new_customers, 0)             as attributed_new_customers,
        coalesce(cr.attributed_revenue, 0)                   as attributed_revenue,
        coalesce(cr.new_customer_clv_credit, 0)              as new_customer_clv_credit
    from keys k
    cross join models m
    left join spend s on s.campaign_key = k.campaign_key
    left join credits cr on cr.campaign_key = k.campaign_key and cr.model = m.model
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
    platform_conversions / nullif(attributed_orders, 0)                          as platform_overclaim_ratio,
    spend / nullif(clicks, 0)                                                    as cpc,
    clicks / nullif(impressions, 0)                                              as ctr,
    attributed_orders / nullif(clicks, 0)                                        as click_to_order_rate
from joined
