"""Accuracy, reconciliation and parity checks -> reports/metrics.json and reports/test_results.md.

Ground-truth based metrics (identity, attribution, response curves) need the simulator's truth tables, so they only run on the
local DuckDB demo.  Reconciliation, SQL-vs-Python parity, CLV back-test and dbt test counts also run on BigQuery.
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from . import config as cfg
from .attribution import MODELS, attribute, channel_table, total_variation
from .warehouse import Warehouse


def _pairs(n: pd.Series) -> float:
    return float((n * (n - 1) / 2).sum())


def pair_metrics(pred: pd.Series, true: pd.Series) -> dict:
    df = pd.DataFrame({"p": pred.values, "t": true.values})
    tp = _pairs(df.groupby(["p", "t"]).size())
    pp, tt = _pairs(df.groupby("p").size()), _pairs(df.groupby("t").size())
    prec, rec = tp / pp if pp else 1.0, tp / tt if tt else 1.0
    return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0}


# ----------------------------------------------------------------------------------------------- identity
def identity_metrics(wh: Warehouse) -> dict:
    m, ml, tr = cfg.dbt_schema("marts"), cfg.ML_SCHEMA, cfg.TRUTH_SCHEMA
    sessions = wh.query(f"select session_key, source_system, device_id, person_id, is_identified from {wh.fq(m, 'fct_sessions')}")
    truth = wh.query(f"select session_key, true_person_id from {wh.fq(tr, 'truth_sessions')}")
    crm_truth = wh.query(f"select crm_customer_id, true_person_id, dup_kind from {wh.fq(tr, 'truth_crm_map')}")
    df = sessions.merge(truth, on="session_key")
    df = df[df.true_person_id.isin(set(crm_truth.true_person_id))].copy()  # sessions of people who are in the CRM
    df["node_key"] = np.where(df.source_system == "ga4", "ga:", "sa:") + df.device_id
    naive = wh.query(f"select node_key, person_id as naive_person from {wh.fq(ml, 'identity_nodes_naive')}")
    df = df.merge(naive, on="node_key", how="left")
    df["naive_person"] = df.naive_person.fillna("anon:" + df.device_id)
    out = {
        "sessions_evaluated": int(len(df)),
        "session_link_rate": round(float(df.is_identified.mean()), 4),
        "guarded": pair_metrics(df.person_id, df.true_person_id),
        "naive_connected_components": pair_metrics(df.naive_person, df.true_person_id),
    }
    nodes = wh.query(f"select node_value as crm_customer_id, person_id from {wh.fq(ml, 'identity_nodes')} where node_type = 'crm'")
    nn = wh.query(f"select node_value as crm_customer_id, person_id from {wh.fq(ml, 'identity_nodes_naive')} where node_type = 'crm'")
    for name, n in (("guarded", nodes), ("naive_connected_components", nn)):
        j = n.merge(crm_truth, on="crm_customer_id")
        wrong = j.groupby("person_id").true_person_id.nunique()
        out[name]["false_merged_person_clusters"] = int((wrong > 1).sum())
        dup_people = j[j.dup_kind.notna()].true_person_id.unique()
        per_true = j.groupby("true_person_id").person_id.nunique()
        out[name]["crm_duplicate_recall"] = round(float((per_true.reindex(dup_people) == 1).mean()), 4) if len(dup_people) else None
    out["crm_duplicate_people_in_truth"] = int(crm_truth[crm_truth.dup_kind.notna()].true_person_id.nunique())
    # shared devices (two real people on one browser)
    per_dev = truth.merge(sessions[["session_key", "device_id"]], on="session_key").groupby("device_id").true_person_id.nunique()
    true_shared = set(per_dev[per_dev > 1].index)
    flagged = wh.query(f"select node_value from {wh.fq(ml, 'identity_nodes')} where is_shared_device and node_type in ('ga','sa')")
    flagged = set(flagged.node_value) & set(sessions.device_id)  # count browsers that actually produced sessions (ga + app ids)
    tp = len(flagged & true_shared)
    out["shared_devices"] = {"truly_shared": len(true_shared), "flagged": len(flagged), "flagged_correctly": tp,
                             "precision": round(tp / len(flagged), 4) if flagged else None, "recall": round(tp / len(true_shared), 4) if true_shared else None}
    # channel classification: SQL macro vs what the simulator really sent
    ch = sessions.merge(wh.query(f"select session_key, channel_group as true_channel from {wh.fq(tr, 'truth_sessions')}"), on="session_key")
    cls = ch.merge(wh.query(f"select session_key, channel_group from {wh.fq(m, 'fct_sessions')}"), on="session_key")
    out["channel_classification_accuracy"] = round(float((cls.channel_group == cls.true_channel).mean()), 4)
    out["session_keys_matching_truth"] = round(float(len(ch) / len(truth)), 4)
    return out


# ----------------------------------------------------------------------------------------------- reconciliation
def reconciliation_metrics(wh: Warehouse) -> dict:
    m = cfg.dbt_schema("marts")
    o = wh.query(f"""select
        sum(case when order_channel in ('web','app') and in_tracking_window then 1 else 0 end) as online_orders,
        sum(case when order_channel in ('web','app') and in_tracking_window and is_tracked_online then 1 else 0 end) as tracked_orders,
        sum(case when order_channel = 'web' and in_tracking_window then 1 else 0 end) as web_orders,
        sum(case when order_channel = 'web' and in_tracking_window and is_tracked_online then 1 else 0 end) as web_tracked,
        sum(case when is_tracked_online and revenue_gap_vs_tracker < 0.01 then 1 else 0 end) as exact_revenue,
        sum(case when is_tracked_online then 1 else 0 end) as tracked_total,
        avg(case when is_tracked_online then revenue_gap_vs_tracker end) as mean_abs_gap
        from {wh.fq(m, 'fct_orders')}""").iloc[0]
    dup = wh.query(f"""select
        (select sum(case when event_name = 'purchase' then 1 else 0 end) from {wh.fq(cfg.dbt_schema('staging'), 'stg_ga4__events')}) as purchase_events,
        (select count(*) from {wh.fq(cfg.dbt_schema('staging'), 'stg_ga4__purchases')}) as unique_transactions""").iloc[0]
    cov = wh.query(f"""select model,
        sum(case when channel_group <> 'Unattributed' then credited_revenue else 0 end) / sum(credited_revenue) as attributed_share
        from {wh.fq(m, 'fct_attribution_credits')} group by model""")
    return {
        "online_orders_in_window": int(o.online_orders), "online_orders_found_in_tracking": int(o.tracked_orders),
        "online_order_match_rate": round(float(o.tracked_orders / o.online_orders), 4),
        "web_order_ga4_match_rate": round(float(o.web_tracked / o.web_orders), 4) if o.web_orders else None,
        "tracked_orders_with_exact_revenue_match": round(float(o.exact_revenue / o.tracked_total), 4),
        "mean_abs_revenue_gap_usd": round(float(o.mean_abs_gap), 3),
        "ga4_purchase_events": int(dup.purchase_events), "ga4_unique_transactions": int(dup.unique_transactions),
        "ga4_duplicate_purchase_events_removed": int(dup.purchase_events - dup.unique_transactions),
        "revenue_attributed_to_a_channel_pct": {r.model: round(100 * float(r.attributed_share), 1) for r in cov.itertuples()},
    }


# ----------------------------------------------------------------------------------------------- attribution
def _load_paths(wh: Warehouse):
    m = cfg.dbt_schema("marts")
    conv = wh.query(f"select order_id, person_id, ordered_at, net_revenue, is_first_order from {wh.fq(m, 'fct_orders')} where is_conversion and in_tracking_window")
    sess = wh.query(f"select session_key, person_id, session_start_ts, channel_group, campaign_key from {wh.fq(m, 'fct_sessions')}")
    for df, c in ((conv, "ordered_at"), (sess, "session_start_ts")):
        df[c] = pd.to_datetime(df[c]).dt.tz_localize(None) if getattr(pd.to_datetime(df[c]).dt, "tz", None) is not None else pd.to_datetime(df[c])
    return conv, sess


def parity_metrics(wh: Warehouse) -> dict:
    conv, sess = _load_paths(wh)
    py = channel_table(attribute(conv, sess))
    sql = wh.query(f"select model, channel_group, attributed_revenue, attributed_orders from {wh.fq(cfg.dbt_schema('marts'), 'mart_attribution_by_channel')}")
    j = py.merge(sql, on=["model", "channel_group"], how="outer").fillna(0)
    return {"max_abs_revenue_diff_usd": round(float((j.revenue - j.attributed_revenue).abs().max()), 6),
            "max_abs_order_diff": round(float((j.orders - j.attributed_orders).abs().max()), 6),
            "rows_compared": int(len(j))}


def attribution_truth_metrics(wh: Warehouse) -> dict:
    m, tr = cfg.dbt_schema("marts"), cfg.TRUTH_SCHEMA
    conv, sess = _load_paths(wh)
    sess_id = wh.query(f"select session_key from {wh.fq(m, 'fct_sessions')} where is_identified")
    tsess = wh.query(f"select session_key, true_person_id as s_true from {wh.fq(tr, 'truth_sessions')}")
    torder = wh.query(f"select order_id, true_person_id as o_true from {wh.fq(tr, 'truth_orders')}")
    camps = wh.query(f"select campaign_key, truth_weight, is_paid from {wh.fq(tr, 'truth_campaigns')}")
    # touchpoints the pipeline could see AND that really belong to the buyer
    t = conv.merge(torder, on="order_id").merge(sess[sess.session_key.isin(sess_id.session_key)], on="person_id").merge(tsess, on="session_key")
    t = t[(t.s_true == t.o_true) & (t.session_start_ts <= t.ordered_at) & (t.session_start_ts >= t.ordered_at - pd.Timedelta(days=cfg.LOOKBACK_DAYS))].copy()
    t["hours"] = (t.ordered_at - t.session_start_ts).dt.total_seconds() / 3600
    t = t.merge(camps[["campaign_key", "truth_weight"]], on="campaign_key", how="left").fillna({"truth_weight": 0.5})
    t = t.sort_values(["order_id", "session_start_ts", "session_key"])
    t["pos"] = t.groupby("order_id").cumcount()
    # ground-truth credit: incrementality weight x recency (7-day decay) x 1.5 "introducer" bonus for the first touch
    t["w"] = t.truth_weight * np.exp(-t.hours / (7 * 24)) * np.where(t.pos == 0, 1.5, 1.0)
    t["credit"] = t.w / t.groupby("order_id").w.transform("sum")
    t["rev"] = t.credit * t.net_revenue
    eval_orders = set(t.order_id)
    truth_ch, truth_cp = t.groupby("channel_group").rev.sum(), t.groupby("campaign_key").rev.sum()

    credits = wh.query(f"select model, order_id, channel_group, campaign_key, credited_revenue from {wh.fq(m, 'fct_attribution_credits')}")
    credits = credits[credits.order_id.isin(eval_orders) & (credits.channel_group != "Unattributed")]
    spend = wh.query(f"select campaign_key, max(spend) as spend from {wh.fq(m, 'mart_campaign_roi')} where is_paid group by campaign_key").set_index("campaign_key").spend
    paid = list(spend.index)
    truth_roas = (truth_cp.reindex(paid).fillna(0) / spend)

    def evaluate(credit_df: pd.DataFrame) -> dict:
        res = {}
        for mod in MODELS:
            c = credit_df[credit_df.model == mod]
            ch, cp = c.groupby("channel_group").credited_revenue.sum(), c.groupby("campaign_key").credited_revenue.sum()
            roas = cp.reindex(paid).fillna(0) / spend
            top3_true, top3_mod = set(truth_roas.nlargest(3).index), set(roas.nlargest(3).index)
            res[mod] = {"channel_tvd": round(total_variation(ch, truth_ch), 4), "campaign_tvd": round(total_variation(cp, truth_cp), 4),
                        "campaign_roas_spearman": round(float(roas.rank().corr(truth_roas.rank())), 3),
                        "top3_campaigns_overlap": len(top3_true & top3_mod)}
        return res

    out = {"orders_evaluated": len(eval_orders), "note": "TVD = total variation distance of revenue shares vs ground truth (0 = perfect, 1 = completely different)",
           "default_policy_dbt": evaluate(credits)}
    # what-if: how much does the Direct policy matter?  (pandas re-implementation, restricted to the same orders)
    sub_conv = conv[conv.order_id.isin(eval_orders)]
    for pol in ("deprioritize", "include"):
        py = attribute(sub_conv, sess[sess.session_key.isin(sess_id.session_key)], direct_policy=pol)
        out[f"direct_policy_{pol}"] = evaluate(py[py.channel_group != "Unattributed"])
    # also a blind baseline: spread revenue evenly over channels present in truth
    flat = pd.Series(1.0, index=truth_ch.index)
    out["uniform_baseline_channel_tvd"] = round(total_variation(flat, truth_ch), 4)
    out["truth_channel_share_pct"] = {k: round(100 * v, 1) for k, v in (truth_ch / truth_ch.sum()).sort_values(ascending=False).items()}
    out["truth_campaign_roas"] = {k: round(float(v), 2) for k, v in truth_roas.sort_values(ascending=False).items()}
    return out


def response_curve_metrics(wh: Warehouse) -> dict | None:
    try:
        rec = wh.query(f"select campaign_key, beta_median from {wh.fq(cfg.ML_SCHEMA, 'budget_recommendations')}")
        truth = wh.query(f"select campaign_key, true_elasticity from {wh.fq(cfg.TRUTH_SCHEMA, 'truth_campaigns')} where is_paid")
    except Exception:
        return None
    j = rec.merge(truth, on="campaign_key")
    err = (j.beta_median - j.true_elasticity).abs()
    return {"campaigns": int(len(j)), "mean_abs_error": round(float(err.mean()), 3), "max_abs_error": round(float(err.max()), 3),
            "within_0_15": int((err <= 0.15).sum()),
            "estimated_vs_true": {r.campaign_key: [round(float(r.beta_median), 2), round(float(r.true_elasticity), 2)] for r in j.itertuples()}}


# ----------------------------------------------------------------------------------------------- dbt results
def dbt_metrics() -> dict:
    files = sorted(cfg.REPORTS_DIR.glob("dbt_stage*_run_results.json")) or [cfg.DBT_TARGET_DIR / "run_results.json"]
    tot = {"models": {}, "tests": {}, "unit_tests": {}, "seeds": {}}
    for f in files:
        if not f.exists():
            continue
        for r in json.loads(f.read_text())["results"]:
            kind = r["unique_id"].split(".")[0]
            key = {"model": "models", "test": "tests", "unit_test": "unit_tests", "seed": "seeds"}.get(kind)
            if key:
                tot[key][r["status"]] = tot[key].get(r["status"], 0) + 1
    return tot


def write_test_results(m: dict) -> None:
    """Human-readable test & accuracy report (reports/test_results.md) rendered from metrics.json."""
    L = ["# Test results and accuracy numbers", "", f"_Generated {m['generated_at']} on target **{m['target']}** by `python -m customer360 evaluate`._", ""]
    d = m.get("dbt", {})
    L += ["## 1. dbt build", "", f"- models built: **{d.get('models', {}).get('success', 0)}**, seeds: {d.get('seeds', {}).get('success', 0)}",
          f"- data tests: **{d.get('tests', {}).get('pass', 0)} passed**, {d.get('tests', {}).get('warn', 0)} warnings, {d.get('tests', {}).get('fail', 0) + d.get('tests', {}).get('error', 0)} failures",
          f"- dbt unit tests: **{d.get('unit_tests', {}).get('pass', 0)} passed**, {d.get('unit_tests', {}).get('fail', 0) + d.get('unit_tests', {}).get('error', 0)} failures", ""]
    r = m["reconciliation"]
    L += ["## 2. Reconciliation: tracking vs CRM (system of record)", "",
          "| check | result |", "|---|---|",
          f"| online CRM orders in window found in GA4 / Segment | {r['online_orders_found_in_tracking']:,} of {r['online_orders_in_window']:,} = **{100 * r['online_order_match_rate']:.1f}%** |",
          f"| web orders found in GA4 | {100 * r['web_order_ga4_match_rate']:.1f}% |",
          f"| matched orders with exactly equal revenue | {100 * r['tracked_orders_with_exact_revenue_match']:.1f}% (mean abs gap ${r['mean_abs_revenue_gap_usd']:.2f}) |",
          f"| double-fired GA4 purchase events removed | {r['ga4_duplicate_purchase_events_removed']} of {r['ga4_purchase_events']:,} |",
          f"| revenue attributed to a real channel (rest = Unattributed) | {r['revenue_attributed_to_a_channel_pct']['time_decay']:.1f}% |", ""]
    p = m["attribution_sql_vs_python_parity"]
    L += ["## 3. SQL vs Python parity (attribution)", "",
          f"Independent pandas re-implementation vs the dbt models over {p['rows_compared']} (model x channel) cells: max revenue difference **${p['max_abs_revenue_diff_usd']:.4f}**, max order difference {p['max_abs_order_diff']}.", ""]
    if "identity_resolution" in m:
        i = m["identity_resolution"]
        g, n = i["guarded"], i["naive_connected_components"]
        L += ["## 4. Identity resolution vs simulator ground truth", "",
              f"Pairwise precision / recall over {i['sessions_evaluated']:,} sessions of CRM customers; {100 * i['session_link_rate']:.1f}% of those sessions were linked to a person.", "",
              "| approach | precision | recall | F1 | wrongly merged people | CRM duplicates found |", "|---|---|---|---|---|---|",
              f"| **guarded graph (this project)** | {g['precision']:.3f} | {g['recall']:.3f} | {g['f1']:.3f} | {g['false_merged_person_clusters']} | {100 * g['crm_duplicate_recall']:.0f}% of {i['crm_duplicate_people_in_truth']} |",
              f"| naive connected components | {n['precision']:.3f} | {n['recall']:.3f} | {n['f1']:.3f} | {n['false_merged_person_clusters']} | {100 * n['crm_duplicate_recall']:.0f}% |", "",
              f"- shared devices (two people, one browser): {i['shared_devices']['flagged_correctly']} of {i['shared_devices']['truly_shared']} detected, precision {i['shared_devices']['precision']:.2f}",
              f"- channel classification (dbt macro vs what was actually sent): **{100 * i['channel_classification_accuracy']:.1f}%**; session keys reproducible from source data: {100 * i['session_keys_matching_truth']:.1f}%", ""]
        a = m["attribution_vs_ground_truth"]
        t = a["default_policy_dbt"]
        L += ["## 5. Attribution models vs simulated ground truth", "", f"{a['orders_evaluated']:,} orders. TVD = total-variation distance between the model's revenue shares and the true shares (0 = perfect). A uniform guess scores {a['uniform_baseline_channel_tvd']:.3f}.", "",
              "| model | channel TVD | campaign TVD | campaign-ROAS rank correlation (Spearman) | top-3 campaigns found |", "|---|---|---|---|---|"]
        L += [f"| {k.replace('_', ' ')} | {v['channel_tvd']:.3f} | {v['campaign_tvd']:.3f} | {v['campaign_roas_spearman']:.2f} | {v['top3_campaigns_overlap']} of 3 |" for k, v in t.items()]
        inc = a["direct_policy_include"]
        L += ["", "Effect of the Direct-traffic policy (channel TVD, deprioritise -> include): " + ", ".join(f"{k.replace('_', ' ')} {t[k]['channel_tvd']:.3f} -> {inc[k]['channel_tvd']:.3f}" for k in t), ""]
        rc = m.get("response_curve_recovery")
        if rc:
            L += ["## 6. Response-curve (elasticity) recovery", "", f"Estimated spend elasticity vs the true value used to simulate costs: mean absolute error **{rc['mean_abs_error']:.3f}**, max {rc['max_abs_error']:.3f}; {rc['within_0_15']} of {rc['campaigns']} campaigns within +/-0.15.", ""]
    c = m.get("clv_backtest")
    if c:
        L += ["## 7. CLV back-test (BG/NBD x Gamma-Gamma)", "", f"Calibrated on orders to {c['calibration_end']}, forecast the next 92 days for {c['customers']:,} customers.", "",
              "| metric | value |", "|---|---|",
              f"| repeat orders predicted vs actual | {c['holdout_repeat_orders_predicted']:.0f} vs {c['holdout_repeat_orders_actual']:.0f} ({c['total_orders_error_pct']:+.1f}%) |",
              f"| per-customer MAE: model vs naive run-rate | {c['mae_per_customer_model']:.3f} vs {c['mae_per_customer_naive_runrate']:.3f} ({c['mae_improvement_vs_naive_pct']:.1f}% better) |",
              f"| correlation predicted vs actual | {c['correlation_pred_vs_actual']:.2f} |",
              f"| order-value MAPE: Gamma-Gamma vs population mean | {c['aov_mape_model_pct']}% vs {c['aov_mape_population_mean_pct']}% |", ""]
    b = m.get("budget_recommendation")
    if b:
        L += ["## 8. Budget recommendation", "", f"Budget moved: ${b['budget_moved']:,.0f} ({b['budget_moved_pct']}% of ${b['total_paid_budget']:,.0f}); projected attributed-revenue change by model: "
              + ", ".join(f"{k.replace('_', ' ')} {v:+.1f}%" for k, v in b["projected_revenue_change_pct_by_model"].items()) + ".", ""]
    tm = m.get("pipeline_timings_seconds")
    if tm:
        L += ["## 9. Performance (single CPU)", "", "| step | seconds |", "|---|---|"] + [f"| {k} | {v} |" for k, v in tm.items()] + [""]
    dv = m.get("data_volumes")
    if dv:
        L += ["## 10. Data volumes (local demo)", "", "| table | rows |", "|---|---|"] + [f"| {k} | {v:,} |" if isinstance(v, int) else f"| {k} | {v} |" for k, v in dv.items()] + [""]
    (cfg.REPORTS_DIR / "test_results.md").write_text("\n".join(L))


def run() -> dict:
    metrics: dict = {"generated_at": datetime.now().isoformat(timespec="seconds"), "target": cfg.TARGET}
    with Warehouse() as wh:
        metrics["reconciliation"] = reconciliation_metrics(wh)
        metrics["attribution_sql_vs_python_parity"] = parity_metrics(wh)
        has_truth = wh.table_exists(cfg.TRUTH_SCHEMA, "truth_sessions")
        if has_truth:
            metrics["identity_resolution"] = identity_metrics(wh)
            metrics["attribution_vs_ground_truth"] = attribution_truth_metrics(wh)
            metrics["response_curve_recovery"] = response_curve_metrics(wh)
        else:
            metrics["ground_truth"] = "not available on this target (real GA4 data has no ground truth)"
    bt = cfg.REPORTS_DIR / "clv_backtest.json"
    if bt.exists():
        metrics["clv_backtest"] = json.loads(bt.read_text())
    bs = cfg.REPORTS_DIR / "budget_summary.json"
    if bs.exists():
        metrics["budget_recommendation"] = json.loads(bs.read_text())
    tm = cfg.REPORTS_DIR / "timings.json"
    if tm.exists():
        metrics["pipeline_timings_seconds"] = json.loads(tm.read_text())
    gs = cfg.DATA_DIR / "generation_summary.json"
    if gs.exists():
        metrics["data_volumes"] = json.loads(gs.read_text())
    metrics["dbt"] = dbt_metrics()
    cfg.REPORTS_DIR.mkdir(exist_ok=True)
    (cfg.REPORTS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    write_test_results(metrics)
    return metrics
