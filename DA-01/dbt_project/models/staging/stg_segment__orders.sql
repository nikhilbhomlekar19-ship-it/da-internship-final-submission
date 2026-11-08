select
    id                                                    as message_id,
    anonymous_id,
    nullif(user_id, '')                                   as user_id,
    cast({{ adapter.quote('timestamp') }} as {{ dbt.type_timestamp() }}) as event_ts,
    order_id,
    revenue,
    total,
    currency,
    coupon
from {{ source('segment', 'order_completed') }}
