{#-
  Evidence for the identity graph. Each row says "these two identifiers belong together" and why.
  Nodes are typed strings:  crm:<customer_id>  email:<normalised>  phone:<normalised>  ga:<user_pseudo_id>  sa:<segment anonymous_id>

  edge_class
    person         strong keys that identify a PERSON      (CRM record <-> email, phone)       -> always merged (dedupes CRM)
    device_device  two ids of the SAME browser/device       (Segment anonymous_id <-> GA client id)
    device_person  a device is linked to a person key       (identify(), order match, GA4 user_id) -> merged unless the device is shared
  The graph algorithm (customer360/identity.py) lives in Python because connected components are awkward in SQL.
-#}
with crm as (
    select customer_id, email_norm, phone_norm, created_at from {{ ref('stg_crm__customers') }}
),

crm_self as (
    select concat('crm:', customer_id) as node_a, concat('crm:', customer_id) as node_b,
           'crm_record' as edge_type, 'person' as edge_class,
           created_at as first_seen_at, created_at as last_seen_at, 1 as evidence_count
    from crm
),

crm_email as (
    select concat('crm:', customer_id) as node_a, concat('email:', email_norm) as node_b,
           'crm_email' as edge_type, 'person' as edge_class,
           created_at as first_seen_at, created_at as last_seen_at, 1 as evidence_count
    from crm where email_norm is not null
),

crm_phone as (
    select concat('crm:', customer_id) as node_a, concat('phone:', phone_norm) as node_b,
           'crm_phone' as edge_type, 'person' as edge_class,
           created_at as first_seen_at, created_at as last_seen_at, 1 as evidence_count
    from crm where phone_norm is not null
),

seg_user as (
    select concat('sa:', anonymous_id) as node_a, concat('crm:', user_id) as node_b,
           'segment_identify_user' as edge_type, 'device_person' as edge_class,
           min(event_ts) as first_seen_at, max(event_ts) as last_seen_at, count(*) as evidence_count
    from {{ ref('stg_segment__identifies') }}
    where user_id is not null and anonymous_id is not null
    group by 1, 2
),

seg_email as (
    select concat('sa:', anonymous_id) as node_a, concat('email:', email_norm) as node_b,
           'segment_identify_email' as edge_type, 'device_person' as edge_class,
           min(event_ts) as first_seen_at, max(event_ts) as last_seen_at, count(*) as evidence_count
    from {{ ref('stg_segment__identifies') }}
    where email_norm is not null and anonymous_id is not null
    group by 1, 2
),

seg_ga_bridge as (
    select concat('sa:', anonymous_id) as node_a, concat('ga:', ga_client_id) as node_b,
           'segment_ga_bridge' as edge_type, 'device_device' as edge_class,
           min(event_ts) as first_seen_at, max(event_ts) as last_seen_at, count(*) as evidence_count
    from {{ ref('stg_segment__identifies') }}
    where ga_client_id is not null and anonymous_id is not null
    group by 1, 2
),

ga_user as (
    select concat('ga:', user_pseudo_id) as node_a, concat('crm:', user_id) as node_b,
           'ga4_user_id' as edge_type, 'device_person' as edge_class,
           min(event_ts) as first_seen_at, max(event_ts) as last_seen_at, count(*) as evidence_count
    from {{ ref('stg_ga4__events') }}
    where user_id is not null and user_pseudo_id is not null
    group by 1, 2
),

order_web as (
    select concat('ga:', p.user_pseudo_id) as node_a, concat('crm:', o.customer_id) as node_b,
           'order_match_web' as edge_type, 'device_person' as edge_class,
           min(p.purchase_ts) as first_seen_at, max(p.purchase_ts) as last_seen_at, count(*) as evidence_count
    from {{ ref('stg_ga4__purchases') }} p
    join {{ ref('stg_crm__orders') }} o on o.external_ref = p.transaction_id and o.order_channel = 'web'
    group by 1, 2
),

order_app as (
    select concat('sa:', s.anonymous_id) as node_a, concat('crm:', o.customer_id) as node_b,
           'order_match_app' as edge_type, 'device_person' as edge_class,
           min(s.event_ts) as first_seen_at, max(s.event_ts) as last_seen_at, count(*) as evidence_count
    from {{ ref('stg_segment__orders') }} s
    join {{ ref('stg_crm__orders') }} o on o.external_ref = s.order_id and o.order_channel = 'app'
    group by 1, 2
)

select * from crm_self
union all select * from crm_email
union all select * from crm_phone
union all select * from seg_user
union all select * from seg_email
union all select * from seg_ga_bridge
union all select * from ga_user
union all select * from order_web
union all select * from order_app
