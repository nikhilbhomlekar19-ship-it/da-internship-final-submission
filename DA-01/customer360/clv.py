"""Customer lifetime value: BG/NBD (purchase frequency + churn) x Gamma-Gamma (order value).

  * BG/NBD       Fader, Hardie & Lee (2005) "Counting your customers the easy way"
  * Gamma-Gamma  Fader & Hardie (2013) "The Gamma-Gamma model of monetary value"

Implemented directly on numpy/scipy (no `lifetimes` dependency: that package is unmaintained).

Back-test: calibrate on orders up to 2020-10-31, forecast the 92 days of the GA4 window, compare with what really happened
and against a naive run-rate baseline.  Production forecast: calibrate on everything up to AS_OF_DATE, predict the next 12 months.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit, gammaln, hyp2f1

from . import config as cfg
from .warehouse import Warehouse

MODEL_VERSION = "bgnbd_gg_v1"


# ----------------------------------------------------------------------------- BG/NBD
def bgnbd_nll(params, x, t_x, T):
    r, alpha, a, b = params
    if np.any(np.asarray(params) <= 0):
        return np.inf
    a1 = gammaln(r + x) - gammaln(r) + r * np.log(alpha)
    a2 = gammaln(a + b) + gammaln(b + x) - gammaln(b) - gammaln(a + b + x)
    a3 = -(r + x) * np.log(alpha + T)
    a4 = np.log(a) - np.log(b + np.maximum(x, 1) - 1) - (r + x) * np.log(t_x + alpha)
    m = np.maximum(a3, a4)
    ll = a1 + a2 + np.log(np.exp(a3 - m) + np.exp(a4 - m) * (x > 0)) + m
    return -ll.sum() / len(x)


def fit_bgnbd(x, t_x, T, penalizer=1e-4):
    f = lambda th: bgnbd_nll(np.exp(th), x, t_x, T) + penalizer * float(np.sum(np.exp(th) ** 2))
    best = None
    for start in ([1.0, 10.0, 1.0, 3.0], [0.5, 5.0, 0.8, 2.0]):
        res = minimize(f, np.log(start), method="L-BFGS-B", bounds=[(-7, 7)] * 4)
        if best is None or res.fun < best.fun:
            best = res
    r, alpha, a, b = np.exp(best.x)
    return dict(r=float(r), alpha=float(alpha), a=float(a), b=float(b), nll=float(best.fun))


def expected_purchases(t, x, t_x, T, p):
    """E[# purchases in the next t weeks | history] (conditional expectation of BG/NBD)."""
    r, alpha, a, b = p["r"], p["alpha"], p["a"], p["b"]
    _a, _b, _c = r + x, b + x, a + b + x - 1
    z = t / (alpha + T + t)
    with np.errstate(all="ignore"):
        ln_h = np.log(hyp2f1(_a, _b, _c, z))
        ln_alt = np.log(hyp2f1(_c - _a, _c - _b, _c, z)) + (_c - _a - _b) * np.log(1 - z)
        ln_h = np.where(~np.isfinite(ln_h), ln_alt, ln_h)
        first = (a + b + x - 1) / (a - 1)
        second = 1 - np.exp(ln_h + (r + x) * np.log((alpha + T) / (alpha + t + T)))
        den = 1 + (x > 0) * (a / (b + x - 1)) * ((alpha + T) / (alpha + t_x)) ** (r + x)
        out = first * second / den
    return np.clip(np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0), 0, None)


def prob_alive(x, t_x, T, p):
    r, alpha, a, b = p["r"], p["alpha"], p["a"], p["b"]
    with np.errstate(all="ignore"):
        log_div = (r + x) * np.log((alpha + T) / (alpha + t_x)) + np.log(a / (b + np.maximum(x, 1) - 1))
        return np.where(x == 0, 1.0, expit(-log_div))


# ----------------------------------------------------------------------------- Gamma-Gamma
def gg_nll(params, x, m):
    p, q, v = params
    if np.any(np.asarray(params) <= 0):
        return np.inf
    ll = (gammaln(p * x + q) - gammaln(p * x) - gammaln(q) + q * np.log(v) + (p * x - 1) * np.log(m)
          + p * x * np.log(x) - (p * x + q) * np.log(x * m + v))
    return -ll.sum() / len(x)


def fit_gg(x, m, penalizer=1e-3):
    f = lambda th: gg_nll(np.exp(th), x, m) + penalizer * float(np.sum(np.exp(th) ** 2))
    res = minimize(f, np.log([6.0, 4.0, 15.0]), method="L-BFGS-B", bounds=[(-5, 7)] * 3)
    p, q, v = np.exp(res.x)
    return dict(p=float(p), q=float(q), v=float(v))


def expected_aov(x, m, g):
    p, q, v = g["p"], g["q"], g["v"]
    pop = v * p / (q - 1) if q > 1 else float(np.mean(m)) if len(m) else 0.0
    if q <= 1:
        return np.where(x > 0, m, pop)
    w = p * x / (p * x + q - 1)
    return np.where(x > 0, (1 - w) * pop + w * m, pop)


# ----------------------------------------------------------------------------- data prep
def load_transactions(wh: Warehouse) -> pd.DataFrame:
    sql = f"""
        select n.person_id, o.order_date as order_date, sum(o.net_revenue) as value
        from {wh.fq(cfg.dbt_schema('staging'), 'stg_crm__orders')} o
        join {wh.fq(cfg.ML_SCHEMA, 'identity_nodes')} n on n.node_key = concat('crm:', o.customer_id)
        where o.status = 'completed'
        group by 1, 2
    """
    tx = wh.query(sql)
    tx["order_date"] = pd.to_datetime(tx["order_date"])
    return tx


def summarise(tx: pd.DataFrame, cal_end: pd.Timestamp) -> pd.DataFrame:
    """Per customer: x (repeat transactions), t_x (weeks first->last), T (weeks first->cal_end), mean repeat value."""
    t = tx[tx.order_date <= cal_end].sort_values(["person_id", "order_date"])
    g = t.groupby("person_id")
    first, last = g.order_date.min(), g.order_date.max()
    n = g.order_date.nunique()
    tot, first_val = g["value"].sum(), g["value"].first()
    out = pd.DataFrame({
        "frequency": (n - 1).astype(float),
        "recency_weeks": ((last - first).dt.days / 7).astype(float),
        "T_weeks": ((cal_end - first).dt.days / 7).astype(float),
        "n_orders": n,
        "first_order_date": first,
        "last_order_date": last,
        "avg_repeat_value": np.where(n > 1, (tot - first_val) / np.maximum(n - 1, 1), np.nan),
        "first_order_value": first_val,
    })
    out["T_weeks"] = np.maximum(out["T_weeks"], out["recency_weeks"])
    return out.reset_index()


# ----------------------------------------------------------------------------- back-test
def backtest(tx: pd.DataFrame, cal_end: pd.Timestamp, hold_end: pd.Timestamp) -> dict:
    s = summarise(tx, cal_end)
    p = fit_bgnbd(s.frequency.values, s.recency_weeks.values, s["T_weeks"].values)
    hold_weeks = (hold_end - cal_end).days / 7
    s["pred"] = expected_purchases(hold_weeks, s.frequency.values, s.recency_weeks.values, s["T_weeks"].values, p)
    s["pred_baseline"] = s.frequency / np.maximum(s["T_weeks"], 1) * hold_weeks  # naive run-rate
    actual = (tx[(tx.order_date > cal_end) & (tx.order_date <= hold_end)].groupby("person_id").order_date.nunique())
    s["actual"] = s.person_id.map(actual).fillna(0).astype(float)
    mae_m, mae_b = float(np.mean(np.abs(s.pred - s.actual))), float(np.mean(np.abs(s.pred_baseline - s.actual)))
    s["decile"] = pd.qcut(s.pred.rank(method="first"), 10, labels=False) + 1
    dec = s.groupby("decile").agg(customers=("person_id", "count"), predicted=("pred", "mean"), actual=("actual", "mean")).round(4).reset_index()
    # monetary back-test
    rep = s[(s.frequency > 0) & s.avg_repeat_value.notna() & (s.avg_repeat_value > 0)]
    g = fit_gg(rep.frequency.values, rep.avg_repeat_value.values)
    hold = tx[(tx.order_date > cal_end) & (tx.order_date <= hold_end)].groupby("person_id")["value"].mean()
    s["pred_aov"] = expected_aov(s.frequency.values, s.avg_repeat_value.fillna(0).values, g)
    s["act_aov"] = s.person_id.map(hold)
    ok = s[s.act_aov.notna()]
    pop_mean = float(rep.avg_repeat_value.mean())
    return {
        "calibration_end": str(cal_end.date()), "holdout_end": str(hold_end.date()), "customers": int(len(s)),
        "bgnbd_params": {k: round(v, 4) for k, v in p.items() if k != "nll"},
        "holdout_repeat_orders_actual": float(s.actual.sum()), "holdout_repeat_orders_predicted": round(float(s.pred.sum()), 1),
        "total_orders_error_pct": round(100 * (s.pred.sum() - s.actual.sum()) / max(s.actual.sum(), 1), 2),
        "mae_per_customer_model": round(mae_m, 4), "mae_per_customer_naive_runrate": round(mae_b, 4),
        "mae_improvement_vs_naive_pct": round(100 * (mae_b - mae_m) / max(mae_b, 1e-9), 1),
        "correlation_pred_vs_actual": round(float(np.corrcoef(s.pred, s.actual)[0, 1]), 4),
        "aov_mape_model_pct": round(100 * float(np.mean(np.abs(ok.pred_aov - ok.act_aov) / ok.act_aov)), 1) if len(ok) else None,
        "aov_mape_population_mean_pct": round(100 * float(np.mean(np.abs(pop_mean - ok.act_aov) / ok.act_aov)), 1) if len(ok) else None,
        "gamma_gamma_params": {k: round(v, 4) for k, v in g.items()},
        "decile_calibration": dec.to_dict(orient="records"),
    }


# ----------------------------------------------------------------------------- production forecast
def forecast(tx: pd.DataFrame, as_of: pd.Timestamp, horizon_weeks: float = 52.18, discount_rate: float = 0.10) -> tuple[pd.DataFrame, dict]:
    s = summarise(tx, as_of)
    p = fit_bgnbd(s.frequency.values, s.recency_weeks.values, s["T_weeks"].values)
    rep = s[(s.frequency > 0) & (s.avg_repeat_value > 0)]
    g = fit_gg(rep.frequency.values, rep.avg_repeat_value.values)
    x, tx_, T = s.frequency.values, s.recency_weeks.values, s["T_weeks"].values
    s["p_alive"] = prob_alive(x, tx_, T, p)
    s["predicted_orders_12m"] = expected_purchases(horizon_weeks, x, tx_, T, p)
    s["predicted_aov"] = expected_aov(x, s.avg_repeat_value.fillna(0).values, g)
    # discounted 12-month revenue: month-by-month increments of the expected-purchases curve
    month, prev, pv = horizon_weeks / 12, np.zeros(len(s)), np.zeros(len(s))
    for m in range(1, 13):
        cur = expected_purchases(m * month, x, tx_, T, p)
        pv += (cur - prev) / (1 + discount_rate) ** (m / 12)
        prev = cur
    s["clv_12m_revenue"] = pv * s.predicted_aov
    s["as_of_date"] = as_of.date()
    s["model_version"] = MODEL_VERSION
    cols = ["person_id", "n_orders", "frequency", "recency_weeks", "T_weeks", "avg_repeat_value", "first_order_value", "p_alive",
            "predicted_orders_12m", "predicted_aov", "clv_12m_revenue", "as_of_date", "model_version"]
    return s[cols].copy(), {"bgnbd_params": {k: round(v, 4) for k, v in p.items() if k != "nll"},
                            "gamma_gamma_params": {k: round(v, 4) for k, v in g.items()}}


def run() -> dict:
    with Warehouse() as wh:
        tx = load_transactions(wh)
        as_of = pd.Timestamp(cfg.AS_OF_DATE)
        bt = backtest(tx, pd.Timestamp(cfg.START_DATE) - pd.Timedelta(days=1), as_of)
        fc, params = forecast(tx, as_of)
        fc["as_of_date"] = pd.to_datetime(fc["as_of_date"])
        wh.write_df(fc, cfg.ML_SCHEMA, "clv_forecast")
    cfg.REPORTS_DIR.mkdir(exist_ok=True)
    (cfg.REPORTS_DIR / "clv_backtest.json").write_text(json.dumps(bt, indent=2))
    return {"customers_scored": int(len(fc)), "mean_clv_12m_revenue": round(float(fc.clv_12m_revenue.mean()), 2),
            "forecast_params": params, **{k: v for k, v in bt.items() if k != "decile_calibration"}}
