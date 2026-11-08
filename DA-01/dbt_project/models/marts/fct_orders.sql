{#- One row per CRM order (system of record), enriched with the tracking evidence (GA4 purchase / Segment Order Completed),
    the resolved person and the converting session.  Reconciliation columns show where tracking and CRM disagree. -#}
with crm as (
    select * from {{ ref('stg_crm__orders') }}
),

crm_person as (
    select node_value as crm_customer_id, person_id
    from {{ source('ml', 'identity_nodes') }}
    where node_type = 'crm'
),

ga4 as (
    select transaction_id, session_key, purchase_revenue from {{ ref('stg_ga4__purchases') }}
),

seg as (
    select o.order_id as external_ref, o.revenue as tracker_revenue, s.session_key
    from {{ ref('stg_segment__orders') }} o
    left join {{ ref('int_segment__sessions') }} s
        on s.device_id = o.anonymous_id
       and o.event_ts between s.session_start_ts and s.session_end_ts
    where true
    qualify row_number() over (partition by o.order_id order by s.session_start_ts) = 1
),

joined as (
    select
        c.order_id,
        coalesce(p.person_id, concat('crm:', c.customer_id))                  as person_id,
        c.customer_id                                                          as crm_customer_id,
        c.ordered_at,
        c.order_date,
        c.order_channel,
        c.status,
        c.gross_amount,
        c.discount_amount,
        c.paid_amount,
        c.refund_amount,
        c.net_revenue,
        c.external_ref,
        coalesce(g.session_key, sg.session_key)                                as converting_session_key,
        (g.transaction_id is not null or sg.external_ref is not null)         as is_tracked_online,
        case when c.order_channel = 'web' then g.purchase_revenue else sg.tracker_revenue end as tracker_revenue,
        (c.status = 'completed')                                               as is_conversion,
        (c.order_date >= cast('{{ var("start_date") }}' as date))              as in_tracking_window
    from crm c
    left join crm_person p on p.crm_customer_id = c.customer_id
    left join ga4 g on c.order_channel = 'web' and g.transaction_id = c.external_ref
    left join seg sg on c.order_channel = 'app' and sg.external_ref = c.external_ref
),

completed as (
    select
        order_id,
        row_number() over (partition by person_id order by ordered_at, order_id)        as customer_order_number,
        lag(order_date) over (partition by person_id order by ordered_at, order_id)     as prev_order_date
    from joined
    where is_conversion
)

select
    j.*,
    c.customer_order_number,
    coalesce(c.customer_order_number = 1, false)                                       as is_first_order,
    case when c.prev_order_date is not null
         then {{ c360_date_diff_days('c.prev_order_date', 'j.order_date') }} end       as days_since_prev_order,
    case when j.tracker_revenue is not null then abs(j.paid_amount - j.tracker_revenue) end as revenue_gap_vs_tracker
from joined j
left join completed c on c.order_id = j.order_id
