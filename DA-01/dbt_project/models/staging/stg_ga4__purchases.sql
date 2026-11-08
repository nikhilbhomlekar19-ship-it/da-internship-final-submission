{#- GA4 purchase events de-duplicated by transaction_id (double-fired purchase tags are common). -#}
with purchases as (
    select
        *,
        concat(user_pseudo_id, '.', cast(ga_session_id as {{ dbt.type_string() }})) as session_key
    from {{ ref('stg_ga4__events') }}
    where event_name = 'purchase'
      and transaction_id is not null
      and transaction_id <> '(not set)'
)

select
    transaction_id,
    user_pseudo_id,
    user_id,
    session_key,
    event_ts          as purchase_ts,
    purchase_revenue,
    item_quantity
from purchases
where true
qualify row_number() over (partition by transaction_id order by event_ts) = 1
