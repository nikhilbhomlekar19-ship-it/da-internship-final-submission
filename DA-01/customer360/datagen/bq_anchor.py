"""BigQuery path: build the synthetic CRM / Segment / ad-spend tables AROUND THE REAL GA4 SAMPLE.

    bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*   (Google Merchandise Store, 2020-11-01 .. 2021-01-31)

The real sample stays untouched (dbt reads it straight from the public dataset).  What we add, in your own project:
  * a CRM customer for every GA4 user that purchased (+ a sample of other users as leads), carrying the REAL transaction ids,
    so CRM orders reconcile with GA4 purchases exactly like in a real company (guest checkout = same e-mail on the order);
  * synthetic order HISTORY before the window (BG/NBD) so RFM / CLV have something to work with;
  * Segment identify() calls that bridge anonymous_id <-> user_id <-> GA client id (user_pseudo_id), plus a mobile app:
    app sessions with campaign context and app orders;
  * a daily ad-spend export for every paid campaign found in the real sessions (+ the app campaigns).

`build_from_anchor()` is pure pandas (unit-tested with a stand-in anchor); `generate_bigquery()` runs the 3 anchor queries and loads results.
"""
from __future__ import annotations

import math
from datetime import timedelta

import numpy as np
import pandas as pd

from .. import config as cfg
from ..warehouse import Warehouse
from .catalog import CAMPAIGNS, PAID, classify_channel
from .simulate import (BGNBD_TRUE, DAYS, HIST_START, N_DAYS, WIN_END, WIN_START, Order, Sess, Simulator, season, weekday_factor)

GA4 = "`bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`"
SUFFIX = f"_table_suffix between '{cfg.START_DATE:%Y%m%d}' and '{cfg.END_DATE:%Y%m%d}'"

PURCHASES_SQL = f"""
select user_pseudo_id, ecommerce.transaction_id as transaction_id,
       min(timestamp_micros(event_timestamp)) as purchase_ts,
       max(ecommerce.purchase_revenue_in_usd) as revenue,
       max(ecommerce.total_item_quantity) as items
from {GA4}
where {SUFFIX} and event_name = 'purchase'
  and ecommerce.transaction_id is not null and ecommerce.transaction_id != '(not set)'
group by 1, 2
having max(ecommerce.purchase_revenue_in_usd) > 0
"""

USERS_SQL = """
with purchasers as (
  select distinct user_pseudo_id from {ga4}
  where {suffix} and event_name = 'purchase' and ecommerce.transaction_id is not null and ecommerce.transaction_id != '(not set)'
)
select user_pseudo_id,
       min(timestamp_micros(event_timestamp)) as first_seen_ts,
       max(timestamp_micros(event_timestamp)) as last_seen_ts,
       min(timestamp_micros(user_first_touch_timestamp)) as first_touch_ts,
       any_value(geo.country) as country, any_value(geo.region) as region, any_value(geo.city) as city,
       any_value(device.category) as device_category
from {ga4}
where {suffix}
  and (user_pseudo_id in (select user_pseudo_id from purchasers)
       or mod(abs(farm_fingerprint(user_pseudo_id)), 1000) < {pct_permille})
group by user_pseudo_id
"""

# session-level source / medium / campaign (first event of the session that carries them), counted per day
SESSIONS_SQL = f"""
with ev as (
  select event_date, user_pseudo_id, event_timestamp,
         (select value.int_value from unnest(event_params) where key = 'ga_session_id') as sid,
         (select value.string_value from unnest(event_params) where key = 'source') as src,
         (select value.string_value from unnest(event_params) where key = 'medium') as med,
         (select value.string_value from unnest(event_params) where key = 'campaign') as cmp,
         traffic_source.source as first_src, traffic_source.medium as first_med, traffic_source.name as first_cmp
  from {GA4} where {SUFFIX}
),
sess as (
  select parse_date('%Y%m%d', min(event_date)) as d,
         array_agg(src ignore nulls order by event_timestamp limit 1)[safe_offset(0)] as src,
         array_agg(med ignore nulls order by event_timestamp limit 1)[safe_offset(0)] as med,
         array_agg(cmp ignore nulls order by event_timestamp limit 1)[safe_offset(0)] as cmp,
         any_value(first_src) as first_src, any_value(first_med) as first_med, any_value(first_cmp) as first_cmp
  from ev where sid is not null group by user_pseudo_id, sid
)
select d,
       lower(coalesce(src, first_src, '(direct)')) as source,
       lower(coalesce(med, first_med, '(none)')) as medium,
       lower(coalesce(cmp, first_cmp, '(direct)')) as campaign,
       count(*) as sessions
from sess group by 1, 2, 3, 4
"""

ISO = {"United States": "US", "Canada": "CA", "United Kingdom": "GB", "India": "IN", "Australia": "AU"}
PLATFORM = {"google": "google_ads", "bing": "bing_ads", "facebook": "meta_ads", "instagram": "meta_ads", "tiktok": "tiktok_ads", "dv360": "dv360"}


def _naive(s: pd.Series) -> pd.Series:
    s = pd.to_datetime(s, utc=True)
    return s.dt.tz_localize(None)


def _history(sim: Simulator, p) -> list:
    """BG/NBD order timeline strictly before the tracking window."""
    rng = sim.rng
    r, alpha, a, b = (BGNBD_TRUE[k] for k in ("r", "alpha", "a", "b"))
    lam, pdrop = max(float(rng.gamma(r, 1 / alpha)), 1e-4), float(rng.beta(a, b))
    t0 = HIST_START + timedelta(seconds=float(rng.uniform(0, (WIN_START - timedelta(days=10) - HIST_START).total_seconds())))
    times, t = [t0.replace(microsecond=0)], t0
    while True:  # drop-out only after a repeat purchase (BG/NBD)
        t = t + timedelta(weeks=min(float(rng.exponential(1 / lam)), 600))
        if t >= WIN_START - timedelta(hours=1):
            break
        times.append(t.replace(microsecond=0))
        if rng.random() < pdrop:
            break
    return times


def build_from_anchor(users: pd.DataFrame, purchases: pd.DataFrame, paid_sessions: pd.DataFrame, seed: int = 42,
                      target_mer: float = 3.4, app_rate: float = 0.28) -> dict:
    """users: user_pseudo_id, first_seen_ts, last_seen_ts, first_touch_ts, country, region, city
       purchases: user_pseudo_id, transaction_id, purchase_ts, revenue, items
       paid_sessions: d, source, medium, campaign, sessions     ->  dict of raw tables for BigQuery"""
    sim = Simulator(n_persons=0, seed=seed, target_mer=target_mer)
    rng = sim.rng
    users, purchases = users.copy(), purchases.copy()
    for c in ("first_seen_ts", "last_seen_ts", "first_touch_ts"):
        users[c] = _naive(users[c])
    purchases["purchase_ts"] = _naive(purchases["purchase_ts"])
    by_user = {u: g.sort_values("purchase_ts") for u, g in purchases.groupby("user_pseudo_id")}

    web_identifies = []
    for i, u in enumerate(users.itertuples()):
        p = sim.make_person(i, is_crm=True)
        p.ga_id = u.user_pseudo_id
        p.country = ISO.get(getattr(u, "country", None), "US")
        real = by_user.get(u.user_pseudo_id)
        p.is_existing = bool(u.first_touch_ts < WIN_START) if pd.notna(u.first_touch_ts) else False
        p.is_buyer = real is not None or (p.is_existing and rng.random() < .6)
        p.app_user = bool(rng.random() < app_rate)
        p.app_id = sim._uuid() if p.app_user else None
        times = []
        if p.is_existing and p.is_buyer:
            times += _history(sim, p)
        real_rows = list(real.itertuples()) if real is not None else []
        times += [r.purchase_ts.to_pydatetime() for r in real_rows]
        extra_app = []
        if p.app_user and p.is_buyer:  # orders placed in the app (never visible to GA4)
            for _ in range(int(rng.poisson(.35))):
                d = DAYS[int(rng.choice(N_DAYS, p=np.array([season(x) * weekday_factor(x) for x in DAYS]) / sum(season(x) * weekday_factor(x) for x in DAYS)))]
                extra_app.append(sim.rand_time(d).replace(microsecond=0))
        p.order_ts = sorted(times + extra_app)
        p.browsers = []
        sim.persons.append(p)
        sim.assign_crm(p)
        # ---- orders (real GA4 purchases keep their transaction ids)
        real_by_ts = {r.purchase_ts.to_pydatetime(): r for r in real_rows}
        for idx, ts in enumerate(p.order_ts):
            n = sim._next("order")
            if ts in real_by_ts:
                r = real_by_ts[ts]
                ch, ext, net, items = "web", str(r.transaction_id), float(r.revenue), int(r.items or 1)
                d = float(rng.choice([0, 0, 0, .10, .15, .20, .25]))
                total = round(net / (1 - d), 2)
                disc = round(total - net, 2)
                ts_crm = ts + timedelta(seconds=int(rng.integers(5, 90)))
            elif ts in extra_app:
                ch, ext, ts_crm = "app", f"A{n:08d}", ts
                total = float(np.clip(round(float(rng.lognormal(math.log(40), .35)) * p.spend_mult + 4, 2), 9, 450))
                disc, items = 0.0, max(1, int(round(total / 30)))
            else:  # history
                ch = "store" if (idx > 0 and rng.random() < .06) else ("app" if p.app_user and rng.random() < .65 else "web")
                ext = None if ch == "store" else f"{'T' if ch == 'web' else 'A'}{n:08d}"
                total = float(np.clip(round(float(rng.lognormal(math.log(40), .35)) * p.spend_mult + 4, 2), 9, 450))
                disc, items, ts_crm = (round(total * float(rng.choice([.10, .15, .20, .25])), 2) if rng.random() < .22 else 0.0), max(1, int(round(total / 30))), ts
            u_ = rng.random()
            status = "completed" if u_ < .91 else ("returned" if u_ < .98 else "cancelled")
            paid = round(total - disc, 2)
            refund = 0.0 if status == "completed" else round(paid * (1.0 if (status == "cancelled" or rng.random() < .7) else .5), 2)
            o = Order(f"O{n:07d}", p, ts_crm, ch, sim.crm_id_at(p, ts_crm), total, disc, status, refund, ext,
                      f"SAVE{int(round(disc / total * 100))}" if disc else None, items, idx == 0, ts_crm >= WIN_START)
            o.purchase_ts = ts_crm - timedelta(seconds=int(rng.integers(5, 90)))
            sim.orders.append(o)
            if ch == "app" and o.in_window:  # synthetic app journey (web touches are the real GA4 sessions)
                n_t = min(1 + int(rng.poisson(1.0)), 5)
                st = o.purchase_ts - timedelta(minutes=float(rng.uniform(2, 20)))
                starts = [st]
                for _ in range(n_t - 1):
                    st = st - timedelta(hours=6 + float(rng.exponential(60)))
                    starts.append(st)
                for k, st_ in enumerate(reversed(starts)):
                    if st_ < WIN_START:
                        continue
                    last = k == n_t - 1
                    s_ = sim._session(p, st_, "close" if last else ("mid" if p.is_existing else "disc"), "app", protected=True, order=o if last else None, final=last)
                    if s_ is not None:
                        sim.sessions.append(s_)
                        if last:
                            o.conv, o.online_tracked = s_, True
        # ---- extra app browsing
        if p.app_user:
            for _ in range(int(rng.poisson(2.0))):
                st = sim.rand_time(DAYS[int(rng.integers(N_DAYS))])
                s_ = sim._session(p, st, "mid" if p.is_existing else "disc", "app")
                if s_ is not None and (p.signup_ts is None or st >= p.signup_ts):
                    sim.sessions.append(s_)
        # ---- web identify() carrying the GA client id (the deterministic GA4 <-> Segment <-> CRM bridge)
        if p.seg_web:
            if real_rows:
                t = real_rows[0].purchase_ts.to_pydatetime() - timedelta(seconds=30)
            else:
                lo, hi = max(u.first_seen_ts, p.signup_ts), max(u.last_seen_ts, p.signup_ts)
                t = lo + (hi - lo) * float(rng.random())
            web_identifies.append({"id": f"msg-w{i:07d}", "anonymous_id": sim._uuid(), "user_id": p.crm_ids[0][0], "timestamp": t,
                                   "received_at": t + timedelta(seconds=1), "email": p.login_email, "ga_client_id": u.user_pseudo_id,
                                   "context_library_name": "analytics.js"})
    sim.finalize_sessions()
    ident, tracks, seg_orders = sim.render_segment(web_identifies=False)
    ident = pd.concat([ident, pd.DataFrame(web_identifies, columns=ident.columns)], ignore_index=True)
    cust, orders = sim.render_crm()
    ads = build_ads(sim, paid_sessions, purchases, target_mer)
    return {"crm_customers": cust, "crm_orders": orders, "segment_identifies": ident, "segment_tracks": tracks,
            "segment_order_completed": seg_orders, "ads_spend_daily": ads}


def build_ads(sim: Simulator, paid_sessions: pd.DataFrame, purchases: pd.DataFrame, target_mer: float) -> pd.DataFrame:
    rng = sim.rng
    ps = paid_sessions.copy()
    ps["d"] = pd.to_datetime(ps["d"]).dt.date
    ps = ps[[classify_channel(s, m) in ("Paid Search", "Paid Social", "Display", "Affiliate") for s, m in zip(ps.source, ps.medium)]]
    series: dict[tuple, np.ndarray] = {}
    for (s, m, c), g in ps.groupby(["source", "medium", "campaign"]):
        arr = np.zeros(N_DAYS)
        idx = {d: i for i, d in enumerate(DAYS)}
        for r in g.itertuples():
            if r.d in idx:
                arr[idx[r.d]] += r.sessions
        if arr.sum() >= 30:
            series[(s, m, c)] = arr
    for cmp_ in PAID:  # synthetic app campaigns
        arr = np.zeros(N_DAYS)
        for s_ in sim.sessions:
            if s_.cmp.key == cmp_.key:
                arr[(s_.start.date() - cfg.START_DATE).days] += 1
        if arr.sum() >= 30:
            series[(cmp_.source, cmp_.medium, cmp_.campaign)] = arr
    revenue = float(purchases.revenue.sum()) + sum(o.net for o in sim.orders if o.in_window and o.channel == "app")
    s_total = revenue / target_mer
    wts = {k: v.sum() ** 0.9 for k, v in series.items()}
    z = sum(wts.values()) or 1.0
    n_sessions = max(float(paid_sessions.sessions.sum()), 1.0)
    cvr = float(len(purchases)) / n_sessions
    rows = []
    for ci, ((s, m, c), n) in enumerate(sorted(series.items())):
        gamma, ctr, over = float(rng.uniform(.25, .6)), float(rng.uniform(.01, .06)), float(rng.uniform(1.15, 1.7))
        clicks = np.round(n / 0.94 * np.exp(rng.normal(0, .03, N_DAYS)))
        mean = clicks[clicks > 0].mean()
        raw = np.where(clicks > 0, (clicks / mean) ** (1 + gamma) * np.exp(rng.normal(0, .06, N_DAYS)), 0.0)
        cost = s_total * wts[(s, m, c)] / z * raw / max(raw.sum(), 1e-9)
        imps = np.round(clicks / ctr * np.exp(rng.normal(0, .05, N_DAYS)))
        conv = rng.poisson(clicks * cvr * over)
        plat = PLATFORM.get(s, f"{s}_ads")
        for di, d in enumerate(DAYS):
            rows.append({"date": d, "platform": plat, "account_id": f"acct-{plat}", "campaign_id": f"{plat[:3]}-{1001 + ci}",
                         "campaign_name": f"{classify_channel(s, m)} | {c}", "utm_source": s, "utm_medium": m, "utm_campaign": c,
                         "impressions": int(imps[di]), "clicks": int(clicks[di]), "cost": round(float(cost[di]), 2), "currency": "USD",
                         "platform_conversions": float(conv[di]), "platform_conversion_value": round(float(conv[di]) * revenue / max(len(purchases), 1), 2)})
    return pd.DataFrame(rows)


def generate_bigquery(seed: int = 42, sample_pct: float = 8.0) -> dict:
    if cfg.TARGET != "bigquery":
        raise SystemExit("Set C360_TARGET=bigquery (and GCP_PROJECT) first - see docs/01_implementation_guide.md")
    with Warehouse("bigquery") as wh:
        purchases = wh.query(PURCHASES_SQL)
        users = wh.query(USERS_SQL.format(ga4=GA4, suffix=SUFFIX, pct_permille=int(sample_pct * 10)))
        sessions = wh.query(SESSIONS_SQL)
        tables = build_from_anchor(users, purchases, sessions, seed=seed)
        for name, df in tables.items():
            wh.write_df(df, cfg.RAW_SCHEMA, name)
    return {"ga4_users_anchored": int(len(users)), "ga4_purchases": int(len(purchases)),
            **{k: int(len(v)) for k, v in tables.items()}, "raw_dataset": f"{cfg.GCP_PROJECT}.{cfg.RAW_SCHEMA}"}
