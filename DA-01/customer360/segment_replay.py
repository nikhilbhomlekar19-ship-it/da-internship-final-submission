"""Replay the synthetic Segment events into a REAL Segment source (so interns can see Segment -> BigQuery end to end).

    python -m customer360.segment_replay --limit 50 --dry-run              # print the calls, send nothing
    SEGMENT_WRITE_KEY=xxxx python -m customer360.segment_replay --limit 500 # send to your Segment source

Then, in the Segment UI, add BigQuery as a Warehouse destination of that source: Segment creates a dataset with the
`identifies`, `tracks`, `pages` ... tables that stg_segment__* read (point the dbt vars segment_schema / *_table at it).
"""
from __future__ import annotations

import argparse
import json
import os

import pandas as pd

from . import config as cfg
from .warehouse import Warehouse


def _ts(v):
    return None if pd.isna(v) else pd.Timestamp(v).to_pydatetime()


def build_calls(identifies: pd.DataFrame, tracks: pd.DataFrame, orders: pd.DataFrame) -> list[dict]:
    """Rows of the warehouse tables -> Segment Spec calls (identify / track), oldest first."""
    calls = []
    for r in identifies.itertuples():
        traits = {"email": r.email}
        if isinstance(r.ga_client_id, str) and r.ga_client_id:
            traits["ga_client_id"] = r.ga_client_id  # <- the deterministic bridge to GA4 (see tracking_plan.yaml)
        calls.append({"type": "identify", "user_id": r.user_id, "anonymous_id": r.anonymous_id, "traits": traits,
                      "timestamp": _ts(r.timestamp), "context": {"library": {"name": r.context_library_name}}})
    order_props = {r.order_id: r for r in orders.itertuples()}
    for r in tracks.itertuples():
        ctx = {"os": {"name": r.context_os_name}, "device": {"type": r.context_device_type}}
        if isinstance(r.context_campaign_source, str):
            ctx["campaign"] = {"source": r.context_campaign_source, "medium": r.context_campaign_medium, "name": r.context_campaign_name}
        props = {}
        if r.event == "Order Completed":  # attach the order properties from the order_completed table
            o = next((o for o in order_props.values() if o.anonymous_id == r.anonymous_id and o.timestamp == r.timestamp), None)
            if o is not None:
                props = {"order_id": o.order_id, "total": float(o.total), "revenue": float(o.revenue), "currency": o.currency}
        calls.append({"type": "track", "user_id": r.user_id if isinstance(r.user_id, str) else None, "anonymous_id": r.anonymous_id,
                      "event": r.event, "properties": props, "timestamp": _ts(r.timestamp), "context": ctx})
    return sorted(calls, key=lambda c: c["timestamp"])


def send(calls: list[dict], write_key: str) -> int:
    import segment.analytics as analytics

    analytics.write_key = write_key
    for c in calls:
        kind = c.pop("type")
        if kind == "identify":
            analytics.identify(**c)
        else:
            analytics.track(**c)
    analytics.flush()
    return len(calls)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=50, help="max number of calls")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    with Warehouse(read_only=cfg.TARGET == "duckdb") as wh:
        ident = wh.read_table(cfg.RAW_SCHEMA, "segment_identifies").head(args.limit)
        trk = wh.read_table(cfg.RAW_SCHEMA, "segment_tracks").head(args.limit)
        ords = wh.read_table(cfg.RAW_SCHEMA, "segment_order_completed")
    calls = build_calls(ident, trk, ords)[: args.limit]
    if args.dry_run or not os.environ.get("SEGMENT_WRITE_KEY"):
        print(json.dumps(calls[:5], indent=2, default=str))
        print(f"... {len(calls)} calls prepared (dry run - set SEGMENT_WRITE_KEY and drop --dry-run to send)")
        return
    print(f"sent {send(calls, os.environ['SEGMENT_WRITE_KEY'])} calls")


if __name__ == "__main__":
    main()
