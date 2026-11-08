{#- Traffic + funnel by day x channel x platform (web vs app): sessions -> add to cart -> checkout -> purchase. -#}
select
    session_date,
    channel_group,
    source_system,
    count(*)                                                     as sessions,
    sum(case when has_add_to_cart = 1 then 1 else 0 end)         as add_to_cart_sessions,
    sum(case when has_checkout = 1 then 1 else 0 end)            as checkout_sessions,
    sum(case when purchases > 0 then 1 else 0 end)              as purchasing_sessions,
    sum(session_revenue)                                         as tracker_revenue
from {{ ref('fct_sessions') }}
group by session_date, channel_group, source_system
