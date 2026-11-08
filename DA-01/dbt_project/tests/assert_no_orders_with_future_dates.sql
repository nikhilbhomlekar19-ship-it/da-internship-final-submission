select order_id, ordered_at from {{ ref('fct_orders') }}
where order_date > cast('{{ var("as_of_date") }}' as date)
