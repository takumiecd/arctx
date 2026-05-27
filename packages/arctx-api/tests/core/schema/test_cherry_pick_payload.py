"""Tests for CherryPickPayload round-trip and deserialization."""

from __future__ import annotations

import pytest

from arctx.core.schema.payloads import payload_from_dict
from arctx.ext.git.payloads import CherryPickPayload


class TestCherryPickPayload:
    def test_fields(self):
        p = CherryPickPayload(
            payload_id="pl_1",
            target_id="t_1",
            source_transition="t_src",
            source_commit="abc123",
        )
        assert p.payload_id == "pl_1"
        assert p.target_id == "t_1"
        assert p.source_transition == "t_src"
        assert p.source_commit == "abc123"
        assert p.target_kind == "transition"
        assert p.payload_type == "cherry_pick"

    def test_source_transition_can_be_none(self):
        p = CherryPickPayload(
            payload_id="pl_1",
            target_id="t_1",
            source_transition=None,
            source_commit="abc123",
        )
        assert p.source_transition is None

    def test_to_dict_round_trip(self):
        p = CherryPickPayload(
            payload_id="pl_abc",
            target_id="t_xyz",
            source_transition="t_from",
            source_commit="feedcafe",
            metadata={"tag": "x"},
        )
        d = p.to_dict()
        assert d["payload_type"] == "cherry_pick"
        assert d["target_kind"] == "transition"
        assert d["source_transition"] == "t_from"
        assert d["source_commit"] == "feedcafe"
        assert d["metadata"] == {"tag": "x"}

        restored = payload_from_dict(d)
        assert isinstance(restored, CherryPickPayload)
        assert restored.payload_id == p.payload_id
        assert restored.target_id == p.target_id
        assert restored.source_transition == p.source_transition
        assert restored.source_commit == p.source_commit
        assert restored.metadata == p.metadata

    def test_to_dict_round_trip_none_source_transition(self):
        p = CherryPickPayload(
            payload_id="pl_cross",
            target_id="t_cross",
            source_transition=None,
            source_commit="0000cafe",
        )
        d = p.to_dict()
        assert d["source_transition"] is None

        restored = payload_from_dict(d)
        assert isinstance(restored, CherryPickPayload)
        assert restored.source_transition is None
        assert restored.source_commit == "0000cafe"

    def test_payload_from_dict_dispatches_cherry_pick_type(self):
        d = {
            "payload_id": "pl_cp",
            "payload_type": "cherry_pick",
            "target_kind": "transition",
            "target_id": "t_cp",
            "source_transition": "t_s",
            "source_commit": "12345678",
            "metadata": {},
        }
        p = payload_from_dict(d)
        assert isinstance(p, CherryPickPayload)
        assert p.source_commit == "12345678"

    def test_frozen(self):
        p = CherryPickPayload(
            payload_id="pl_1",
            target_id="t_1",
            source_transition="t_x",
            source_commit="sha1",
        )
        with pytest.raises(Exception):
            p.source_commit = "other"  # type: ignore[misc]

    def test_metadata_defaults_empty(self):
        p = CherryPickPayload(
            payload_id="pl_1",
            target_id="t_1",
            source_transition=None,
            source_commit="sha1",
        )
        assert p.metadata == {}
