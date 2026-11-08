select
    id                                                    as message_id,
    anonymous_id,
    nullif(user_id, '')                                   as user_id,
    event                                                 as event_name,
    cast({{ adapter.quote('timestamp') }} as {{ dbt.type_timestamp() }}) as event_ts,
    context_campaign_source                               as campaign_source,
    context_campaign_medium                               as campaign_medium,
    context_campaign_name                                 as campaign_name,
    context_device_type                                   as device_type,
    context_os_name                                       as os_name
from {{ source('segment', 'tracks') }}
