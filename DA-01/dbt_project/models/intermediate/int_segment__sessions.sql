{#- Segment has no session concept: build one with the classic gap rule (new session after N minutes of inactivity).
    Campaign context (UTM / deep link / push) is read from the first event in the session that carries it. -#}
with tracks as (
    select * from {{ ref('stg_segment__tracks') }} where anonymous_id is not null
),

gaps as (
    select
        *,
        lag(event_ts) over (partition by anonymous_id order by event_ts, message_id) as prev_ts
    from tracks
),

flagged as (
    select
        *,
        case when prev_ts is null
               or ({{ c360_epoch_seconds('event_ts') }} - {{ c360_epoch_seconds('prev_ts') }}) > {{ var('session_timeout_minutes') }} * 60
             then 1 else 0 end as is_new_session
    from gaps
),

numbered as (
    select
        *,
        sum(is_new_session) over (partition by anonymous_id order by event_ts, message_id
                                  rows between unbounded preceding and current row) as session_number
    from flagged
),

keyed as (
    select *, min(event_ts) over (partition by anonymous_id, session_number) as session_start_ts
    from numbered
),

with_key as (
    select
        *,
        concat(anonymous_id, '.', cast({{ c360_epoch_seconds('session_start_ts') }} as {{ dbt.type_string() }})) as session_key
    from keyed
),

campaign as (
    select session_key, campaign_source, campaign_medium, campaign_name
    from with_key
    where campaign_source is not null
    qualify row_number() over (partition by session_key order by event_ts, message_id) = 1
),

agg as (
    select
        session_key,
        min(anonymous_id)                                                       as device_id,
        min(event_ts)                                                           as session_start_ts,
        max(event_ts)                                                           as session_end_ts,
        count(*)                                                                as event_count,
        sum(case when event_name = 'Application Opened' then 1 else 0 end)      as page_views,
        sum(case when event_name = 'Product Viewed' then 1 else 0 end)          as item_views,
        max(case when event_name = 'Product Added' then 1 else 0 end)           as has_add_to_cart,
        max(case when event_name = 'Checkout Started' then 1 else 0 end)        as has_checkout,
        sum(case when event_name = 'Order Completed' then 1 else 0 end)         as purchases,
        max(user_id)                                                            as user_id_in_session,
        max(os_name)                                                            as platform
    from with_key
    group by session_key
),

revenue as (
    select a.session_key, sum(o.revenue) as session_revenue
    from agg a
    join {{ ref('stg_segment__orders') }} o
      on o.anonymous_id = a.device_id
     and o.event_ts between a.session_start_ts and a.session_end_ts
    group by a.session_key
),

resolved as (
    select
        a.*,
        coalesce(r.session_revenue, 0)                          as session_revenue,
        coalesce(c.campaign_source, '(direct)')                 as utm_source,
        coalesce(c.campaign_medium, '(none)')                   as utm_medium,
        coalesce(c.campaign_name, '(direct)')                   as utm_campaign
    from agg a
    left join campaign c on c.session_key = a.session_key
    left join revenue r on r.session_key = a.session_key
)

select
    session_key,
    'segment'                                                   as source_system,
    device_id,
    session_start_ts,
    session_end_ts,
    utm_source,
    utm_medium,
    utm_campaign,
    {{ c360_channel_group('utm_source', 'utm_medium') }}        as channel_group,
    {{ c360_campaign_key('utm_source', 'utm_medium', 'utm_campaign') }} as campaign_key,
    platform,
    cast(null as {{ dbt.type_string() }})                       as country,
    cast(null as {{ dbt.type_string() }})                       as landing_page,
    event_count,
    page_views,
    item_views,
    has_add_to_cart,
    has_checkout,
    purchases,
    session_revenue,
    user_id_in_session
from resolved
