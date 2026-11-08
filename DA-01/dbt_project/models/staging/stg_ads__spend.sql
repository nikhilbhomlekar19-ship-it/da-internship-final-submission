select
    cast({{ adapter.quote('date') }} as date)              as spend_date,
    platform,
    account_id,
    campaign_id,
    campaign_name,
    lower(trim(utm_source))                                as utm_source,
    lower(trim(utm_medium))                                as utm_medium,
    lower(trim(utm_campaign))                              as utm_campaign,
    {{ c360_campaign_key('utm_source', 'utm_medium', 'utm_campaign') }} as campaign_key,
    {{ c360_channel_group('utm_source', 'utm_medium') }}   as channel_group,
    impressions,
    clicks,
    cost,
    platform_conversions,
    platform_conversion_value
from {{ source('ads', 'spend_daily') }}
