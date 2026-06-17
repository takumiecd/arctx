"""Tests for the diagram extension payload schema."""

from __future__ import annotations

from arctx.core.schema.payloads import payload_from_dict
from arctx.ext.diagram import DiagramExtension
from arctx.ext.diagram.payloads import DiagramPayload


def test_diagram_payload_allows_cyclic_embedded_edges():
    payload = DiagramPayload(
        payload_id="pl_d",
        target_id="n_x",
        target_kind="node",
        title="retry loop",
        format="nodes_edges",
        nodes=({"id": "fetch"}, {"id": "retry"}),
        edges=(
            {"from": "fetch", "to": "retry"},
            {"from": "retry", "to": "fetch"},
        ),
    )

    assert payload.target_kind == "node"
    assert payload.payload_type == "diagram"
    assert payload.edges[1]["to"] == "fetch"
    assert payload.to_dict()["edges"][1]["from"] == "retry"


def test_payload_from_dict_diagram_after_extension_schema_registration():
    DiagramExtension().register_schema()
    data = {
        "payload_type": "diagram",
        "payload_id": "pl_d",
        "target_id": "t_x",
        "target_kind": "step",
        "title": "state machine",
        "format": "mermaid",
        "source": "stateDiagram-v2\n  A --> B\n  B --> A",
        "metadata": {},
    }

    payload = payload_from_dict(data)

    assert isinstance(payload, DiagramPayload)
    assert payload.target_kind == "step"
    assert payload.title == "state machine"
    assert payload.source and "B --> A" in payload.source
