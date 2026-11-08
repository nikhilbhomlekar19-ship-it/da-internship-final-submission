{#- One row per channel, the four models side by side. share_spread_pp = how many percentage points of revenue share
    the channel "moves" depending purely on which model you believe. -#}
{% set models = ['first_touch', 'last_touch', 'linear', 'time_decay'] %}
with wide as (
    select
        channel_group,
        {% for m in models -%}
        sum(case when model = '{{ m }}' then attributed_revenue else 0 end)   as revenue_{{ m }},
        sum(case when model = '{{ m }}' then revenue_share else 0 end)        as share_{{ m }},
        max(case when model = '{{ m }}' then revenue_rank end)                as rank_{{ m }}{{ "," if not loop.last }}
        {% endfor %}
    from {{ ref('mart_attribution_by_channel') }}
    group by channel_group
)

select
    *,
    (greatest(share_first_touch, share_last_touch, share_linear, share_time_decay)
       - least(share_first_touch, share_last_touch, share_linear, share_time_decay)) * 100   as share_spread_pp,
    greatest(rank_first_touch, rank_last_touch, rank_linear, rank_time_decay)
       - least(rank_first_touch, rank_last_touch, rank_linear, rank_time_decay)             as rank_swing,
    share_first_touch - share_last_touch                                                    as first_minus_last_share
from wide
