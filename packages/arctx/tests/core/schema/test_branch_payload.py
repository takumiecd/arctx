"""Tests for BranchPayload round-trip and deserialization."""

from __future__ import annotations

import pytest

from arctx.core.schema.payloads import payload_from_dict
from arctx.ext.git.payloads import BranchPayload


class TestBranchPayload:
    def test_fields(self):
        p = BranchPayload(
            payload_id="pl_1",
            target_id="t_1",
            branch="main",
        )
        assert p.payload_id == "pl_1"
        assert p.target_id == "t_1"
        assert p.branch == "main"
        assert p.target_kind == "step"
        assert p.payload_type == "branch"

    def test_to_dict_round_trip(self):
        p = BranchPayload(
            payload_id="pl_abc",
            target_id="t_xyz",
            branch="feature/foo",
            metadata={"note": "test"},
        )
        d = p.to_dict()
        assert d["payload_type"] == "branch"
        assert d["target_kind"] == "step"
        assert d["branch"] == "feature/foo"
        assert d["metadata"] == {"note": "test"}

        restored = payload_from_dict(d)
        assert isinstance(restored, BranchPayload)
        assert restored.payload_id == p.payload_id
        assert restored.target_id == p.target_id
        assert restored.branch == p.branch
        assert restored.metadata == p.metadata

    def test_payload_from_dict_dispatches_branch_type(self):
        d = {
            "payload_id": "pl_br",
            "payload_type": "branch",
            "target_kind": "step",
            "target_id": "t_br",
            "branch": "develop",
            "metadata": {},
        }
        p = payload_from_dict(d)
        assert isinstance(p, BranchPayload)
        assert p.branch == "develop"

    def test_frozen(self):
        p = BranchPayload(payload_id="pl_1", target_id="t_1", branch="main")
        with pytest.raises(Exception):
            p.branch = "other"  # type: ignore[misc]

    def test_metadata_defaults_empty(self):
        p = BranchPayload(payload_id="pl_1", target_id="t_1", branch="main")
        assert p.metadata == {}

    def test_unknown_payload_type_fallback_is_not_branch(self):
        """Unregistered types should fall back to generic StepPayload."""
        d = {
            "payload_id": "pl_x",
            "payload_type": "some_unknown_type",
            "target_kind": "step",
            "target_id": "t_x",
        }
        p = payload_from_dict(d)
        assert not isinstance(p, BranchPayload)
