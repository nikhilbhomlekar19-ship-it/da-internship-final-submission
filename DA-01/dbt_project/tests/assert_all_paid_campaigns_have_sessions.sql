{{ config(severity='warn') }}
-- Data-quality alert (warn): a campaign with spend but no sessions usually means a UTM naming mismatch.
select s.campaign_key, sum(s.cost) as spend
from {{ ref('stg_ads__spend') }} s
left join (select distinct campaign_key from {{ ref('fct_sessions') }}) f on f.campaign_key = s.campaign_key
where f.campaign_key is null
group by s.campaign_key
