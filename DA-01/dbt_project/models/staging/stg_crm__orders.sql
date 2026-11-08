with src as (
    select
        order_id,
        customer_id,
        cast(ordered_at as {{ dbt.type_timestamp() }})     as ordered_at,
        lower(order_channel)                               as order_channel,
        lower(status)                                      as status,
        order_total                                        as gross_amount,
        coalesce(discount_amount, 0)                       as discount_amount,
        coalesce(refund_amount, 0)                         as refund_amount,
        external_ref,
        coupon_code,
        items_count
    from {{ source('crm', 'orders') }}
)

select
    *,
    cast(ordered_at as date)                               as order_date,
    gross_amount - discount_amount                         as paid_amount,
    case when gross_amount - discount_amount - refund_amount > 0
         then gross_amount - discount_amount - refund_amount else 0 end as net_revenue
from src
