{#- BigQuery: partition by day and cluster by person for cheap per-person lookups. DuckDB has no such options. -#}
{% if target.type == 'bigquery' %}
{{ config(materialized='table', partition_by={'field': 'session_date', 'data_type': 'date'}, cluster_by=['person_id']) }}
{% else %}
{{ config(materialized='table') }}
{% endif %}
{#- Unified sessions: GA4 web sessions + Segment app sessions, stitched to a person through the identity graph.
    Devices that never identified themselves stay as their own anonymous "person" (person_id = anon:<device>). -#}
with sessions as (
    select * from {{ ref('int_ga4__sessions') }}
    union all
    select * from {{ ref('int_segment__sessions') }}
),

nodes as (
    select node_key, person_id, is_shared_device from {{ source('ml', 'identity_nodes') }}
),

joined as (
    select
        s.*,
        n.person_id                                       as linked_person_id,
        coalesce(n.is_shared_device, false)               as is_shared_device
    from sessions s
    left join nodes n
        on n.node_key = concat(case when s.source_system = 'ga4' then 'ga:' else 'sa:' end, s.device_id)
),

final as (
    select
        *,
        coalesce(linked_person_id, concat('anon:', device_id)) as resolved_person_id
    from joined
)

select
    session_key,
    source_system,
    device_id,
    resolved_person_id                                    as person_id,
    (linked_person_id is not null)                        as is_identified,
    is_shared_device,
    cast(session_start_ts as date)                        as session_date,
    session_start_ts,
    session_end_ts,
    {{ c360_epoch_seconds('session_end_ts') }} - {{ c360_epoch_seconds('session_start_ts') }} as duration_seconds,
    utm_source,
    utm_medium,
    utm_campaign,
    channel_group,
    campaign_key,
    platform,
    country,
    landing_page,
    event_count,
    page_views,
    item_views,
    has_add_to_cart,
    has_checkout,
    purchases,
    session_revenue,
    row_number() over (partition by resolved_person_id order by session_start_ts, session_key) as person_session_number
from final
