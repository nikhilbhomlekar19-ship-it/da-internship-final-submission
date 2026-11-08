"""Reference implementation of the four attribution models in pandas.

The production models live in dbt (int_attribution__paths.sql).  This module re-implements them independently so that
  * the evaluation can prove the SQL and the Python agree to ~1e-9 (parity test), and
  * analysts can run what-if scenarios (other lookbacks / half-lives / direct policy) without re-running dbt.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MODELS = ["first_touch", "last_touch", "linear", "time_decay"]


def attribute(conv: pd.DataFrame, sess: pd.DataFrame, lookback_days: float = 30, half_life_days: float = 7,
              direct_policy: str = "deprioritize") -> pd.DataFrame:
    """conv: order_id, person_id, ordered_at, net_revenue, is_first_order
       sess: session_key, person_id, session_start_ts, channel_group, campaign_key
       -> long table: model, order_id, person_id, session_key, channel_group, campaign_key, credit, credited_revenue, is_first_order"""
    t = conv.merge(sess[["session_key", "person_id", "session_start_ts", "channel_group", "campaign_key"]], on="person_id", how="inner")
    t = t[(t.session_start_ts <= t.ordered_at) & (t.session_start_ts >= t.ordered_at - pd.Timedelta(days=lookback_days))].copy()
    t["hours"] = (t.ordered_at - t.session_start_ts).dt.total_seconds() / 3600
    if direct_policy != "include":
        has_other = (t.channel_group != "Direct").groupby(t.order_id).transform("max")
        t = t[(t.channel_group != "Direct") | (~has_other)]
    t = t.sort_values(["order_id", "session_start_ts", "session_key"])
    t["pos"] = t.groupby("order_id").cumcount() + 1
    t["n"] = t.groupby("order_id")["order_id"].transform("size")
    t["w"] = 0.5 ** (t.hours / (half_life_days * 24))
    t["credit_first_touch"] = (t.pos == 1).astype(float)
    t["credit_last_touch"] = (t.pos == t.n).astype(float)
    t["credit_linear"] = 1.0 / t.n
    t["credit_time_decay"] = t.w / t.groupby("order_id")["w"].transform("sum")
    missing = conv[~conv.order_id.isin(t.order_id)].copy()
    missing["session_key"], missing["channel_group"], missing["campaign_key"] = None, "Unattributed", "(unattributed)"
    for m in MODELS:
        missing[f"credit_{m}"] = 1.0
    cols = ["order_id", "person_id", "session_key", "channel_group", "campaign_key", "net_revenue", "is_first_order"] + [f"credit_{m}" for m in MODELS]
    allp = pd.concat([t[cols], missing[cols]], ignore_index=True)
    out = []
    for m in MODELS:
        x = allp[["order_id", "person_id", "session_key", "channel_group", "campaign_key", "net_revenue", "is_first_order"]].copy()
        x["model"], x["credit"] = m, allp[f"credit_{m}"]
        x["credited_revenue"] = x.credit * x.net_revenue
        out.append(x)
    return pd.concat(out, ignore_index=True)


def channel_table(credits: pd.DataFrame, by: str = "channel_group") -> pd.DataFrame:
    g = credits.groupby(["model", by]).agg(orders=("credit", "sum"), revenue=("credited_revenue", "sum")).reset_index()
    g["share"] = g.revenue / g.groupby("model").revenue.transform("sum")
    return g


def total_variation(p: pd.Series, q: pd.Series) -> float:
    """0.5 * sum |p - q| over the union of categories (0 = identical allocation, 1 = completely different)."""
    idx = p.index.union(q.index)
    p, q = p.reindex(idx, fill_value=0.0), q.reindex(idx, fill_value=0.0)
    return float(0.5 * np.abs(p / p.sum() - q / q.sum()).sum())
