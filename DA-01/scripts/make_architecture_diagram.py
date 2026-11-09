#!/usr/bin/env python
"""Render docs/diagrams/architecture.svg + .png (no graphviz needed).   python scripts/make_architecture_diagram.py"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parents[1] / "docs" / "diagrams"
OUT.mkdir(parents=True, exist_ok=True)
fig, ax = plt.subplots(figsize=(15, 8.2))
ax.set_xlim(0, 150)
ax.set_ylim(0, 82)
ax.axis("off")


def box(x, y, w, h, title, sub="", color="#e8f0fe", edge="#4c78a8", fs=9):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.3,rounding_size=1.2", fc=color, ec=edge, lw=1.4))
    ax.text(x + w / 2, y + h - 2.2, title, ha="center", va="top", fontsize=fs, fontweight="bold")
    if sub:
        ax.text(x + w / 2, y + h - 5.4, sub, ha="center", va="top", fontsize=7.3, color="#333333", linespacing=1.35)


def arrow(x1, y1, x2, y2, label="", color="#555555", rad=0.0):
    ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=12, lw=1.3, color=color, connectionstyle=f"arc3,rad={rad}"))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 1.2, label, ha="center", fontsize=7, color=color)


def lane(x, w, title):
    ax.add_patch(FancyBboxPatch((x, 2), w, 74, boxstyle="round,pad=0.2,rounding_size=1.5", fc="#fafafa", ec="#dddddd", lw=1))
    ax.text(x + w / 2, 73.5, title, ha="center", fontsize=10.5, fontweight="bold", color="#333333")


lane(1, 27, "1  SOURCES")
lane(31, 30, "2  WAREHOUSE")
lane(64, 39, "3  TRANSFORM + MODEL")
lane(106, 43, "4  SERVE")

box(3, 54, 23, 15, "GA4 web events", "public sample (BigQuery)\nnested event_params,\ntraffic_source, ecommerce", "#fff4e5", "#ff9f1c")
box(3, 36, 23, 15, "Segment (web + app)", "identify() / track()\nanonymous_id <-> user_id\n+ ga_client_id trait", "#e9f7ef", "#2ca02c")
box(3, 18, 23, 15, "CRM (synthetic)", "customers (+duplicates)\norders, external_ref\n= GA4 transaction_id", "#f3e8fd", "#9467bd")
box(3, 5, 23, 11, "Ad platforms (synthetic)", "daily spend, clicks,\nplatform-reported conv.", "#fdecea", "#d62728")

box(33, 54, 26, 15, "raw / c360_raw", "ga4 events_* (public)\nsegment_*  crm_*  ads_spend_daily", "#eef2f7", "#5b6b7b")
box(33, 36, 26, 15, "c360_staging", "stg_ga4__events  stg_segment__*\nstg_crm__*  stg_ads__spend\n(flatten, dedupe, normalise)", "#eef2f7", "#5b6b7b")
box(33, 18, 26, 15, "c360_ml (python output)", "identity_nodes\nclv_forecast\nbudget_recommendations", "#fff9db", "#b8860b")
box(33, 5, 26, 11, "c360_marts", "fct_sessions  fct_orders\ncustomer_profile  mart_*", "#e6f4ea", "#2e7d32")

box(66, 54, 35, 15, "dbt  staging + intermediate", "sessions (GA4 + app sessionisation)\nidentity edges  conversion paths\nchannel taxonomy macros (BQ/DuckDB)", "#e8f0fe", "#1f77b4")
box(66, 36, 35, 15, "Python  identity graph", "persons = CRM dedupe + device stitching\nshared-device guard\n(person edges / device edges / device->person)", "#fff9db", "#b8860b")
box(66, 18, 35, 15, "Python  CLV + budget optimiser", "BG/NBD x Gamma-Gamma (+ back-test)\nresponse curves, marginal ROAS\nbudget re-allocation", "#fff9db", "#b8860b")
box(66, 5, 35, 11, "dbt  marts + 80 tests", "orders, customer profile, RFM, 4 attribution\nmodels, ROAS / CPA / CAC / LTV:CAC", "#e8f0fe", "#1f77b4")

box(108, 54, 39, 15, "Tableau dashboards", "Executive overview  |  Attribution compare\nCampaign ROI  |  Customer 360  |  Budget", "#e7f1ff", "#1f77b4")
box(108, 36, 39, 15, "Streamlit demo app", "same marts, runs on DuckDB or BigQuery", "#e7f1ff", "#1f77b4")
box(108, 18, 39, 15, "Evaluation + report", "identity P/R, attribution vs ground truth,\nSQL-vs-Python parity, CLV back-test\nreports/findings.md", "#e6f4ea", "#2e7d32")
box(108, 5, 39, 11, "Recommendations", "where to move budget, what to test", "#fdecea", "#d62728")

for y in (61, 43, 25, 10):
    arrow(26, y, 33, y)
arrow(46, 54, 46, 51)
arrow(46, 36, 46, 33, "")
arrow(59, 61, 66, 61)
arrow(59, 43, 66, 43)
arrow(59, 25, 66, 25)
arrow(83, 54, 83, 51)
arrow(83, 36, 83, 33, "ml tables")
arrow(83, 18, 83, 16)
arrow(66, 43, 59, 25, "", "#b8860b", -0.2)
arrow(101, 10, 108, 10)
arrow(101, 43, 108, 43)
arrow(101, 61, 108, 61)
arrow(101, 25, 108, 25)
ax.text(75, 0.4, "Order of execution:  dbt staging -> python identity -> python CLV -> dbt marts + tests -> python budget -> evaluate / report / export",
        ha="center", fontsize=8.2, style="italic", color="#444444")
fig.savefig(OUT / "architecture.svg", bbox_inches="tight")
fig.savefig(OUT / "architecture.png", dpi=140, bbox_inches="tight")
print("wrote", OUT / "architecture.svg")
