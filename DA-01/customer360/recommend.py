"""Where should the next marketing dollar go?

1. Response curves.  For every paid campaign and every attribution model fit  revenue = k * spend^beta  on DAILY data
   (revenue is dated by the touchpoint, so cost and the revenue it produced line up).  beta < 1 = diminishing returns and
   marginal ROAS = beta * revenue / spend.  The fit is a Poisson quasi-likelihood (handles zero-revenue days) with a bootstrap
   standard error; noisy fits are shrunk towards a prior elasticity (empirical-Bayes style) instead of being trusted blindly.
2. Re-allocate the SAME total budget so that marginal ROAS is equalised, maximising the AVERAGE revenue over the four
   attribution models (so no single model's bias drives the answer).  Each campaign may move +/-35 %.
3. Model-risk guard.  If last-touch ROAS is >2x (a "closer") or <0.5x (an "introducer") first-touch ROAS, the models
   disagree about what the campaign really does.  Those campaigns are capped at +/-10 % and flagged "Test incrementality":
   attribution alone cannot settle them - run a holdout / geo-lift test.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from . import config as cfg
from .attribution import MODELS
from .warehouse import Warehouse

BAND, BAND_FLAGGED = 0.35, 0.10
PRIOR_BETA, PRIOR_SD = 0.65, 0.15
N_BOOT, MIN_DAYS = 40, 25
CENSOR_LAST_DAYS = 14  # revenue from touches in the last 2 weeks is incomplete (orders not yet placed)


def fit_power_poisson(spend: np.ndarray, rev: np.ndarray, n_boot: int = N_BOOT, seed: int = 0) -> tuple[float, float]:
    """Quasi-Poisson fit of rev = exp(a) * (spend/mean)^beta.  Returns (beta, bootstrap standard error)."""
    x = np.log(spend / spend.mean())

    def fit(idx):
        xi, yi = x[idx], rev[idx]

        def nll(p):
            mu = np.exp(p[0] + p[1] * xi)
            return float((mu - yi * np.log(mu + 1e-12)).sum() / len(yi))

        return minimize(nll, [np.log(yi.mean() + 1e-6), 0.6], method="L-BFGS-B", bounds=[(-20, 20), (-1, 3)]).x[1]

    beta = fit(np.arange(len(x)))
    rng = np.random.default_rng(seed)
    boots = [fit(rng.integers(0, len(x), len(x))) for _ in range(n_boot)]
    return float(beta), float(max(np.std(boots), 0.05))


def shrink(beta: float, se: float) -> float:
    w = (1 / se**2) / (1 / se**2 + 1 / PRIOR_SD**2)
    return float(np.clip(w * beta + (1 - w) * PRIOR_BETA, 0.2, 0.95))


def allocate(S: np.ndarray, R: np.ndarray, beta: np.ndarray, band: np.ndarray, iters: int = 60) -> np.ndarray:
    """Maximise mean_m sum_c A_mc x_c^beta_mc  s.t. sum x = sum S,  (1-band) S <= x <= (1+band) S.
    R, beta: (models x campaigns).  Concave => water-filling on the Lagrange multiplier."""
    A = R / S[None, :] ** beta
    lo, hi, total = (1 - band) * S, (1 + band) * S, S.sum()
    grad = lambda x: (A * beta * x[None, :] ** (beta - 1)).mean(axis=0)

    def solve(lam: float) -> np.ndarray:
        a, b = lo.copy(), hi.copy()
        for _ in range(iters):
            mid = (a + b) / 2
            up = grad(mid) > lam
            a, b = np.where(up, mid, a), np.where(up, b, mid)
        x = (a + b) / 2
        x = np.where(grad(lo) <= lam, lo, x)
        return np.where(grad(hi) >= lam, hi, x)

    la, lb = 1e-9, 1e9
    for _ in range(100):
        lam = np.sqrt(la * lb)
        la, lb = (lam, lb) if solve(lam).sum() > total else (la, lam)
    return solve(np.sqrt(la * lb))


def run() -> dict:
    with Warehouse() as wh:
        marts = cfg.dbt_schema("marts")
        daily = wh.query(f"select spend_date, campaign_key, model, spend, attributed_revenue from {wh.fq(marts, 'mart_campaign_daily')} where spend > 0")
        roi = wh.query(f"select campaign_key, model, channel_group, platform, campaign_name, spend, attributed_revenue, attributed_orders, "
                       f"attributed_new_customers, roas, cpa, cac_new_customer, ltv_to_cac, platform_roas "
                       f"from {wh.fq(marts, 'mart_campaign_roi')} where is_paid")
        daily["spend_date"] = pd.to_datetime(daily["spend_date"])
        cutoff = daily.spend_date.max() - pd.Timedelta(days=CENSOR_LAST_DAYS)
        rows = []
        for (camp, model), d in daily[daily.spend_date <= cutoff].groupby(["campaign_key", "model"]):
            if len(d) >= MIN_DAYS:
                b, se = fit_power_poisson(d.spend.values, d.attributed_revenue.values)
            else:
                b, se = PRIOR_BETA, 1.0
            rows.append({"campaign_key": camp, "model": model, "n_days": len(d), "beta_fit": b, "beta_se": se,
                         "beta": shrink(b, se), "fit_quality": "ok" if se <= 0.20 else "low"})
        curves = pd.DataFrame(rows).merge(roi[["campaign_key", "model", "spend", "attributed_revenue", "roas"]], on=["campaign_key", "model"])
        curves["mroas"] = curves.beta * curves.roas

        camps = sorted(curves.campaign_key.unique())
        P = lambda col: curves.pivot(index="model", columns="campaign_key", values=col).reindex(index=MODELS, columns=camps)
        S = P("spend").iloc[0].values.astype(float)
        R = np.maximum(P("attributed_revenue").values.astype(float), 1e-6)
        B = P("beta").values.astype(float)
        roas = P("roas")
        ratio = (roas.loc["last_touch"] / roas.loc["first_touch"]).replace([np.inf, -np.inf], np.nan)
        flagged = ((ratio > 2) | (ratio < 0.5)).fillna(False).values
        band = np.where(flagged, BAND_FLAGGED, BAND)

        x = allocate(S, R, B, band)  # consensus
        per_model = {m: allocate(S, R[[i]], B[[i]], band) for i, m in enumerate(MODELS)}
        chg = x / S - 1
        agree = np.array([np.mean([(np.sign(per_model[m][j] - S[j]) == np.sign(x[j] - S[j])) or abs(x[j] / S[j] - 1) < .02 for m in MODELS]) for j in range(len(camps))])
        meta = roi.groupby("campaign_key").agg(channel_group=("channel_group", "first"), platform=("platform", "first"),
                                               campaign_name=("campaign_name", "first"), platform_roas=("platform_roas", "first"),
                                               ltv_to_cac_time_decay=("ltv_to_cac", "last")).reindex(camps)
        rec = meta.copy()
        for m in MODELS:
            rec[f"roas_{m}"] = roas.loc[m].values
        rec["beta_median"] = P("beta").median().values
        rec["mroas_median"] = P("mroas").median().values
        rec["roas_median"] = roas.median().values
        rec["last_vs_first_touch_ratio"] = ratio.values
        rec["model_dependent"] = flagged
        rec["current_spend"], rec["recommended_spend"] = S, x
        rec["change_pct"], rec["change_amount"] = chg, x - S
        for m in MODELS:
            rec[f"spend_if_only_{m}"] = per_model[m]
        rec["direction_agreement"] = agree
        low = (P("fit_quality") == "low").sum().values
        rec["low_fit_models"] = low
        rec["action"] = np.where(flagged, "Test incrementality",
                                 np.where(chg >= 0.10, "Scale up", np.where(chg <= -0.10, "Cut / reallocate", "Maintain")))
        rec["confidence"] = np.where(flagged, "Low (models disagree)",
                                     np.where((agree >= .99) & (low <= 1), "High", np.where(agree >= .75, "Medium", "Low")))
        rec["note"] = np.where(
            ratio.values > 2, "Closer: last-touch ROAS is >2x first-touch. Likely harvests demand created elsewhere - validate with a holdout before scaling.",
            np.where(ratio.values < 0.5, "Introducer: last-touch undervalues it (first-touch ROAS >2x). Don't cut on last-click alone - validate with a geo/holdout test.", ""))
        rec = rec.reset_index().rename(columns={"index": "campaign_key"}).sort_values("change_pct", ascending=False)

        base = {m: float(R[i].sum()) for i, m in enumerate(MODELS)}
        new = {m: float((R[i] * (x / S) ** B[i]).sum()) for i, m in enumerate(MODELS)}
        summary = {
            "total_paid_budget": round(float(S.sum()), 2), "campaigns": len(camps),
            "budget_moved": round(float(np.clip(x - S, 0, None).sum()), 2),
            "budget_moved_pct": round(100 * float(np.clip(x - S, 0, None).sum() / S.sum()), 1),
            "projected_revenue_change_by_model": {m: round(new[m] - base[m], 0) for m in MODELS},
            "projected_revenue_change_pct_by_model": {m: round(100 * (new[m] - base[m]) / base[m], 1) for m in MODELS},
            "worst_case_change_pct": round(min(100 * (new[m] - base[m]) / base[m] for m in MODELS), 1),
            "mean_change_pct": round(float(np.mean([100 * (new[m] - base[m]) / base[m] for m in MODELS])), 1),
            "scale_up": rec[rec.action == "Scale up"].campaign_key.tolist(),
            "cut": rec[rec.action == "Cut / reallocate"].campaign_key.tolist(),
            "test_incrementality": rec[rec.action == "Test incrementality"].campaign_key.tolist(),
            "elasticity_by_campaign": {r.campaign_key: round(float(r.beta_median), 3) for r in rec.itertuples()},
        }
        wh.write_df(rec, cfg.ML_SCHEMA, "budget_recommendations")
        wh.write_df(curves, cfg.ML_SCHEMA, "response_curves")
    cfg.REPORTS_DIR.mkdir(exist_ok=True)
    (cfg.REPORTS_DIR / "budget_summary.json").write_text(json.dumps(summary, indent=2))
    return summary
