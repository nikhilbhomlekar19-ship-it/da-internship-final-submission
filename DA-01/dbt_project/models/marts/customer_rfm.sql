{#- RFM scores 1-5, then the classic 10-segment grid on R and F.
    R and M: quintiles via percent_rank (tied customers get the SAME score - unlike NTILE, which splits ties arbitrarily).
    F: number of orders capped at 5 - frequency is a small integer with heavy ties, so quantiles would give 1 or 4 and nothing in between. -#}
with base as (
    select
        person_id,
        first_order_at,
        last_order_at,
        order_count                                                                    as frequency,
        net_revenue                                                                    as monetary,
        {{ c360_date_diff_days('cast(last_order_at as date)', "cast('" ~ var('as_of_date') ~ "' as date)") }} as recency_days
    from {{ ref('int_customer__orders') }}
    where order_count > 0
),

pct as (
    select
        *,
        percent_rank() over (order by recency_days desc)                               as r_pr,
        percent_rank() over (order by monetary)                                        as m_pr
    from base
),

scored as (
    select
        *,
        least(5, cast(floor(r_pr * 5) as {{ dbt.type_bigint() }}) + 1)                 as r_score,
        least(5, cast(frequency as {{ dbt.type_bigint() }}))                           as f_score,
        least(5, cast(floor(m_pr * 5) as {{ dbt.type_bigint() }}) + 1)                 as m_score
    from pct
)

select
    person_id,
    first_order_at,
    last_order_at,
    recency_days,
    frequency,
    monetary,
    r_score,
    f_score,
    m_score,
    cast(r_score as {{ dbt.type_string() }}) || cast(f_score as {{ dbt.type_string() }}) || cast(m_score as {{ dbt.type_string() }}) as rfm_code,
    case
        when r_score <= 2 and f_score <= 2 then 'Hibernating'
        when r_score <= 2 and f_score in (3, 4) then 'At Risk'
        when r_score <= 2 and f_score = 5 then 'Cant Lose Them'
        when r_score = 3 and f_score <= 2 then 'About To Sleep'
        when r_score = 3 and f_score = 3 then 'Need Attention'
        when r_score in (3, 4) and f_score >= 4 then 'Loyal Customers'
        when r_score = 4 and f_score = 1 then 'Promising'
        when r_score = 5 and f_score = 1 then 'New Customers'
        when r_score in (4, 5) and f_score in (2, 3) then 'Potential Loyalists'
        when r_score = 5 and f_score >= 4 then 'Champions'
    end                                                                                as rfm_segment,
    case when m_score >= 4 then 'High' when m_score = 3 then 'Medium' else 'Low' end   as monetary_tier
from scored
