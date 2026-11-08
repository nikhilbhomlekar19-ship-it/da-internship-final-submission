"""Identity resolution: evidence edges (built in dbt) -> persons (graph algorithm in Python).

Why two classes of edges?  A naive "connected components over everything" merges two people who share one device
(family laptop, office PC) into ONE customer and silently corrupts every downstream number.  So:

  1. person edges   (CRM record <-> email / phone)           -> merged: this also de-duplicates the CRM
  2. device edges   (Segment anonymous_id <-> GA client id)   -> merged: same physical browser
  3. device->person (identify(), order match, GA4 user_id)    -> a device joins a person ONLY if it points to exactly one
                                                                 person; devices that point to several are flagged
                                                                 `is_shared_device` and given to the best-evidenced person.

Output (ml.identity_nodes): one row per node_key with its person_id, how it was linked and a confidence label.
`identity_nodes_naive` is the naive baseline, kept only so the evaluation can quantify the false merges the guard avoids.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict

import pandas as pd

from . import config as cfg
from .warehouse import Warehouse

EVIDENCE_WEIGHT = {"order_match_web": 3, "order_match_app": 3, "segment_identify_user": 2, "segment_identify_email": 1, "ga4_user_id": 1}


class UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[max(ra, rb)] = min(ra, rb)  # deterministic root


def node_type(key: str) -> str:
    return key.split(":", 1)[0]


def _person_id(members) -> str:
    crm = sorted(m for m in members if m.startswith("crm:"))
    anchor = crm[0] if crm else sorted(members)[0]
    return "P" + hashlib.md5(anchor.encode()).hexdigest()[:12]


def resolve(edges: pd.DataFrame, guard: bool = True, shared_policy: str = "dominant") -> pd.DataFrame:
    """Return the identity_nodes table. `guard=False` is the naive connected-components baseline."""
    persons_uf, devices_uf = UnionFind(), UnionFind()
    nodes = set(edges["node_a"]) | set(edges["node_b"])
    for n in nodes:
        persons_uf.find(n)
        devices_uf.find(n)

    rows = list(zip(edges["node_a"], edges["node_b"], edges["edge_type"], edges["edge_class"],
                    edges["last_seen_at"], edges["evidence_count"]))

    if not guard:  # naive baseline: everything that touches, merges
        for a, b, *_ in rows:
            persons_uf.union(a, b)
        clusters: dict[str, set] = defaultdict(set)
        for n in nodes:
            clusters[persons_uf.find(n)].add(n)
        out = []
        for members in clusters.values():
            pid = _person_id(members)
            for m in members:
                out.append((m, node_type(m), m.split(":", 1)[1], pid, "naive_union", "n/a", False, len(members)))
        return pd.DataFrame(out, columns=["node_key", "node_type", "node_value", "person_id", "link_method", "confidence", "is_shared_device", "group_size"])

    for a, b, _, cls, *_ in rows:
        if cls == "person":
            persons_uf.union(a, b)
        elif cls == "device_device":
            devices_uf.union(a, b)

    person_members: dict[str, set] = defaultdict(set)
    for n in nodes:
        if node_type(n) in ("crm", "email", "phone"):
            person_members[persons_uf.find(n)].add(n)
    person_id = {root: _person_id(m) for root, m in person_members.items()}

    # evidence that a device group belongs to a person cluster
    ev: dict[tuple, dict] = defaultdict(lambda: {"w": 0, "last": None, "methods": set()})
    for a, b, et, cls, last, cnt in rows:
        if cls != "device_person":
            continue
        slot = ev[(devices_uf.find(a), persons_uf.find(b))]
        slot["w"] += EVIDENCE_WEIGHT.get(et, 1) * int(cnt)
        slot["last"] = last if slot["last"] is None or last > slot["last"] else slot["last"]
        slot["methods"].add(et)

    by_device: dict[str, list] = defaultdict(list)
    for (dev, per), slot in ev.items():
        by_device[dev].append((per, slot))

    device_groups: dict[str, set] = defaultdict(set)
    for n in nodes:
        if node_type(n) in ("ga", "sa"):
            device_groups[devices_uf.find(n)].add(n)

    out = []
    for root, members in person_members.items():
        for m in members:
            out.append((m, node_type(m), m.split(":", 1)[1], person_id[root], "crm_strong_key", "high", False, len(members)))
    for dev, cands in by_device.items():
        cands.sort(key=lambda c: (-c[1]["w"], -(c[1]["last"].value if c[1]["last"] is not None else 0), c[0]))
        shared = len(cands) > 1
        if shared and shared_policy == "unlink":
            continue
        per, slot = cands[0]
        methods = sorted(set().union(*[c[1]["methods"] for c in cands]) if not shared else slot["methods"])
        strong = any(m.startswith("order_match") for m in methods) or len(methods) >= 2
        conf = "low" if shared else ("high" if strong else "medium")
        for m in device_groups.get(dev, {dev}):
            out.append((m, node_type(m), m.split(":", 1)[1], person_id[per], "+".join(methods) + ("+shared_device_dominant" if shared else ""),
                        conf, shared, len(person_members[per])))
    return pd.DataFrame(out, columns=["node_key", "node_type", "node_value", "person_id", "link_method", "confidence", "is_shared_device", "group_size"])


def run() -> dict:
    with Warehouse() as wh:
        edges = wh.read_table(cfg.dbt_schema("intermediate"), "int_identity_edges")
        guarded = resolve(edges, guard=True)
        naive = resolve(edges, guard=False)
        wh.write_df(guarded, cfg.ML_SCHEMA, "identity_nodes")
        wh.write_df(naive, cfg.ML_SCHEMA, "identity_nodes_naive")
    crm = guarded[guarded.node_type == "crm"]
    dev = guarded[guarded.node_type.isin(["ga", "sa"])]
    stats = {
        "edges": int(len(edges)),
        "nodes_total": int(len(guarded)),
        "persons": int(guarded.person_id.nunique()),
        "crm_records": int(len(crm)),
        "crm_records_merged_by_dedupe": int(len(crm) - crm.person_id.nunique()),
        "devices_linked": int(len(dev)),
        "shared_devices_flagged": int(dev[dev.is_shared_device].node_key.nunique()),
        "persons_naive": int(naive.person_id.nunique()),
        "naive_person_clusters_with_multiple_people_possible": int(naive.person_id.nunique() - guarded.person_id.nunique()),
    }
    return stats
