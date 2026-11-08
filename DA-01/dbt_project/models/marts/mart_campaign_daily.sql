{#- Daily spend next to revenue credited to the SAME day's touchpoints (credit is dated by touch, not by order),
    so cost and the revenue it produced line up. Feeds the response-curve fit in customer360/recommend.py. -#}
with spend as (
    select spend_date, campaign_key, max(channel_group) as channel_group, sum(cost) as spend, sum(clicks) as clicks, sum(impressions) as impressions
    from {{ ref('stg_ads__spend') }}
    group by spend_date, campaign_key
),

credits as (
    select touch_date, campaign_key, model, sum(credit) as attributed_orders, sum(credited_revenue) as attributed_revenue
    from {{ ref('fct_attribution_credits') }}
    where touch_date is not null
    group by touch_date, campaign_key, model
),

models as (
    select distinct model from credits
)

select
    s.spend_date,
    s.campaign_key,
    s.channel_group,
    m.model,
    s.spend,
    s.clicks,
    s.impressions,
    coalesce(c.attributed_orders, 0)    as attributed_orders,
    coalesce(c.attributed_revenue, 0)   as attributed_revenue
from spend s
cross join models m
left join credits c
    on c.touch_date = s.spend_date and c.campaign_key = s.campaign_key and c.model = m.model
