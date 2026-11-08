{#- GA4 events -> one row per web session (session_key = device id + ga_session_id).
    Session traffic source = first event that carries source/medium/campaign params, else the user's first-touch traffic_source. -#}
with events as (
    select
        *,
        concat(user_pseudo_id, '.', cast(ga_session_id as {{ dbt.type_string() }})) as session_key
    from {{ ref('stg_ga4__events') }}
    where ga_session_id is not null
),

first_event as (
    select session_key, device_category, country, first_user_source, first_user_medium, first_user_campaign
    from events
    where true
    qualify row_number() over (partition by session_key order by event_ts, event_name) = 1
),

session_traffic as (
    select session_key, param_source, param_medium, param_campaign
    from events
    where param_source is not null
    qualify row_number() over (partition by session_key order by event_ts, event_name) = 1
),

landing as (
    select session_key, page_location as landing_page
    from events
    where event_name = 'page_view'
    qualify row_number() over (partition by session_key order by event_ts, event_name) = 1
),

purchases as (
    select session_key, count(*) as purchases, sum(purchase_revenue) as session_revenue
    from {{ ref('stg_ga4__purchases') }}
    group by session_key
),

agg as (
    select
        session_key,
        min(user_pseudo_id)                                                     as device_id,
        min(event_ts)                                                           as session_start_ts,
        max(event_ts)                                                           as session_end_ts,
        count(*)                                                                as event_count,
        sum(case when event_name = 'page_view' then 1 else 0 end)               as page_views,
        sum(case when event_name = 'view_item' then 1 else 0 end)               as item_views,
        max(case when event_name = 'add_to_cart' then 1 else 0 end)             as has_add_to_cart,
        max(case when event_name = 'begin_checkout' then 1 else 0 end)          as has_checkout,
        max(user_id)                                                            as user_id_in_session
    from events
    group by session_key
),

resolved as (
    select
        a.*,
        f.device_category,
        f.country,
        l.landing_page,
        coalesce(p.purchases, 0)                                                as purchases,
        coalesce(p.session_revenue, 0)                                          as session_revenue,
        case when t.param_source is not null then t.param_source
             else coalesce(f.first_user_source, '(direct)') end                 as utm_source,
        case when t.param_source is not null then coalesce(t.param_medium, '(not set)')
             else coalesce(f.first_user_medium, '(none)') end                   as utm_medium,
        case when t.param_source is not null then coalesce(t.param_campaign, '(not set)')
             else coalesce(f.first_user_campaign, '(direct)') end               as utm_campaign
    from agg a
    left join first_event f on f.session_key = a.session_key
    left join session_traffic t on t.session_key = a.session_key
    left join landing l on l.session_key = a.session_key
    left join purchases p on p.session_key = a.session_key
)

select
    session_key,
    'ga4'                                                       as source_system,
    device_id,
    session_start_ts,
    session_end_ts,
    utm_source,
    utm_medium,
    utm_campaign,
    {{ c360_channel_group('utm_source', 'utm_medium') }}        as channel_group,
    {{ c360_campaign_key('utm_source', 'utm_medium', 'utm_campaign') }} as campaign_key,
    device_category                                             as platform,
    country,
    landing_page,
    event_count,
    page_views,
    item_views,
    has_add_to_cart,
    has_checkout,
    purchases,
    session_revenue,
    user_id_in_session
from resolved
