"""Tests for RevertPayload round-trip and deserialization."""

from __future__ import annotations

import pytest

from stag_api.core.schema.payloads import payload_from_dict
from stag_api.ext.git.payloads import RevertPayload


class TestRevertPayload:
    def test_fields(self):
        p = RevertPayload(
            payload_id="pl_1",
            target_id="t_1",
            reverted_transition="t_orig",
            reverted_commit="abc123",
        )
        assert p.payload_id == "pl_1"
        assert p.target_id == "t_1"
        assert p.reverted_transition == "t_orig"
        assert p.reverted_commit == "abc123"
        assert p.target_kind == "transition"
        assert p.payload_type == "revert"

    def test_to_dict_round_trip(self):
        p = RevertPayload(
            payload_id="pl_abc",
            target_id="t_xyz",
            reverted_transition="t_old",
            reverted_commit="deadbeef",
            metadata={"note": "test"},
        )
        d = p.to_dict()
        assert d["payload_type"] == "revert"
        assert d["target_kind"] == "transition"
        assert d["reverted_transition"] == "t_old"
        assert d["reverted_commit"] == "deadbeef"
        assert d["metadata"] == {"note": "test"}

        restored = payload_from_dict(d)
        assert isinstance(restored, RevertPayload)
        assert restored.payload_id == p.payload_id
        assert restored.target_id == p.target_id
        assert restored.reverted_transition == p.reverted_transition
        assert restored.reverted_commit == p.reverted_commit
        assert restored.metadata == p.metadata

    def test_payload_from_dict_dispatches_revert_type(self):
        d = {
            "payload_id": "pl_r",
            "payload_type": "revert",
            "target_kind": "transition",
            "target_id": "t_r",
            "reverted_transition": "t_source",
            "reverted_commit": "cafe0000",
            "metadata": {},
        }
        p = payload_from_dict(d)
        assert isinstance(p, RevertPayload)
        assert p.reverted_commit == "cafe0000"

    def test_frozen(self):
        p = RevertPayload(
            payload_id="pl_1",
            target_id="t_1",
            reverted_transition="t_x",
            reverted_commit="sha1",
        )
        with pytest.raises(Exception):
            p.reverted_commit = "other"  # type: ignore[misc]

    def test_metadata_defaults_empty(self):
        p = RevertPayload(
            payload_id="pl_1",
            target_id="t_1",
            reverted_transition="t_x",
            reverted_commit="sha1",
        )
        assert p.metadata == {}
