{#- Long format: one row per (attribution model, order, touchpoint). This is the table every attribution / ROI mart reads. -#}
{% set models = ['first_touch', 'last_touch', 'linear', 'time_decay'] %}
{% for m in models %}
select
    '{{ m }}'                                              as model,
    order_id,
    person_id,
    ordered_at,
    order_date,
    session_start_ts                                       as touch_ts,
    touch_date,
    coalesce(touch_date, order_date)                       as credit_date,
    session_key,
    source_system,
    channel_group,
    campaign_key,
    touch_position,
    touch_count,
    hours_before_conversion,
    credit_{{ m }}                                         as credit,
    net_revenue,
    credit_{{ m }} * net_revenue                           as credited_revenue,
    is_first_order
from {{ ref('int_attribution__paths') }}
{% if not loop.last %}union all{% endif %}
{% endfor %}
