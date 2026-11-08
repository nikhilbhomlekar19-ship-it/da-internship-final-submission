import pandas as pd

from customer360.identity import resolve

T = pd.Timestamp("2020-12-01")


def edges(rows):
    return pd.DataFrame(rows, columns=["node_a", "node_b", "edge_type", "edge_class", "last_seen_at", "evidence_count"]).assign(first_seen_at=T)


def person(df, key):
    return df.set_index("node_key").person_id.get(key)


BASE = [
    ("crm:C1", "crm:C1", "crm_record", "person", T, 1),
    ("crm:C2", "crm:C2", "crm_record", "person", T, 1),
    ("crm:C3", "crm:C3", "crm_record", "person", T, 1),
    ("crm:C1", "email:a@x.com", "crm_email", "person", T, 1),
    ("crm:C2", "email:a@x.com", "crm_email", "person", T, 1),  # duplicate CRM record: same e-mail
    ("crm:C3", "phone:5551234567", "crm_phone", "person", T, 1),
]


def test_crm_duplicates_are_merged():
    n = resolve(edges(BASE))
    assert person(n, "crm:C1") == person(n, "crm:C2")
    assert person(n, "crm:C1") != person(n, "crm:C3")


def test_devices_are_stitched_through_identify_and_bridge():
    rows = BASE + [
        ("sa:A", "crm:C1", "segment_identify_user", "device_person", T, 1),
        ("sa:A", "ga:G", "segment_ga_bridge", "device_device", T, 1),  # same browser: Segment id <-> GA client id
    ]
    n = resolve(edges(rows))
    assert person(n, "ga:G") == person(n, "crm:C1") == person(n, "sa:A")
    assert not n.set_index("node_key").loc["ga:G", "is_shared_device"]


def test_shared_device_does_not_merge_two_people_but_naive_does():
    rows = BASE + [
        ("ga:S", "crm:C1", "order_match_web", "device_person", T, 3),
        ("ga:S", "crm:C3", "order_match_web", "device_person", T, 1),
    ]
    g, naive = resolve(edges(rows)), resolve(edges(rows), guard=False)
    assert person(g, "crm:C1") != person(g, "crm:C3")  # two people stay two people
    assert g.set_index("node_key").loc["ga:S", "is_shared_device"]
    assert person(g, "ga:S") == person(g, "crm:C1")  # best-evidenced person owns the device
    assert person(naive, "crm:C1") == person(naive, "crm:C3")  # the failure the guard prevents


def test_unlinked_devices_are_not_in_output():
    n = resolve(edges(BASE + [("sa:Z", "ga:Y", "segment_ga_bridge", "device_device", T, 1)]))
    assert "ga:Y" not in set(n.node_key)


def test_node_keys_are_unique_and_person_ids_stable():
    n1, n2 = resolve(edges(BASE)), resolve(edges(BASE[::-1]))
    assert n1.node_key.is_unique
    assert dict(zip(n1.node_key, n1.person_id)) == dict(zip(n2.node_key, n2.person_id))
