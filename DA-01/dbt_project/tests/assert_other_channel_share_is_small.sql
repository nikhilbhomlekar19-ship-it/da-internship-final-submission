{{ config(severity='warn') }}
-- Data-quality alert (warn): if >5% of sessions fall in "Other", extend the c360_channel_group macro.
select count(*) as sessions,
       sum(case when channel_group = 'Other' then 1 else 0 end) * 1.0 / count(*) as other_share
from {{ ref('fct_sessions') }}
having sum(case when channel_group = 'Other' then 1 else 0 end) * 1.0 / count(*) > 0.05
