{#- Segment identify() calls = the deterministic bridge anonymous_id <-> user_id (<-> email, <-> GA client id). -#}
select
    id                                                    as message_id,
    anonymous_id,
    nullif(user_id, '')                                   as user_id,
    cast({{ adapter.quote('timestamp') }} as {{ dbt.type_timestamp() }}) as event_ts,
    {{ c360_normalize_email('email') }}                   as email_norm,
    nullif(ga_client_id, '')                              as ga_client_id,
    context_library_name
from {{ source('segment', 'identifies') }}
