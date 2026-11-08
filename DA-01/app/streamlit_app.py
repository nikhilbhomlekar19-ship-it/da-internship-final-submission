"""Demo app - runs on the local DuckDB build or on BigQuery (same marts, same code):

    streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from customer360 import config as cfg  # noqa: E402
from customer360.warehouse import Warehouse  # noqa: E402

DEMO_DB = Path(__file__).resolve().parent / "demo.duckdb"
if cfg.TARGET == "duckdb" and not cfg.DUCKDB_PATH.exists() and DEMO_DB.exists():
    cfg.DUCKDB_PATH = DEMO_DB  # slim copy shipped with the repo: lets the demo run without the pipeline

st.set_page_config(page_title="Customer 360 & Marketing Attribution", layout="wide")
MARTS, ML = cfg.dbt_schema("marts"), cfg.ML_SCHEMA
MODELS = {"first_touch": "First touch", "last_touch": "Last touch", "linear": "Linear", "time_decay": "Time decay"}


@st.cache_data(ttl=600, show_spinner=False)
def q(sql: str) -> pd.DataFrame:
    with Warehouse(read_only=True) if cfg.TARGET == "duckdb" else Warehouse() as wh:
        return wh.query(sql)


def t(schema: str, table: str) -> str:
    return f"{schema}.{table}" if cfg.TARGET == "duckdb" else f"`{cfg.GCP_PROJECT}.{schema}.{table}`"


def money(x) -> str:
    return f"${x:,.0f}"


st.sidebar.title("Customer 360 + Attribution")
st.sidebar.caption(f"Target: **{cfg.TARGET}**  |  {cfg.START_DATE} to {cfg.END_DATE}")
page = st.sidebar.radio("Page", ["Overview", "Attribution models", "Campaign ROI", "Budget recommendation", "Customer 360", "Data quality"])

if page == "Overview":
    k = q(f"select * from {t(MARTS, 'mart_daily_kpis')} order by kpi_date")
    rev, spend, orders, newc = k.net_revenue.sum(), k.ad_spend.sum(), k.orders.sum(), k.new_customers.sum()
    c = st.columns(5)
    c[0].metric("Net revenue", money(rev))
    c[1].metric("Orders", f"{int(orders):,}")
    c[2].metric("Ad spend", money(spend))
    c[3].metric("Blended ROAS", f"{rev / spend:.2f}x")
    c[4].metric("Blended CAC", money(spend / max(newc, 1)))
    st.subheader("Daily revenue vs ad spend")
    st.line_chart(k.set_index("kpi_date")[["net_revenue", "ad_spend"]])
    st.subheader("Traffic mix by channel")
    s = q(f"select channel_group, sum(sessions) as sessions from {t(MARTS, 'mart_sessions_by_channel_daily')} group by 1 order by 2 desc")
    st.bar_chart(s.set_index("channel_group"))

elif page == "Attribution models":
    sel = st.multiselect("Models", list(MODELS), default=list(MODELS), format_func=MODELS.get)
    d = q(f"select model, channel_group, revenue_share, attributed_revenue from {t(MARTS, 'mart_attribution_by_channel')}")
    d = d[d.model.isin(sel)].assign(model_label=lambda x: x.model.map(MODELS))
    st.altair_chart(alt.Chart(d).mark_bar().encode(y=alt.Y("channel_group:N", sort="-x", title=None), x=alt.X("revenue_share:Q", axis=alt.Axis(format="%"), title="Share of attributed revenue"),
                                                   yOffset="model_label:N", color=alt.Color("model_label:N", title="Model")).properties(height=420), use_container_width=True)
    comp = q(f"select channel_group, share_first_touch, share_last_touch, share_linear, share_time_decay, share_spread_pp, rank_swing from {t(MARTS, 'mart_attribution_comparison')} order by share_spread_pp desc")
    st.dataframe(comp.style.format({c: "{:.1%}" for c in comp.columns if c.startswith("share_") and c != "share_spread_pp"} | {"share_spread_pp": "{:.1f}"}), use_container_width=True)
    st.caption("share_spread_pp = percentage points of revenue share a channel moves just by changing the model.")

elif page == "Campaign ROI":
    m = st.selectbox("Attribution model", list(MODELS), index=3, format_func=MODELS.get)
    d = q(f"select campaign_key, channel_group, spend, attributed_orders, attributed_revenue, roas, roi, cpa, cac_new_customer, ltv_to_cac, platform_roas "
          f"from {t(MARTS, 'mart_campaign_roi')} where is_paid and model = '{m}' order by spend desc")
    st.dataframe(d.style.format({"spend": "${:,.0f}", "attributed_revenue": "${:,.0f}", "attributed_orders": "{:,.0f}", "roas": "{:.2f}", "roi": "{:.0%}", "cpa": "${:,.0f}",
                                 "cac_new_customer": "${:,.0f}", "ltv_to_cac": "{:.2f}", "platform_roas": "{:.2f}"}), use_container_width=True)
    base = alt.Chart(d)
    pts = base.mark_circle(size=140).encode(x=alt.X("spend:Q", title="Ad spend"), y=alt.Y("attributed_revenue:Q", title="Attributed revenue"), color="channel_group:N", tooltip=["campaign_key", "roas", "cpa"])
    st.altair_chart(pts.properties(height=380), use_container_width=True)
    st.caption(f"Break-even ROAS on gross profit = 1 / {cfg.GROSS_MARGIN:.2f} = {1 / cfg.GROSS_MARGIN:.2f}. Platform ROAS is what the ad platform claims on its own.")

elif page == "Budget recommendation":
    r = q(f"select campaign_key, channel_group, action, confidence, current_spend, recommended_spend, change_pct, roas_median, last_vs_first_touch_ratio, beta_median, note "
          f"from {t(ML, 'budget_recommendations')} order by change_pct desc")
    st.dataframe(r.style.format({"current_spend": "${:,.0f}", "recommended_spend": "${:,.0f}", "change_pct": "{:+.1%}", "roas_median": "{:.2f}", "last_vs_first_touch_ratio": "{:.2f}", "beta_median": "{:.2f}"}), use_container_width=True)
    st.altair_chart(alt.Chart(r).mark_bar().encode(y=alt.Y("campaign_key:N", sort="-x", title=None), x=alt.X("change_pct:Q", axis=alt.Axis(format="%"), title="Recommended change in spend"),
                                                   color=alt.Color("action:N", scale=alt.Scale(domain=["Scale up", "Cut / reallocate", "Maintain", "Test incrementality"], range=["#2ca02c", "#d62728", "#7f7f7f", "#ff9f1c"]))).properties(height=380), use_container_width=True)
    st.info("Campaigns marked *Test incrementality* have last-touch ROAS more than 2x (or less than 0.5x) first-touch ROAS: attribution alone cannot decide - run a holdout / geo-lift test.")

elif page == "Customer 360":
    seg = q(f"select rfm_segment, count(*) as customers, sum(monetary) as revenue from {t(MARTS, 'customer_rfm')} group by 1 order by 3 desc")
    a, b = st.columns(2)
    a.subheader("RFM segments")
    a.bar_chart(seg.set_index("rfm_segment")[["customers"]])
    tiers = q(f"select clv_tier, lifecycle_stage, count(*) as customers from {t(MARTS, 'customer_profile')} group by 1, 2")
    b.subheader("CLV tier x lifecycle")
    b.altair_chart(alt.Chart(tiers).mark_bar().encode(x="clv_tier:N", y="customers:Q", color="lifecycle_stage:N"), use_container_width=True)
    st.subheader("Look up a customer")
    top = q(f"select person_id, rfm_segment, clv_tier, order_count, total_clv_revenue from {t(MARTS, 'customer_profile')} where order_count > 0 order by total_clv_revenue desc limit 200")
    pid = st.selectbox("Person (top 200 by CLV)", top.person_id, format_func=lambda p: f"{p}  |  {top.set_index('person_id').loc[p, 'rfm_segment']}  |  {top.set_index('person_id').loc[p, 'clv_tier']}")
    prof = q(f"select * from {t(MARTS, 'customer_profile')} where person_id = '{pid}'").iloc[0]
    st.json({k: (None if pd.isna(v) else (v.isoformat() if hasattr(v, "isoformat") else (v.item() if hasattr(v, "item") else v))) for k, v in prof.items()}, expanded=False)
    sess = q(f"select session_start_ts, source_system, channel_group, campaign_key, platform, page_views, purchases from {t(MARTS, 'fct_sessions')} where person_id = '{pid}' order by session_start_ts")
    orders = q(f"select ordered_at, order_channel, status, net_revenue, converting_session_key from {t(MARTS, 'fct_orders')} where person_id = '{pid}' order by ordered_at")
    st.write("**Sessions across web + app** (stitched by the identity graph)")
    st.dataframe(sess, use_container_width=True)
    st.write("**Orders**")
    st.dataframe(orders, use_container_width=True)

else:
    mp = cfg.REPORTS_DIR / "metrics.json"
    if not mp.exists():
        st.warning("Run the pipeline first: `make demo`")
    else:
        m = json.loads(mp.read_text())
        st.subheader("dbt")
        st.json(m.get("dbt", {}), expanded=True)
        st.subheader("Reconciliation GA4/Segment vs CRM")
        st.json(m.get("reconciliation", {}), expanded=False)
        if "identity_resolution" in m:
            st.subheader("Identity resolution vs ground truth")
            st.json(m["identity_resolution"], expanded=False)
            st.subheader("Attribution vs ground truth")
            st.json(m["attribution_vs_ground_truth"], expanded=False)
        st.subheader("CLV back-test")
        st.json({k: v for k, v in m.get("clv_backtest", {}).items() if k != "decile_calibration"}, expanded=False)
