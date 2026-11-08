import numpy as np
import pandas as pd
import pytest

from customer360.attribution import MODELS, attribute, total_variation

T0 = pd.Timestamp("2020-12-10 12:00")


def sess(rows):
    return pd.DataFrame(rows, columns=["session_key", "person_id", "session_start_ts", "channel_group", "campaign_key"])


CONV = pd.DataFrame([{"order_id": "O1", "person_id": "P1", "ordered_at": T0, "net_revenue": 100.0, "is_first_order": True}])
PATH = sess([
    ("s1", "P1", T0 - pd.Timedelta(hours=216), "Paid Social", "fb|paid_social|a"),
    ("s2", "P1", T0 - pd.Timedelta(hours=48), "Email", "k|email|b"),
    ("s3", "P1", T0 - pd.Timedelta(hours=1), "Direct", "(direct)|(none)|(direct)"),
    ("s4", "P1", T0 - pd.Timedelta(hours=0.5), "Paid Search", "g|cpc|c"),
])


def credit(df, model):
    return df[df.model == model].set_index("session_key").credit


def test_credits_sum_to_one_per_order_and_model():
    out = attribute(CONV, PATH)
    assert np.allclose(out.groupby(["model", "order_id"]).credit.sum(), 1.0)


def test_model_semantics_with_direct_deprioritised():
    out = attribute(CONV, PATH)  # Direct (s3) is ignored because other channels exist
    assert set(out.session_key) == {"s1", "s2", "s4"}
    assert credit(out, "first_touch").to_dict() == {"s1": 1.0, "s2": 0.0, "s4": 0.0}
    assert credit(out, "last_touch").to_dict() == {"s1": 0.0, "s2": 0.0, "s4": 1.0}
    assert np.allclose(credit(out, "linear"), 1 / 3)
    td = credit(out, "time_decay")
    assert td["s4"] > td["s2"] > td["s1"] > 0  # more recent = more credit


def test_direct_included_when_policy_says_so():
    out = attribute(CONV, PATH, direct_policy="include")
    assert "s3" in set(out.session_key) and credit(out, "last_touch")["s4"] == 1.0


def test_direct_only_path_still_gets_credit():
    only_direct = PATH[PATH.channel_group == "Direct"]
    out = attribute(CONV, only_direct)
    assert (out.channel_group == "Direct").all() and np.isclose(out[out.model == "last_touch"].credit.sum(), 1.0)


def test_lookback_and_future_touches_excluded():
    p = sess([("old", "P1", T0 - pd.Timedelta(days=45), "Paid Search", "x"), ("future", "P1", T0 + pd.Timedelta(hours=1), "Email", "y")])
    out = attribute(CONV, p)
    assert (out.channel_group == "Unattributed").all()  # nothing in the window -> unattributed, revenue still reconciles
    assert np.isclose(out.groupby("model").credited_revenue.sum(), 100.0).all()


def test_half_life_halves_weight():
    p = sess([("a", "P1", T0 - pd.Timedelta(days=7), "Paid Search", "x"), ("b", "P1", T0, "Email", "y")])
    td = credit(attribute(CONV, p, half_life_days=7), "time_decay")
    assert td["b"] / td["a"] == pytest.approx(2.0)


def test_total_variation_bounds():
    a = pd.Series({"x": 1.0, "y": 1.0})
    assert total_variation(a, a) == 0
    assert total_variation(pd.Series({"x": 1.0}), pd.Series({"y": 1.0})) == 1
    assert set(MODELS) == {"first_touch", "last_touch", "linear", "time_decay"}
