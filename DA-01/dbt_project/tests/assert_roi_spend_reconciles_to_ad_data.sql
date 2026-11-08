-- Joins in the ROI mart must not fan out or drop spend: spend per model == spend in the ad export.
with mart as (
    select model, sum(spend) as spend from {{ ref('mart_campaign_roi') }} group by model
),
src as (
    select sum(cost) as spend from {{ ref('stg_ads__spend') }}
)
select m.model, m.spend as mart_spend, s.spend as source_spend
from mart m cross join src s
where abs(m.spend - s.spend) > 0.01
