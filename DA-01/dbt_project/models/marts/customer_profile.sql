{#- Customer 360: one row per resolved person that exists in the CRM. Everything we know about them in one place:
    who they are, how they behave on web + app, what they buy, how valuable they are and which segment they fall in. -#}
{% set asof = "cast('" ~ var('as_of_date') ~ "' as date)" %}

with crm_person as (
    select node_value as crm_customer_id, person_id
    from {{ source('ml', 'identity_nodes') }}
    where node_type = 'crm'
),

crm as (
    select
        p.person_id,
        c.*,
        row_number() over (partition by p.person_id order by c.created_at, c.customer_id) as rn,
        count(*) over (partition by p.person_id)                                          as crm_record_count
    from {{ ref('stg_crm__customers') }} c
    join crm_person p on p.crm_customer_id = c.customer_id
),

primary_crm as (
    select * from crm where rn = 1
),

sess as (
    select
        person_id,
        count(*)                                                                    as total_sessions,
        sum(case when source_system = 'ga4' then 1 else 0 end)                      as web_sessions,
        sum(case when source_system = 'segment' then 1 else 0 end)                  as app_sessions,
        count(distinct device_id)                                                   as distinct_devices,
        min(session_start_ts)                                                       as first_session_at,
        max(session_start_ts)                                                       as last_session_at,
        max(case when is_shared_device then 1 else 0 end)                           as uses_shared_device
    from {{ ref('fct_sessions') }}
    where is_identified
    group by person_id
),

first_sess as (
    select person_id, channel_group as first_session_channel, campaign_key as first_session_campaign_key
    from {{ ref('fct_sessions') }}
    where is_identified
    qualify row_number() over (partition by person_id order by session_start_ts, session_key) = 1
),

base as (
    select
        c.person_id,
        c.customer_id                                                               as primary_crm_customer_id,
        c.crm_record_count,
        c.email_hash,
        c.first_name,
        c.country_code,
        c.city,
        c.created_at                                                                as signup_at,
        c.marketing_opt_in,
        c.loyalty_tier,
        c.self_reported_source,
        c.signup_channel,
        coalesce(s.total_sessions, 0)                                               as total_sessions,
        coalesce(s.web_sessions, 0)                                                 as web_sessions,
        coalesce(s.app_sessions, 0)                                                 as app_sessions,
        coalesce(s.distinct_devices, 0)                                             as distinct_devices,
        s.first_session_at,
        s.last_session_at,
        (coalesce(s.app_sessions, 0) > 0)                                           as is_app_user,
        (coalesce(s.distinct_devices, 0) > 1)                                       as is_multi_device,
        (coalesce(s.uses_shared_device, 0) = 1)                                     as uses_shared_device,
        coalesce(o.order_count, 0)                                                  as order_count,
        coalesce(o.return_count, 0)                                                 as return_count,
        coalesce(o.net_revenue, 0)                                                  as historical_clv_revenue,
        coalesce(o.net_revenue, 0) * {{ var('gross_margin_pct') }}                  as historical_clv_profit,
        o.avg_order_value,
        o.first_order_at,
        o.last_order_at,
        coalesce(o.web_orders, 0)                                                   as web_orders,
        coalesce(o.app_orders, 0)                                                   as app_orders,
        coalesce(o.store_orders, 0)                                                 as store_orders,
        case when o.last_order_at is not null
             then {{ c360_date_diff_days('cast(o.last_order_at as date)', asof) }} end   as recency_days,
        case when o.first_order_at is not null
             then {{ c360_date_diff_days('cast(o.first_order_at as date)', asof) }} end  as days_since_first_order,
        case
            when o.first_order_at is null then 'Unknown'
            when cast(o.first_order_at as date) < cast('{{ var("start_date") }}' as date) then 'Pre-tracking (existing customer)'
            else coalesce(fs.first_session_channel, 'Untracked (no linked session)')
        end                                                                         as acquisition_channel,
        fs.first_session_campaign_key,
        r.r_score,
        r.f_score,
        r.m_score,
        r.rfm_code,
        r.rfm_segment,
        r.monetary_tier,
        f.p_alive,
        f.predicted_orders_12m,
        f.predicted_aov,
        coalesce(f.clv_12m_revenue, 0)                                              as predicted_clv_12m_revenue,
        coalesce(f.clv_12m_revenue, 0) * {{ var('gross_margin_pct') }}              as predicted_clv_12m_profit
    from primary_crm c
    left join sess s on s.person_id = c.person_id
    left join first_sess fs on fs.person_id = c.person_id
    left join {{ ref('int_customer__orders') }} o on o.person_id = c.person_id
    left join {{ ref('customer_rfm') }} r on r.person_id = c.person_id
    left join {{ source('ml', 'clv_forecast') }} f on f.person_id = c.person_id
),

scored as (
    select
        *,
        historical_clv_revenue + predicted_clv_12m_revenue                          as total_clv_revenue,
        case when order_count > 0
             then percent_rank() over (partition by (case when order_count > 0 then 1 else 0 end)
                                       order by historical_clv_revenue + predicted_clv_12m_revenue) end as clv_percentile
    from base
)

select
    *,
    case
        when clv_percentile is null then 'No orders'
        when clv_percentile >= 0.95 then 'Platinum'
        when clv_percentile >= 0.80 then 'Gold'
        when clv_percentile >= 0.50 then 'Silver'
        else 'Bronze'
    end                                                                             as clv_tier,
    case
        when order_count = 0 then 'Prospect'
        when days_since_first_order <= 30 then 'New'
        when recency_days <= 90 and coalesce(p_alive, 1) >= 0.5 then 'Active'
        when recency_days <= 180 and coalesce(p_alive, 1) >= 0.25 then 'At Risk'
        else 'Churned'
    end                                                                             as lifecycle_stage
from scored
