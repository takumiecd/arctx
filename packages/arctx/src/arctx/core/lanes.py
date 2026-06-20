"""Core lane semantics over a RunGraph.

Lanes are the durable work/thought units of a run. The graph records stay
minimal: node/step/payload topology is stored in ``RunGraph``, while lane
membership is derived from append-only ``WorkEvent.created_records``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from arctx.core.run_graph import RunGraph
from arctx.core.schema.work import WorkEvent, WorkSession


@dataclass(frozen=True)
class LaneRecordProvenance:
    record_id: str
    lane_id: str
    lane_name: str | None
    user_id: str
    event_id: str
    event_type: str
    created_at: str | None

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "lane_id": self.lane_id,
            "lane_name": self.lane_name,
            "user_id": self.user_id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class LaneGroup:
    lane_id: str
    label: str
    node_ids: tuple[str, ...] = ()
    step_ids: tuple[str, ...] = ()

    @property
    def group_id(self) -> str:
        return f"lane:{self.lane_id}"

    def to_dict(self) -> dict:
        return {
            "group_id": self.group_id,
            "kind": "lane",
            "lane_id": self.lane_id,
            "label": self.label,
            "node_ids": list(self.node_ids),
            "step_ids": list(self.step_ids),
            "color_key": self.lane_id,
        }


@dataclass(frozen=True)
class LaneMembership:
    provenance: dict[str, LaneRecordProvenance] = field(default_factory=dict)
    node_to_lane: dict[str, str] = field(default_factory=dict)
    step_to_lane: dict[str, str] = field(default_factory=dict)
    payload_to_lane: dict[str, str] = field(default_factory=dict)
    groups: tuple[LaneGroup, ...] = ()
    event_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class LaneBoundary:
    from_lane_id: str
    to_lane_id: str
    step_id: str
    input_node_id: str
    output_node_id: str

    def to_dict(self) -> dict:
        return {
            "from_lane_id": self.from_lane_id,
            "to_lane_id": self.to_lane_id,
            "step_id": self.step_id,
            "input_node_id": self.input_node_id,
            "output_node_id": self.output_node_id,
        }


@dataclass(frozen=True)
class LaneValidationIssue:
    code: str
    severity: str
    message: str
    record_id: str | None = None
    lane_id: str | None = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "record_id": self.record_id,
            "lane_id": self.lane_id,
        }


def lane_label(session: WorkSession | None, lane_id: str) -> str:
    """Return the human label for a lane id."""
    if session is None:
        return lane_id
    return str(session.name or session.work_session_id)


def lane_root_node_id(session: WorkSession) -> str | None:
    """Return the configured lane root/anchor node, if any.

    ``root_node_id`` is the preferred key. ``anchor_node_id`` is accepted as a
    synonym while the vocabulary settles.
    """
    root = session.metadata.get("root_node_id") or session.metadata.get("anchor_node_id")
    return str(root) if root else None


def lane_membership(
    graph: RunGraph,
    *,
    node_ids: set[str] | None = None,
    step_ids: set[str] | None = None,
    payload_ids: set[str] | None = None,
) -> LaneMembership:
    """Derive lane membership for graph records.

    The first WorkEvent that creates a record determines that record's lane.
    Later payload attachments remain their own provenance; they do not move the
    target node or step between lanes.
    """
    node_ids = set(graph.nodes) if node_ids is None else set(node_ids)
    step_ids = set(graph.steps) if step_ids is None else set(step_ids)
    payload_ids = set(graph.payloads) if payload_ids is None else set(payload_ids)
    included_ids = node_ids | step_ids | payload_ids

    provenance: dict[str, LaneRecordProvenance] = {}
    node_to_lane: dict[str, str] = {}
    step_to_lane: dict[str, str] = {}
    payload_to_lane: dict[str, str] = {}
    lane_nodes: dict[str, set[str]] = {}
    lane_steps: dict[str, set[str]] = {}
    event_ids: list[str] = []

    for event in graph.work_events:
        created = [record_id for record_id in event.created_records if record_id in included_ids]
        if not created:
            continue
        event_ids.append(event.event_id)
        session = graph.work_sessions.get(event.work_session_id)
        lane_name = session.name if session is not None else None
        for record_id in created:
            provenance.setdefault(
                record_id,
                LaneRecordProvenance(
                    record_id=record_id,
                    lane_id=event.work_session_id,
                    lane_name=lane_name,
                    user_id=event.user_id,
                    event_id=event.event_id,
                    event_type=event.event_type,
                    created_at=event.created_at,
                ),
            )
            if record_id in node_ids:
                node_to_lane.setdefault(record_id, event.work_session_id)
                lane_nodes.setdefault(event.work_session_id, set()).add(record_id)
            elif record_id in step_ids:
                step_to_lane.setdefault(record_id, event.work_session_id)
                lane_steps.setdefault(event.work_session_id, set()).add(record_id)
            elif record_id in payload_ids:
                payload_to_lane.setdefault(record_id, event.work_session_id)

    groups = tuple(
        LaneGroup(
            lane_id=lane_id,
            label=lane_label(graph.work_sessions.get(lane_id), lane_id),
            node_ids=tuple(sorted(lane_nodes.get(lane_id, set()))),
            step_ids=tuple(sorted(lane_steps.get(lane_id, set()))),
        )
        for lane_id in sorted(set(lane_nodes) | set(lane_steps))
    )

    return LaneMembership(
        provenance=provenance,
        node_to_lane=node_to_lane,
        step_to_lane=step_to_lane,
        payload_to_lane=payload_to_lane,
        groups=groups,
        event_ids=tuple(event_ids),
    )


def lane_boundaries(
    graph: RunGraph,
    membership: LaneMembership | None = None,
) -> tuple[LaneBoundary, ...]:
    """Return cross-lane step inputs as derived lane boundaries."""
    membership = membership or lane_membership(graph)
    out: list[LaneBoundary] = []
    for step_id, step in graph.steps.items():
        to_lane = membership.step_to_lane.get(step_id)
        if to_lane is None:
            continue
        for input_node_id in step.input_node_ids:
            from_lane = membership.node_to_lane.get(input_node_id)
            if from_lane is None or from_lane == to_lane:
                continue
            out.append(
                LaneBoundary(
                    from_lane_id=from_lane,
                    to_lane_id=to_lane,
                    step_id=step_id,
                    input_node_id=input_node_id,
                    output_node_id=step.output_node_id,
                )
            )
    return tuple(out)


def lane_subgraph(graph: RunGraph, lane_id: str) -> dict[str, tuple[str, ...]]:
    """Return node/step ids that belong to one lane."""
    membership = lane_membership(graph)
    return {
        "node_ids": tuple(
            sorted(node_id for node_id, owner in membership.node_to_lane.items() if owner == lane_id)
        ),
        "step_ids": tuple(
            sorted(step_id for step_id, owner in membership.step_to_lane.items() if owner == lane_id)
        ),
    }


def validate_lanes(
    graph: RunGraph,
    *,
    root_node_id: str | None = None,
) -> tuple[LaneValidationIssue, ...]:
    """Validate lane-level invariants derivable from the graph.

    This deliberately reports issues instead of raising. Existing runs may lack
    lane provenance, and GUI/CLI surfaces can decide whether a warning should
    block a workflow.
    """
    membership = lane_membership(graph)
    issues: list[LaneValidationIssue] = []

    for lane_id, session in graph.work_sessions.items():
        lane_root = lane_root_node_id(session)
        if lane_root is not None and lane_root not in graph.nodes:
            issues.append(
                LaneValidationIssue(
                    code="unknown_lane_root",
                    severity="error",
                    message=f"lane {lane_id!r} root node does not exist: {lane_root}",
                    record_id=lane_root,
                    lane_id=lane_id,
                )
            )

    for step_id, step in graph.steps.items():
        step_lane = membership.step_to_lane.get(step_id)
        output_lane = membership.node_to_lane.get(step.output_node_id)
        if step_lane is None:
            issues.append(
                LaneValidationIssue(
                    code="step_without_lane",
                    severity="warning",
                    message=f"step has no lane provenance: {step_id}",
                    record_id=step_id,
                )
            )
            continue
        if output_lane is None:
            issues.append(
                LaneValidationIssue(
                    code="output_node_without_lane",
                    severity="warning",
                    message=f"step output has no lane provenance: {step.output_node_id}",
                    record_id=step.output_node_id,
                    lane_id=step_lane,
                )
            )
        elif output_lane != step_lane:
            issues.append(
                LaneValidationIssue(
                    code="step_output_lane_mismatch",
                    severity="error",
                    message=(
                        f"step {step_id} is in lane {step_lane}, but its output "
                        f"node {step.output_node_id} is in lane {output_lane}"
                    ),
                    record_id=step_id,
                    lane_id=step_lane,
                )
            )

    lane_roots = {
        root
        for session in graph.work_sessions.values()
        if (root := lane_root_node_id(session)) is not None
    }
    run_root = root_node_id or graph.metadata.get("root_node_id")
    for node_id in graph.roots():
        if node_id == run_root or node_id in lane_roots:
            continue
        if node_id not in membership.node_to_lane:
            issues.append(
                LaneValidationIssue(
                    code="orphan_root_node",
                    severity="warning",
                    message=f"producer-less node is not a run root or lane root: {node_id}",
                    record_id=node_id,
                )
            )

    return tuple(issues)


def lane_export_view(
    graph: RunGraph,
    *,
    node_ids: set[str],
    step_ids: set[str],
    payload_ids: set[str],
) -> dict:
    """Return JSON-ready lane data for export/API surfaces."""
    membership = lane_membership(
        graph,
        node_ids=node_ids,
        step_ids=step_ids,
        payload_ids=payload_ids,
    )
    event_ids = set(membership.event_ids)
    sessions = [
        session.to_dict()
        for session in sorted(
            graph.work_sessions.values(),
            key=lambda s: (s.started_at or "", s.work_session_id),
        )
    ]
    events = [
        event.to_dict()
        for event in graph.work_events
        if event.event_id in event_ids
    ]
    return {
        "lanes": sessions,
        "work_sessions": sessions,
        "work_events": events,
        "record_provenance": {
            record_id: provenance.to_dict()
            for record_id, provenance in sorted(membership.provenance.items())
        },
        "groups": [group.to_dict() for group in membership.groups],
        "lane_boundaries": [
            boundary.to_dict()
            for boundary in lane_boundaries(graph, membership)
            if boundary.step_id in step_ids
        ],
    }
