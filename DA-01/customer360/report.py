"""Charts (reports/figures/*.png) and the auto-generated findings document (reports/findings.md).

Every number in findings.md is read from the warehouse / metrics.json at run time - nothing is hand-typed.
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config as cfg
from .attribution import MODELS
from .warehouse import Warehouse

MODEL_LABEL = {"first_touch": "First touch", "last_touch": "Last touch", "linear": "Linear", "time_decay": "Time decay"}
MODEL_COLOR = {"first_touch": "#1f77b4", "last_touch": "#d62728", "linear": "#2ca02c", "time_decay": "#ff7f0e"}
ACTION_COLOR = {"Scale up": "#2ca02c", "Cut / reallocate": "#d62728", "Maintain": "#7f7f7f", "Test incrementality": "#ff9f1c"}
FIG = cfg.REPORTS_DIR / "figures"
plt.rcParams.update({"figure.dpi": 130, "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.alpha": .25,
                     "font.size": 9, "axes.titleweight": "bold", "axes.titlesize": 11})


def short(key: str) -> str:
    s, m, c = key.split("|")
    return f"{s} / {c}"


def money(x) -> str:
    return f"${x:,.0f}"


def money_plot(x) -> str:
    return "\\$" + f"{x:,.0f}"  # escaped: matplotlib would otherwise treat $...$ as math text


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(str(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join(out)


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(FIG / name, bbox_inches="tight")
    plt.close(fig)


def run() -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    m, ml = cfg.dbt_schema("marts"), cfg.ML_SCHEMA
    margin = cfg.GROSS_MARGIN
    with Warehouse() as wh:
        comp = wh.query(f"select * from {wh.fq(m, 'mart_attribution_comparison')}")
        camp = wh.query(f"select * from {wh.fq(m, 'mart_campaign_roi')} where is_paid")
        chan = wh.query(f"select * from {wh.fq(m, 'mart_channel_roi')}")
        kpi = wh.query(f"select * from {wh.fq(m, 'mart_daily_kpis')} order by kpi_date")
        rfm = wh.query(f"select rfm_segment, count(*) as customers, sum(monetary) as revenue, avg(monetary) as avg_revenue, avg(recency_days) as recency_days "
                       f"from {wh.fq(m, 'customer_rfm')} group by rfm_segment")
        prof = wh.query(f"select lifecycle_stage, clv_tier, count(*) as customers, sum(historical_clv_revenue) as historical_revenue, sum(predicted_clv_12m_revenue) as forecast_revenue "
                        f"from {wh.fq(m, 'customer_profile')} group by lifecycle_stage, clv_tier")
        rec = wh.query(f"select * from {wh.fq(ml, 'budget_recommendations')}")
    metrics = json.loads((cfg.REPORTS_DIR / "metrics.json").read_text()) if (cfg.REPORTS_DIR / "metrics.json").exists() else {}
    budget = json.loads((cfg.REPORTS_DIR / "budget_summary.json").read_text())
    bt = json.loads((cfg.REPORTS_DIR / "clv_backtest.json").read_text())
    truth = metrics.get("attribution_vs_ground_truth")
    kpi["kpi_date"] = pd.to_datetime(kpi.kpi_date)

    # 1 ---- attribution model comparison
    c = comp.sort_values("share_time_decay")
    fig, ax = plt.subplots(figsize=(8, 5))
    h = 0.2
    for i, mo in enumerate(MODELS):
        ax.barh(np.arange(len(c)) + (i - 1.5) * h, 100 * c[f"share_{mo}"], h, label=MODEL_LABEL[mo], color=MODEL_COLOR[mo])
    ax.set_yticks(range(len(c)), c.channel_group)
    ax.set_xlabel("Share of attributed revenue (%)")
    ax.set_title("Same revenue, four stories: channel credit depends on the model")
    ax.legend(loc="lower right")
    save(fig, "01_attribution_model_comparison.png")

    # 2 ---- campaign ROAS by model vs platform claims
    piv = camp.pivot(index="campaign_key", columns="model", values="roas")
    plat = camp.groupby("campaign_key").platform_roas.first()
    order = piv.median(axis=1).sort_values().index
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    for i, k in enumerate(order):
        ax.hlines(i, piv.loc[k].min(), piv.loc[k].max(), color="#bbbbbb", lw=2, zorder=1)
        for mo in MODELS:
            ax.scatter(piv.loc[k, mo], i, color=MODEL_COLOR[mo], s=42, zorder=3, label=MODEL_LABEL[mo] if i == 0 else None)
        ax.scatter(plat[k], i, marker="x", color="black", s=36, zorder=3, label="Ad platform's own claim" if i == 0 else None)
    ax.axvline(1 / margin, color="red", ls="--", lw=1)
    ax.set_ylim(-1.3, len(order) - .4)
    ax.text(1 / margin + .1, -1.0, f"break-even ROAS = 1/margin = {1 / margin:.2f}", color="red", fontsize=8, va="center")
    ax.set_yticks(range(len(order)), [short(k) for k in order])
    ax.set_xlabel("ROAS (attributed revenue / ad spend)")
    ax.set_title("Campaign ROAS: models disagree - and platforms over-claim")
    ax.legend(loc="lower right", fontsize=8)
    save(fig, "02_campaign_roas_by_model.png")

    # 3 ---- budget recommendation
    r = rec.sort_values("change_pct")
    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.barh([short(k) for k in r.campaign_key], 100 * r.change_pct, color=[ACTION_COLOR[a] for a in r.action])
    for i, (v, cur, new) in enumerate(zip(r.change_pct, r.current_spend, r.recommended_spend)):
        ax.text(100 * v + (1 if v >= 0 else -1), i, f"{money_plot(cur)} → {money_plot(new)}", va="center", ha="left" if v >= 0 else "right", fontsize=7.5)
    ax.axvline(0, color="black", lw=.8)
    ax.set_xlim(-60, 60)
    ax.set_xlabel("Recommended change in spend (%) - budget neutral")
    ax.set_title("Where to move budget")
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=v) for v in ACTION_COLOR.values()], labels=list(ACTION_COLOR), loc="lower right", fontsize=8)
    save(fig, "03_budget_recommendation.png")

    # 4 ---- RFM
    s = rfm.sort_values("revenue")
    fig, axs = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)
    axs[0].barh(s.rfm_segment, s.customers, color="#4c78a8")
    axs[0].set_title("Customers")
    axs[1].barh(s.rfm_segment, 100 * s.revenue / s.revenue.sum(), color="#f58518")
    axs[1].set_title("Share of revenue (%)")
    save(fig, "04_rfm_segments.png")

    # 5 ---- CLV back-test
    d = pd.DataFrame(bt["decile_calibration"])
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(d.decile - .2, d.predicted, .4, label="Predicted", color="#4c78a8")
    ax.bar(d.decile + .2, d.actual, .4, label="Actual", color="#f58518")
    ax.set_xlabel("Customer decile by predicted repeat purchases (1 = lowest)")
    ax.set_ylabel("Repeat orders in 92-day holdout")
    ax.set_xticks(range(1, 11))
    ax.set_title(f"BG/NBD back-test: total error {bt['total_orders_error_pct']:+.1f}%, corr {bt['correlation_pred_vs_actual']:.2f}")
    ax.legend()
    save(fig, "05_clv_backtest.png")

    # 6 ---- attribution vs ground truth
    if truth:
        t = pd.DataFrame({mo: truth["default_policy_dbt"][mo] for mo in MODELS}).T
        fig, axs = plt.subplots(1, 2, figsize=(9, 3.8))
        axs[0].bar([MODEL_LABEL[x] for x in t.index], t.channel_tvd, color=[MODEL_COLOR[x] for x in t.index])
        axs[0].axhline(truth["uniform_baseline_channel_tvd"], color="grey", ls="--")
        axs[0].text(0, truth["uniform_baseline_channel_tvd"] + .005, "uniform guess", color="grey", fontsize=8)
        axs[0].set_title("Channel credit error vs truth (lower = better)")
        axs[1].bar([MODEL_LABEL[x] for x in t.index], t.campaign_roas_spearman, color=[MODEL_COLOR[x] for x in t.index])
        axs[1].set_title("Campaign ROAS ranking vs truth (Spearman)")
        axs[1].set_ylim(0, 1)
        save(fig, "06_attribution_vs_truth.png")

    # 7 ---- daily KPIs
    fig, axs = plt.subplots(2, 1, figsize=(9, 5.5), sharex=True)
    axs[0].bar(kpi.kpi_date, kpi.net_revenue, color="#4c78a8", label="Net revenue")
    axs[0].plot(kpi.kpi_date, kpi.ad_spend, color="#d62728", lw=1.4, label="Ad spend")
    axs[0].legend()
    axs[0].set_title("Daily revenue and ad spend")
    axs[1].plot(kpi.kpi_date, kpi.blended_roas.rolling(7, min_periods=1).mean(), color="#2ca02c")
    axs[1].set_title("Blended ROAS (7-day mean)")
    save(fig, "07_daily_kpis.png")

    # 8 ---- CAC vs CLV of acquired customers (time decay)
    ch = chan[(chan.model == "time_decay") & chan.is_paid]
    fig, ax = plt.subplots(figsize=(7, 4))
    x = np.arange(len(ch))
    ax.bar(x - .2, ch.cac_new_customer, .4, label="CAC (spend / new customers)", color="#d62728")
    ax.bar(x + .2, ch.avg_new_customer_clv, .4, label="12-month CLV of acquired customers", color="#2ca02c")
    for i, v in enumerate(ch.ltv_to_cac):
        ax.text(i, max(ch.cac_new_customer.iloc[i], ch.avg_new_customer_clv.iloc[i]) * 1.03, f"LTV:CAC {v:.1f}x", ha="center", fontsize=8)
    ax.set_xticks(x, ch.channel_group)
    ax.set_title("Unit economics of paid channels (time-decay attribution)")
    ax.legend(fontsize=8)
    save(fig, "08_channel_unit_economics.png")

    write_findings(comp, camp, chan, kpi, rfm, prof, rec, budget, bt, metrics, truth)
    print(f"Wrote {len(list(FIG.glob('*.png')))} figures + reports/findings.md")


def write_findings(comp, camp, chan, kpi, rfm, prof, rec, budget, bt, metrics, truth) -> None:
    margin = cfg.GROSS_MARGIN
    td = chan[chan.model == "time_decay"]
    revenue, spend, orders = kpi.net_revenue.sum(), kpi.ad_spend.sum(), kpi.orders.sum()
    new_c = kpi.new_customers.sum()
    big = comp.sort_values("share_spread_pp", ascending=False).iloc[0]
    L = []
    L.append("# Findings and budget recommendations\n")
    L.append(f"_Auto-generated by `python -m customer360 report` from run data (target: **{cfg.TARGET}**). Window {cfg.START_DATE} to {cfg.END_DATE}._\n")
    L.append("## 1. Headlines\n")
    L.append(f"- **{int(orders):,} completed orders, {money(revenue)} net revenue; {money(spend)} ad spend -> blended ROAS (MER) {revenue / spend:.2f}x**, "
             f"blended CAC {money(spend / max(new_c, 1))} per new customer ({int(new_c):,} new customers).")
    L.append(f"- **The attribution model changes the answer.** {big.channel_group} receives {100 * big.share_first_touch:.1f}% of revenue under first touch, "
             f"{100 * big.share_last_touch:.1f}% under last touch, {100 * big.share_linear:.1f}% linear and {100 * big.share_time_decay:.1f}% time-decay "
             f"(a {big.share_spread_pp:.1f} percentage-point swing).")
    over = (camp.groupby("campaign_key").platform_roas.first() / camp[camp.model == "time_decay"].set_index("campaign_key").roas).median()
    L.append(f"- **Ad platforms over-claim.** Platform-reported ROAS is a median {over:.1f}x the time-decay ROAS.")
    L.append(f"- **Budget:** moving {money(budget['budget_moved'])} ({budget['budget_moved_pct']}% of the {money(budget['total_paid_budget'])} paid budget) is projected to change attributed "
             f"revenue by {budget['mean_change_pct']:+.1f}% on average across models (worst model {budget['worst_case_change_pct']:+.1f}%). "
             f"{len(budget['test_incrementality'])} of {budget['campaigns']} campaigns are flagged **Test incrementality**: the models disagree about them too much for attribution alone to decide.")
    L.append("\n## 2. Attribution models side by side (share of attributed revenue)\n")
    t = comp.sort_values("share_time_decay", ascending=False)
    L.append(md_table(pd.DataFrame({"Channel": t.channel_group, "First touch": (100 * t.share_first_touch).round(1).astype(str) + "%",
                                    "Last touch": (100 * t.share_last_touch).round(1).astype(str) + "%", "Linear": (100 * t.share_linear).round(1).astype(str) + "%",
                                    "Time decay": (100 * t.share_time_decay).round(1).astype(str) + "%", "Swing (pp)": t.share_spread_pp.round(1)})))
    L.append("\n![model comparison](figures/01_attribution_model_comparison.png)\n")
    L.append("## 3. Campaign ROI\n")
    wide = camp.pivot(index="campaign_key", columns="model", values="roas")
    td_c = camp[camp.model == "time_decay"].set_index("campaign_key")
    tbl = pd.DataFrame({"Campaign": [short(k) for k in td_c.index], "Spend": td_c.spend.map(money),
                        "ROAS FT / LT / Lin / TD": [" / ".join(f"{wide.loc[k, mo]:.2f}" for mo in MODELS) for k in td_c.index],
                        "Platform ROAS": td_c.platform_roas.round(2), "CPA (TD)": td_c.cpa.map(lambda v: f"${v:,.0f}"),
                        "CAC (TD)": td_c.cac_new_customer.map(lambda v: f"${v:,.0f}"), "LTV:CAC (TD)": td_c.ltv_to_cac.round(2)}).assign(_s=td_c.spend.values).sort_values("_s", ascending=False).drop(columns="_s")
    L.append(md_table(tbl))
    L.append(f"\nBreak-even ROAS on gross profit is 1 / {margin:.2f} = **{1 / margin:.2f}**; anything below it loses money before overheads.\n")
    L.append("![campaign ROAS](figures/02_campaign_roas_by_model.png)\n")
    L.append("## 4. Where to move budget\n")
    r = rec.sort_values("change_pct", ascending=False)
    L.append(md_table(pd.DataFrame({"Campaign": [short(k) for k in r.campaign_key], "Action": r.action, "Current": r.current_spend.map(money),
                                    "Recommended": r.recommended_spend.map(money), "Change": (100 * r.change_pct).round(1).astype(str) + "%",
                                    "Median ROAS": r.roas_median.round(2), "Confidence": r.confidence})))
    L.append("\n![budget](figures/03_budget_recommendation.png)\n")
    notes = r[r.note != ""]
    if len(notes):
        L.append("**Why campaigns are flagged**\n")
        for x in notes.itertuples():
            L.append(f"- `{short(x.campaign_key)}` (last/first-touch ROAS ratio {x.last_vs_first_touch_ratio:.2f}): {x.note}")
    L.append("\n**Method.** Per campaign and per model a power-law response curve (revenue ~ spend^beta, Poisson quasi-likelihood, bootstrap SE, shrunk to a prior) gives marginal ROAS; the same total budget "
             "is re-allocated to equalise marginal ROAS while maximising the average over the four models; campaigns where last-touch ROAS is >2x or <0.5x first-touch ROAS are capped at +/-10% and flagged.\n")
    L.append("**Important:** attribution measures who *gets credit*, not what is *incremental*. Treat \"Scale up / Cut\" as high-confidence only where all models agree; run holdout or geo-lift tests for the flagged campaigns before large moves.\n")
    L.append("## 5. Customer segments\n")
    s = rfm.sort_values("revenue", ascending=False)
    L.append(md_table(pd.DataFrame({"RFM segment": s.rfm_segment, "Customers": s.customers, "% customers": (100 * s.customers / s.customers.sum()).round(1),
                                    "% revenue": (100 * s.revenue / s.revenue.sum()).round(1), "Avg revenue": s.avg_revenue.map(money), "Avg recency (days)": s.recency_days.round(0).astype(int)})))
    L.append("\n![rfm](figures/04_rfm_segments.png)\n")
    life = prof.groupby("lifecycle_stage").agg(customers=("customers", "sum"), historical_revenue=("historical_revenue", "sum"), forecast_revenue=("forecast_revenue", "sum")).reset_index()
    L.append(md_table(pd.DataFrame({"Lifecycle stage": life.lifecycle_stage, "Customers": life.customers, "Historical revenue": life.historical_revenue.map(money), "Forecast 12-mo revenue": life.forecast_revenue.map(money)})))
    atrisk = prof[(prof.lifecycle_stage.isin(["At Risk", "Churned"])) & (prof.clv_tier.isin(["Platinum", "Gold"]))]
    L.append(f"\n- **Win-back priority:** {int(atrisk.customers.sum()):,} Platinum/Gold customers are At Risk or Churned, with {money(atrisk.historical_revenue.sum())} historical revenue.")
    L.append(f"- **CLV model back-test:** forecast {bt['holdout_repeat_orders_predicted']:.0f} vs actual {bt['holdout_repeat_orders_actual']:.0f} repeat orders in the 92-day holdout "
             f"({bt['total_orders_error_pct']:+.1f}%), per-customer MAE {bt['mae_improvement_vs_naive_pct']:.0f}% better than a run-rate baseline.\n")
    if truth:
        t = truth["default_policy_dbt"]
        best = min(MODELS, key=lambda k: t[k]["channel_tvd"])
        L.append("## 6. Validation against simulated ground truth\n")
        L.append(f"The synthetic world knows each touchpoint's true incrementality. Closest to truth at channel level: **{MODEL_LABEL[best]}** (TVD {t[best]['channel_tvd']:.3f}; "
                 f"a uniform guess scores {truth['uniform_baseline_channel_tvd']:.3f}). Last-touch ranks campaign ROAS with Spearman rho = {t['last_touch']['campaign_roas_spearman']:.2f} "
                 f"vs {t['linear']['campaign_roas_spearman']:.2f} for linear. _These are simulation results - they show the method works and why last-click misleads, not that linear is best on real data._\n")
        L.append("![truth](figures/06_attribution_vs_truth.png)\n")
    L.append("## 7. Limitations\n")
    L.append("- CRM, Segment and ad data are synthetic; absolute numbers are illustrative. Only the method and the pipeline transfer to real data.\n"
             "- Attribution is observational: it cannot separate demand that would have converted anyway (brand search, retargeting, coupon sites).\n"
             "- Paths are left-censored at the start of the tracking window; consent-denied and unlinked devices are invisible (see identity metrics).\n"
             "- Revenue is attributed by touch date for curve fitting; the last 14 days are excluded because their orders are not yet observed.\n")
    (cfg.REPORTS_DIR / "findings.md").write_text("\n".join(L))
