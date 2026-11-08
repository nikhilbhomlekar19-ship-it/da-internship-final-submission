select person_id, count(*) as first_orders
from {{ ref('fct_orders') }}
where is_first_order
group by person_id
having count(*) > 1
