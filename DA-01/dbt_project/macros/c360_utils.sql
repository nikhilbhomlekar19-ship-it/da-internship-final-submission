{#
  Warehouse-specific building blocks. Every model is written against these macros so the SAME project
  runs on BigQuery (production, real GA4 export) and DuckDB (local demo, GA4-shaped synthetic data).
  `adapter.dispatch` picks bigquery__<macro> or duckdb__<macro> at compile time.
#}

{# ---- GA4 event_params extraction -------------------------------------------------------------- #}
{% macro c360_ga4_param(key, value_type='string_value', alias='e') -%}
  {{ return(adapter.dispatch('c360_ga4_param', 'customer360')(key, value_type, alias)) }}
{%- endmacro %}
{% macro bigquery__c360_ga4_param(key, value_type, alias) -%}
  (select ep.value.{{ value_type }} from unnest({{ alias }}.event_params) as ep where ep.key = '{{ key }}')
{%- endmacro %}
{% macro duckdb__c360_ga4_param(key, value_type, alias) -%}
  list_filter({{ alias }}.event_params, lambda p: p.key = '{{ key }}')[1].value.{{ value_type }}
{%- endmacro %}

{# ---- time helpers ------------------------------------------------------------------------------ #}
{% macro c360_ts_from_micros(col) -%}
  {{ return(adapter.dispatch('c360_ts_from_micros', 'customer360')(col)) }}
{%- endmacro %}
{% macro bigquery__c360_ts_from_micros(col) -%}timestamp_micros({{ col }}){%- endmacro %}
{% macro duckdb__c360_ts_from_micros(col) -%}make_timestamp({{ col }}){%- endmacro %}

{% macro c360_parse_yyyymmdd(col) -%}
  {{ return(adapter.dispatch('c360_parse_yyyymmdd', 'customer360')(col)) }}
{%- endmacro %}
{% macro bigquery__c360_parse_yyyymmdd(col) -%}parse_date('%Y%m%d', {{ col }}){%- endmacro %}
{% macro duckdb__c360_parse_yyyymmdd(col) -%}cast(strptime({{ col }}, '%Y%m%d') as date){%- endmacro %}

{% macro c360_epoch_seconds(ts) -%}
  {{ return(adapter.dispatch('c360_epoch_seconds', 'customer360')(ts)) }}
{%- endmacro %}
{% macro bigquery__c360_epoch_seconds(ts) -%}unix_seconds({{ ts }}){%- endmacro %}
{% macro duckdb__c360_epoch_seconds(ts) -%}cast(floor(epoch({{ ts }})) as bigint){%- endmacro %}

{# whole days from date a to date b (b - a) #}
{% macro c360_date_diff_days(a, b) -%}
  {{ return(adapter.dispatch('c360_date_diff_days', 'customer360')(a, b)) }}
{%- endmacro %}
{% macro bigquery__c360_date_diff_days(a, b) -%}date_diff({{ b }}, {{ a }}, day){%- endmacro %}
{% macro duckdb__c360_date_diff_days(a, b) -%}date_diff('day', {{ a }}, {{ b }}){%- endmacro %}

{# ts minus a literal number of days #}
{% macro c360_ts_sub_days(ts, n) -%}
  {{ return(adapter.dispatch('c360_ts_sub_days', 'customer360')(ts, n)) }}
{%- endmacro %}
{% macro bigquery__c360_ts_sub_days(ts, n) -%}timestamp_sub({{ ts }}, interval {{ n }} day){%- endmacro %}
{% macro duckdb__c360_ts_sub_days(ts, n) -%}({{ ts }} - interval {{ n }} day){%- endmacro %}

{# ---- strings / types / hashing ----------------------------------------------------------------- #}
{% macro c360_regexp_replace_all(col, pattern, replacement) -%}
  {{ return(adapter.dispatch('c360_regexp_replace_all', 'customer360')(col, pattern, replacement)) }}
{%- endmacro %}
{% macro bigquery__c360_regexp_replace_all(col, pattern, replacement) -%}regexp_replace({{ col }}, r'{{ pattern }}', '{{ replacement }}'){%- endmacro %}
{% macro duckdb__c360_regexp_replace_all(col, pattern, replacement) -%}regexp_replace({{ col }}, '{{ pattern }}', '{{ replacement }}', 'g'){%- endmacro %}

{% macro c360_float() -%}
  {{ return(adapter.dispatch('c360_float', 'customer360')()) }}
{%- endmacro %}
{% macro bigquery__c360_float() -%}float64{%- endmacro %}
{% macro duckdb__c360_float() -%}double{%- endmacro %}

{% macro c360_md5(col) -%}
  {{ return(adapter.dispatch('c360_md5', 'customer360')(col)) }}
{%- endmacro %}
{% macro bigquery__c360_md5(col) -%}to_hex(md5({{ col }})){%- endmacro %}
{% macro duckdb__c360_md5(col) -%}md5({{ col }}){%- endmacro %}

{# ---- identity-resolution normalisers (SAME rules for CRM and Segment) ------------------------- #}
{% macro c360_normalize_email(col) -%}
  {%- set e = "lower(trim(" ~ col ~ "))" -%}
  {%- set local_part = dbt.split_part(dbt.split_part(e, "'@'", 1), "'+'", 1) -%}
  {%- set dom_raw = dbt.split_part(e, "'@'", 2) -%}
  {%- set dom = "(case when " ~ dom_raw ~ " = 'googlemail.com' then 'gmail.com' else " ~ dom_raw ~ " end)" -%}
  case
    when {{ col }} is null or strpos({{ e }}, '@') = 0 then null
    when {{ dom }} = 'gmail.com' then concat(replace({{ local_part }}, '.', ''), '@', {{ dom }})
    else concat({{ local_part }}, '@', {{ dom }})
  end
{%- endmacro %}

{% macro c360_normalize_phone(col) -%}
  {%- set digits = c360_regexp_replace_all(col, '[^0-9]', '') -%}
  case when length({{ digits }}) >= 10 then right({{ digits }}, 10) else null end
{%- endmacro %}

{# ---- marketing taxonomy ------------------------------------------------------------------------ #}
{# Simplified GA4 default channel grouping. Order matters: first match wins. #}
{% macro c360_channel_group(source, medium) -%}
  case
    when lower({{ source }}) = '(direct)' and ({{ medium }} is null or lower({{ medium }}) in ('(none)', '(not set)')) then 'Direct'
    when lower({{ medium }}) in ('paid_social', 'paidsocial', 'social_paid', 'cpc')
         and lower({{ source }}) in ('facebook', 'instagram', 'tiktok', 'linkedin', 'twitter', 'pinterest', 'snapchat', 'meta') then 'Paid Social'
    when lower({{ medium }}) in ('cpc', 'ppc', 'paidsearch', 'paid_search') then 'Paid Search'
    when lower({{ medium }}) in ('display', 'cpm', 'banner', 'programmatic') then 'Display'
    when lower({{ medium }}) = 'affiliate' then 'Affiliate'
    when lower({{ medium }}) in ('email', 'e-mail', 'newsletter') then 'Email'
    when lower({{ medium }}) in ('push', 'app_push', 'notification') then 'App Push'
    when lower({{ medium }}) = 'organic' then 'Organic Search'
    when lower({{ medium }}) in ('social', 'social_organic', 'social-network', 'social-media') then 'Organic Social'
    when lower({{ medium }}) = 'referral' then 'Referral'
    else 'Other'
  end
{%- endmacro %}

{# key that joins sessions to ad-spend rows #}
{% macro c360_campaign_key(source, medium, campaign) -%}
  concat(lower(trim(coalesce({{ source }}, '(not set)'))), '|', lower(trim(coalesce({{ medium }}, '(not set)'))), '|', lower(trim(coalesce({{ campaign }}, '(not set)'))))
{%- endmacro %}
