select
    customer_id,
    trim(first_name)                                       as first_name,
    trim(last_name)                                        as last_name,
    {{ c360_normalize_email('email') }}                    as email_norm,
    {{ c360_md5(c360_normalize_email('email')) }}          as email_hash,
    {{ c360_normalize_phone('phone') }}                    as phone_norm,
    upper(country)                                         as country_code,
    city,
    cast(created_at as {{ dbt.type_timestamp() }})         as created_at,
    marketing_opt_in,
    loyalty_tier,
    self_reported_source,
    signup_channel
from {{ source('crm', 'customers') }}
