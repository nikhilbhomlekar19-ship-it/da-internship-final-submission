{{ config(materialized='table') }}
{#- One row per GA4 event with the nested event_params flattened. On BigQuery consider making this incremental
    (partition by event_date) for the full export; the public sample is small enough to rebuild. -#}
select
    {{ c360_parse_yyyymmdd('e.event_date') }}                    as event_date,
    {{ c360_ts_from_micros('e.event_timestamp') }}               as event_ts,
    e.event_name,
    e.user_pseudo_id,
    nullif(e.user_id, '')                                       as user_id,
    {{ c360_ga4_param('ga_session_id', 'int_value') }}          as ga_session_id,
    {{ c360_ga4_param('ga_session_number', 'int_value') }}      as ga_session_number,
    {{ c360_ga4_param('page_location') }}                       as page_location,
    {{ c360_ga4_param('source') }}                              as param_source,
    {{ c360_ga4_param('medium') }}                              as param_medium,
    {{ c360_ga4_param('campaign') }}                            as param_campaign,
    {{ c360_ga4_param('engagement_time_msec', 'int_value') }}   as engagement_time_msec,
    e.traffic_source.source                                     as first_user_source,
    e.traffic_source.medium                                     as first_user_medium,
    e.traffic_source.name                                       as first_user_campaign,
    e.device.category                                           as device_category,
    e.device.operating_system                                   as device_os,
    e.geo.country                                               as country,
    e.geo.city                                                  as city,
    e.ecommerce.transaction_id                                  as transaction_id,
    e.ecommerce.purchase_revenue_in_usd                         as purchase_revenue,
    e.ecommerce.total_item_quantity                             as item_quantity
from {{ source('ga4', 'events') }} as e
where e.event_date between '{{ var("start_date") | replace("-", "") }}' and '{{ var("end_date") | replace("-", "") }}'
{%- if target.type == 'bigquery' and var('use_public_ga4', true) %}
  and _table_suffix between '{{ var("start_date") | replace("-", "") }}' and '{{ var("end_date") | replace("-", "") }}'
{%- endif %}
