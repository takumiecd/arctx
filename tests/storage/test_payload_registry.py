"""Tests for payload registry and deserialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import pytest

from stag.core.schema.payloads import (
    NodePayload,
    PayloadBase,
    TransitionPayload,
    payload_from_dict,
    register_payload_class,
)


def test_register_and_dispatch():
    @dataclass(frozen=True)
    class MetricPayload(PayloadBase):
        payload_id: str
        target_id: str
        accuracy: float = 0.0
        target_kind: Literal["transition"] = field(default="transition", init=False)
        payload_type: str = field(default="metric_payload_reg_test", init=False)

        def to_dict(self):
            return {
                "payload_id": self.payload_id,
                "target_id": self.target_id,
                "target_kind": self.target_kind,
                "payload_type": self.payload_type,
                "accuracy": self.accuracy,
            }

    register_payload_class(MetricPayload)
    data = {
        "payload_type": "metric_payload_reg_test",
        "payload_id": "pl_x",
        "target_id": "t_1",
        "target_kind": "transition",
        "accuracy": 0.95,
    }
    p = payload_from_dict(data)
    assert isinstance(p, MetricPayload)
    assert p.accuracy == 0.95


def test_unknown_type_fallback_node():
    data = {
        "payload_type": "totally_unknown_node_type",
        "payload_id": "pl_u",
        "target_id": "n_x",
        "target_kind": "node",
        "some_field": "some_value",
    }
    p = payload_from_dict(data)
    assert isinstance(p, NodePayload)
    assert p.type == "totally_unknown_node_type"


def test_unknown_type_fallback_transition():
    data = {
        "payload_type": "totally_unknown_transition_type",
        "payload_id": "pl_u",
        "target_id": "t_x",
        "target_kind": "transition",
    }
    p = payload_from_dict(data)
    assert isinstance(p, TransitionPayload)
    assert p.type == "totally_unknown_transition_type"


def test_register_requires_payload_type():
    class BadPayload(PayloadBase):
        def to_dict(self):
            return {}

    with pytest.raises(ValueError, match="payload_type"):
        register_payload_class(BadPayload)  # type: ignore[arg-type]
