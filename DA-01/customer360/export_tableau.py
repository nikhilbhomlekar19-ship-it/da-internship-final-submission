"""CSV extracts for Tableau (Tableau Public / Desktop without a BigQuery licence).  With BigQuery, connect Tableau directly instead."""
from __future__ import annotations

from . import config as cfg
from .warehouse import Warehouse

MARTS = ["mart_attribution_by_channel", "mart_attribution_comparison", "mart_campaign_roi", "mart_channel_roi", "mart_campaign_daily",
         "mart_daily_kpis", "mart_sessions_by_channel_daily", "customer_rfm"]
ML = ["budget_recommendations", "response_curves"]
PROFILE_COLS = """person_id, crm_record_count, country_code, city, signup_at, marketing_opt_in, loyalty_tier, self_reported_source, signup_channel,
    total_sessions, web_sessions, app_sessions, distinct_devices, first_session_at, last_session_at, is_app_user, is_multi_device, uses_shared_device,
    order_count, return_count, historical_clv_revenue, avg_order_value, first_order_at, last_order_at, web_orders, app_orders, store_orders,
    recency_days, days_since_first_order, acquisition_channel, r_score, f_score, m_score, rfm_code, rfm_segment, monetary_tier, p_alive,
    predicted_orders_12m, predicted_aov, predicted_clv_12m_revenue, predicted_clv_12m_profit, total_clv_revenue, clv_percentile, clv_tier, lifecycle_stage"""


def run() -> None:
    cfg.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with Warehouse() as wh:
        for t in MARTS:
            wh.query(f"select * from {wh.fq(cfg.dbt_schema('marts'), t)}").to_csv(cfg.EXPORT_DIR / f"{t}.csv", index=False)
        for t in ML:
            wh.query(f"select * from {wh.fq(cfg.ML_SCHEMA, t)}").to_csv(cfg.EXPORT_DIR / f"{t}.csv", index=False)
        # PII-safe customer table (no name / e-mail / phone)
        wh.query(f"select {PROFILE_COLS} from {wh.fq(cfg.dbt_schema('marts'), 'customer_profile')}").to_csv(cfg.EXPORT_DIR / "customer_profile.csv", index=False)
        wh.query(f"select * from {wh.fq(cfg.dbt_schema('staging'), 'channel_catalog')}").to_csv(cfg.EXPORT_DIR / "channel_catalog.csv", index=False)
    print(f"Wrote {len(list(cfg.EXPORT_DIR.glob('*.csv')))} CSV files to {cfg.EXPORT_DIR}")
