"""Tests for MergePayload and JoinPayload schema (round-trip + payload_from_dict)."""

from __future__ import annotations

import pytest

from stag_api.core.schema.payloads import (
    JoinPayload,
    payload_from_dict,
)
from stag_api.ext.git.payloads import MergePayload


class TestMergePayload:
    def test_basic_construction(self):
        p = MergePayload(
            payload_id="pl_1",
            target_id="t_1",
            merged_from="feature/x",
            merged_into="main",
        )
        assert p.payload_type == "merge"
        assert p.target_kind == "transition"
        assert p.merged_from == "feature/x"
        assert p.merged_into == "main"
        assert p.metadata == {}

    def test_to_dict_round_trip(self):
        p = MergePayload(
            payload_id="pl_m1",
            target_id="t_merge",
            merged_from="feature/branch",
            merged_into="main",
            metadata={"note": "fast-forward"},
        )
        d = p.to_dict()
        assert d["payload_type"] == "merge"
        assert d["target_kind"] == "transition"
        assert d["merged_from"] == "feature/branch"
        assert d["merged_into"] == "main"
        assert d["metadata"] == {"note": "fast-forward"}

    def test_payload_from_dict(self):
        data = {
            "payload_id": "pl_m2",
            "payload_type": "merge",
            "target_kind": "transition",
            "target_id": "t_m",
            "merged_from": "feat",
            "merged_into": "main",
            "metadata": {},
        }
        p = payload_from_dict(data)
        assert isinstance(p, MergePayload)
        assert p.payload_id == "pl_m2"
        assert p.merged_from == "feat"
        assert p.merged_into == "main"

    def test_payload_from_dict_missing_fields_graceful(self):
        """Missing optional fields should fall back to empty strings."""
        data = {
            "payload_id": "pl_m3",
            "payload_type": "merge",
            "target_kind": "transition",
            "target_id": "t_m3",
        }
        p = payload_from_dict(data)
        assert isinstance(p, MergePayload)
        assert p.merged_from == ""
        assert p.merged_into == ""

    def test_immutable(self):
        p = MergePayload(
            payload_id="pl_x",
            target_id="t_x",
            merged_from="a",
            merged_into="b",
        )
        with pytest.raises(Exception):
            p.merged_from = "changed"  # type: ignore[misc]


class TestJoinPayload:
    def test_basic_construction(self):
        p = JoinPayload(
            payload_id="pl_j1",
            target_id="t_j1",
            joined_views=("main", "experiment"),
        )
        assert p.payload_type == "join"
        assert p.target_kind == "transition"
        assert p.joined_views == ("main", "experiment")
        assert p.metadata == {}

    def test_to_dict_round_trip(self):
        p = JoinPayload(
            payload_id="pl_j2",
            target_id="t_j2",
            joined_views=("viewA", "viewB"),
            metadata={"source": "manual"},
        )
        d = p.to_dict()
        assert d["payload_type"] == "join"
        assert d["target_kind"] == "transition"
        assert d["joined_views"] == ["viewA", "viewB"]
        assert d["metadata"] == {"source": "manual"}

    def test_payload_from_dict(self):
        data = {
            "payload_id": "pl_j3",
            "payload_type": "join",
            "target_kind": "transition",
            "target_id": "t_j3",
            "joined_views": ["alpha", "beta"],
            "metadata": {},
        }
        p = payload_from_dict(data)
        assert isinstance(p, JoinPayload)
        assert p.payload_id == "pl_j3"
        assert p.joined_views == ("alpha", "beta")

    def test_payload_from_dict_empty_views(self):
        data = {
            "payload_id": "pl_j4",
            "payload_type": "join",
            "target_kind": "transition",
            "target_id": "t_j4",
        }
        p = payload_from_dict(data)
        assert isinstance(p, JoinPayload)
        assert p.joined_views == ()

    def test_immutable(self):
        p = JoinPayload(
            payload_id="pl_jx",
            target_id="t_jx",
            joined_views=("a", "b"),
        )
        with pytest.raises(Exception):
            p.joined_views = ("c",)  # type: ignore[misc]
