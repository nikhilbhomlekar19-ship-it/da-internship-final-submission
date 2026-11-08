{#-
  Conversion paths + the four attribution weights, one row per (order, touchpoint).

  conversion  = a completed CRM order inside the tracking window
  touchpoint  = any session of the same PERSON (web + app, all devices linked by the identity graph) that started
                at most `attribution_lookback_days` before the order and not after it
  direct_policy
      deprioritize (default): a Direct session only gets credit when the path has no other channel
                              ("last non-direct click" - the convention in GA4 / ad platforms)
      include               : Direct competes like any other channel

  first_touch  100% to the first touchpoint        last_touch  100% to the last touchpoint
  linear       1/n each                            time_decay  weight = 0.5 ^ (hours_before_order / half_life), normalised to 1
  Orders without any tracked touchpoint go 100% to the pseudo-channel "Unattributed" so totals always reconcile to revenue.
-#}
{% set lookback = var('attribution_lookback_days') %}
{% set half_life_hours = var('time_decay_half_life_days') * 24 %}

with conversions as (
    select order_id, person_id, ordered_at, order_date, net_revenue, is_first_order
    from {{ ref('fct_orders') }}
    where is_conversion and in_tracking_window
),

touches as (
    select
        c.order_id, c.person_id, c.ordered_at, c.order_date, c.net_revenue, c.is_first_order,
        s.session_key, s.session_start_ts, s.session_date as touch_date,
        s.channel_group, s.campaign_key, s.source_system,
        cast({{ c360_epoch_seconds('c.ordered_at') }} - {{ c360_epoch_seconds('s.session_start_ts') }} as {{ c360_float() }}) / 3600 as hours_before_conversion
    from conversions c
    join {{ ref('fct_sessions') }} s
      on s.person_id = c.person_id
     and s.session_start_ts <= c.ordered_at
     and s.session_start_ts >= {{ c360_ts_sub_days('c.ordered_at', lookback) }}
),

flagged as (
    select
        *,
        max(case when channel_group <> 'Direct' then 1 else 0 end) over (partition by order_id) as has_non_direct
    from touches
),

eligible as (
    select * from flagged
    {%- if var('direct_policy') != 'include' %}
    where channel_group <> 'Direct' or has_non_direct = 0
    {%- endif %}
),

ranked as (
    select
        *,
        row_number() over (partition by order_id order by session_start_ts, session_key) as touch_position,
        count(*) over (partition by order_id)                                          as touch_count,
        power(0.5, hours_before_conversion / {{ half_life_hours }})                    as decay_weight
    from eligible
),

credited as (
    select
        order_id, person_id, ordered_at, order_date, net_revenue, is_first_order,
        session_key, session_start_ts, touch_date, channel_group, campaign_key, source_system,
        touch_position, touch_count, hours_before_conversion,
        case when touch_position = 1 then cast(1 as {{ c360_float() }}) else cast(0 as {{ c360_float() }}) end           as credit_first_touch,
        case when touch_position = touch_count then cast(1 as {{ c360_float() }}) else cast(0 as {{ c360_float() }}) end as credit_last_touch,
        cast(1 as {{ c360_float() }}) / touch_count                                                                       as credit_linear,
        decay_weight / sum(decay_weight) over (partition by order_id)                                                    as credit_time_decay
    from ranked
),

unattributed as (
    select
        c.order_id, c.person_id, c.ordered_at, c.order_date, c.net_revenue, c.is_first_order,
        cast(null as {{ dbt.type_string() }})        as session_key,
        cast(null as {{ dbt.type_timestamp() }})     as session_start_ts,
        cast(null as date)                           as touch_date,
        'Unattributed'                               as channel_group,
        '(unattributed)'                             as campaign_key,
        'none'                                       as source_system,
        1                                            as touch_position,
        1                                            as touch_count,
        cast(0 as {{ c360_float() }})                as hours_before_conversion,
        cast(1 as {{ c360_float() }})                as credit_first_touch,
        cast(1 as {{ c360_float() }})                as credit_last_touch,
        cast(1 as {{ c360_float() }})                as credit_linear,
        cast(1 as {{ c360_float() }})                as credit_time_decay
    from conversions c
    where not exists (select 1 from credited x where x.order_id = c.order_id)
)

select * from credited
union all
select * from unattributed
