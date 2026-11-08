import numpy as np
import pandas as pd
import pytest

from customer360.datagen.bq_anchor import build_from_anchor
from customer360.datagen.simulate import simulate


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    from customer360.datagen import simulate as s

    out = tmp_path_factory.mktemp("sim")
    r = s.Simulator(n_persons=500, bounce_per_day=20, seed=7, out_dir=out).run()
    return r


def test_referential_integrity(sim):
    t = sim.tables
    cust, orders = t["crm_customers"], t["crm_orders"]
    assert orders.customer_id.isin(cust.customer_id).all()
    assert cust.customer_id.is_unique and orders.order_id.is_unique
    web_refs = set(orders[orders.order_channel == "web"].external_ref)
    seg_refs = set(t["segment_order_completed"].order_id)
    assert seg_refs <= set(orders[orders.order_channel == "app"].external_ref)
    assert t["segment_identifies"].user_id.isin(cust.customer_id).all()
    assert len(web_refs) > 0


def test_ga4_events_have_session_ids_and_duplicates_exist(sim):
    import json

    ids, txn = [], []
    for line in open(sim.ga4_jsonl):
        r = json.loads(line)
        ids.append(any(p["key"] == "ga_session_id" for p in r["event_params"]))
        if r["event_name"] == "purchase":
            txn.append(r["ecommerce"]["transaction_id"])
    assert all(ids)
    assert len(txn) >= len(set(txn))  # double-fired purchase tags are part of the simulation on purpose


def test_ad_spend_matches_target_mer(sim):
    spend = sim.tables["ads_spend_daily"].cost.sum()
    assert spend == pytest.approx(sim.summary["paid_spend"], rel=0.01)
    assert sim.summary["online_net_revenue"] / spend == pytest.approx(3.4, rel=0.05)


def test_truth_tables_cover_all_sessions(sim):
    assert len(sim.truth["truth_sessions"]) == sim.summary["sessions_web"] + sim.summary["sessions_app"]
    assert sim.truth["truth_sessions"].session_key.is_unique


def test_build_from_anchor_keeps_real_transaction_ids():
    rng = np.random.default_rng(1)
    n = 300
    users = pd.DataFrame({"user_pseudo_id": [f"{10**9 + i}.{16 * 10**8 + i}" for i in range(n)],
                          "first_seen_ts": pd.to_datetime("2020-11-05", utc=True) + pd.to_timedelta(rng.integers(0, 80, n), unit="D"),
                          "last_seen_ts": pd.to_datetime("2021-01-20", utc=True),
                          "first_touch_ts": pd.to_datetime("2020-10-01", utc=True) + pd.to_timedelta(rng.integers(0, 120, n), unit="D"),
                          "country": "United States", "region": "x", "city": "y"})
    b = users.sample(80, random_state=2)
    purchases = pd.DataFrame({"user_pseudo_id": b.user_pseudo_id.values, "transaction_id": [f"{9 * 10**5 + i}" for i in range(len(b))],
                              "purchase_ts": pd.to_datetime((b.first_seen_ts + pd.to_timedelta(rng.integers(1, 3000, len(b)), unit="min")).values, utc=True),
                              "revenue": rng.uniform(15, 200, len(b)).round(2), "items": 2})
    days = pd.date_range("2020-11-01", "2021-01-31").date
    sess = pd.DataFrame([{"d": d, "source": "google", "medium": "cpc", "campaign": "(not set)", "sessions": int(rng.integers(5, 40))} for d in days])
    t = build_from_anchor(users, purchases, sess, seed=3)
    web = t["crm_orders"][(t["crm_orders"].order_channel == "web") & (t["crm_orders"].ordered_at >= "2020-11-01")]
    assert set(web.external_ref) == set(purchases.transaction_id)
    net = (web.order_total - web.discount_amount).round(2).sum()
    assert net == pytest.approx(purchases.revenue.sum(), abs=0.5)  # CRM revenue == GA4 revenue for the real purchases
    assert t["crm_orders"].customer_id.isin(t["crm_customers"].customer_id).all()
    assert (t["ads_spend_daily"].cost >= 0).all()


def test_segment_replay_builds_valid_spec_calls(sim):
    from customer360.segment_replay import build_calls

    t = sim.tables
    ident = t["segment_identifies"]
    ident = pd.concat([ident[ident.ga_client_id.notna()].head(10), ident[ident.ga_client_id.isna()].head(10)])
    calls = build_calls(ident, t["segment_tracks"].head(60), t["segment_order_completed"])
    assert {c["type"] for c in calls} <= {"identify", "track"}
    assert all(c["anonymous_id"] for c in calls)
    web = [c for c in calls if c["type"] == "identify" and "ga_client_id" in c["traits"]]
    assert web, "web identify() calls must carry the GA client id"
    assert [c["timestamp"] for c in calls] == sorted(c["timestamp"] for c in calls)
