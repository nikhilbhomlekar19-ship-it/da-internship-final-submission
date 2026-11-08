-- Every attribution model must hand out exactly 100% of an order's credit.
select model, order_id, sum(credit) as total_credit
from {{ ref('fct_attribution_credits') }}
group by model, order_id
having abs(sum(credit) - 1) > 0.000001
