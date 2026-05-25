from stag.core.sync.records import body_key


def test_sync_body_key_supports_new_record_kinds():
    assert body_key("node", {"node_id": "n_1"}) == ("node", "n_1")
    assert body_key("transition", {"transition_id": "t_1"}) == ("transition", "t_1")
    assert body_key("edge", {"edge_id": "e_1"}) == ("edge", "e_1")
