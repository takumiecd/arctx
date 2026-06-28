"""Core lane semantics over a RunGraph.

Lanes are the durable work/thought units of a run. The graph records stay
minimal: node/step/payload topology is stored in ``RunGraph``, while lane
membership is derived from append-only ``WorkEvent.created_records``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from arctx.core.cuts import inactive_node_ids, inactive_step_ids
from arctx.core.run_graph import RunGraph
from arctx.core.schema.payloads import SummaryPayload
from arctx.core.schema.work import WorkEvent, Lane


# Lane status is a PROJECTION of the append-only work-event log, not a mutable
# field on the lane record. A lane opens at create (status "open") and toggles via
# ``lane_closed`` / ``lane_opened`` events; the lane row on disk stays as first
# written, and the current status is folded from the events on load.
LANE_STATUS_EVENTS = ("lane_closed", "lane_opened")


def _event_order(event: WorkEvent) -> tuple[int, str]:
    """Sort key putting later events last (seq if present, else timestamp)."""
    return (event.seq if event.seq is not None else -1, event.created_at or "")


def apply_lane_status_events(graph: RunGraph) -> None:
    """Fold ``lane_closed`` / ``lane_opened`` events into each lane's status in place.

    Call once after a run loads. The latest close/open event per lane wins:
    ``lane_closed`` → status ``"closed"`` (+ ``closed_at``), ``lane_opened`` →
    status ``"open"`` (clears ``closed_at``). Lanes with no such event keep the
    status on their record ("open" by default).
    """
    latest: dict[str, WorkEvent] = {}
    for event in graph.work_events:
        if event.event_type not in LANE_STATUS_EVENTS:
            continue
        prev = latest.get(event.lane_id)
        if prev is None or _event_order(event) >= _event_order(prev):
            latest[event.lane_id] = event
    for lane_id, event in latest.items():
        lane = graph.lanes.get(lane_id)
        if lane is None:
            continue
        if event.event_type == "lane_closed":
            graph.lanes[lane_id] = replace(
                lane, status="closed", closed_at=event.created_at or lane.closed_at
            )
        else:
            graph.lanes[lane_id] = replace(lane, status="open", closed_at=None)


@dataclass(frozen=True)
class LaneRecordProvenance:
    record_id: str
    lane_id: str
    lane_name: str | None
    user_id: str
    event_id: str
    event_type: str
    created_at: str | None
    membership_kind: str = "created"

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "lane_id": self.lane_id,
            "lane_name": self.lane_name,
            "user_id": self.user_id,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "membership_kind": self.membership_kind,
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
    # Current lane membership. Creation events set the initial membership;
    # later lane_adopted events may move membership without rewriting creation
    # provenance.
    provenance: dict[str, LaneRecordProvenance] = field(default_factory=dict)
    created_provenance: dict[str, LaneRecordProvenance] = field(default_factory=dict)
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


def lane_validation_errors(
    graph: RunGraph,
    *,
    root_node_id: str | None = None,
) -> tuple[LaneValidationIssue, ...]:
    """Return only blocking lane validation errors."""
    return tuple(
        issue
        for issue in validate_lanes(graph, root_node_id=root_node_id)
        if issue.severity == "error"
    )


def format_lane_validation_errors(
    issues: tuple[LaneValidationIssue, ...] | list[LaneValidationIssue],
) -> str:
    """Format lane validation errors for writer-facing exceptions."""
    if not issues:
        return "lane validation failed"
    rendered = "; ".join(f"{issue.code}: {issue.message}" for issue in issues[:3])
    if len(issues) > 3:
        rendered += f"; ... and {len(issues) - 3} more"
    return f"lane validation failed: {rendered}"


def ensure_valid_lanes(
    graph: RunGraph,
    *,
    root_node_id: str | None = None,
) -> None:
    """Raise when lane invariants have blocking errors."""
    errors = lane_validation_errors(graph, root_node_id=root_node_id)
    if errors:
        raise ValueError(format_lane_validation_errors(errors))


def lane_label(session: Lane | None, lane_id: str) -> str:
    """Return the human label for a lane id."""
    if session is None:
        return lane_id
    return str(session.name or session.lane_id)


def lane_root_node_id(session: Lane) -> str | None:
    """Return the configured lane root/anchor node, if any.

    ``root_node_id`` is the preferred key. ``anchor_node_id`` is accepted as a
    synonym while the vocabulary settles.
    """
    root = session.metadata.get("root_node_id") or session.metadata.get("anchor_node_id")
    return str(root) if root else None


def lane_root_candidates(
    graph: RunGraph,
    lane_id: str,
    membership: LaneMembership | None = None,
    *,
    root_node_id: str | None = None,
) -> tuple[str, ...]:
    """Return explicit or inferred root/anchor nodes for one lane.

    If the lane metadata names ``root_node_id`` / ``anchor_node_id``, that node
    is the lane root. Otherwise roots are inferred from the lane-local topology
    at the unit level. A lane root candidate may be either:

    - a lane-owned node with no producing step in the same lane, or
    - the output node of a lane-owned entry step whose input comes from another
      lane.

    The second form matches the UI's "step + output node" unit: a lane can
    start by deriving a new lane-root node from an external node without making
    that external input part of the lane. This is the only *valid* lane root —
    a lane root must be a step output. A truly producer-less candidate (no
    producing step at all) is still returned here so reachability can traverse
    from it, but ``validate_lanes`` flags it as ``lane_root_not_step_output``.
    """
    run_root = _membership_root_node_id(graph, root_node_id)
    membership = membership or lane_membership(graph, root_node_id=run_root)
    session = graph.lanes.get(lane_id)
    explicit = lane_root_node_id(session) if session is not None else None
    if explicit == run_root:
        return ()
    if explicit is not None:
        return (explicit,)

    roots: set[str] = set()
    lane_nodes = {
        node_id
        for node_id, owner in membership.node_to_lane.items()
        if owner == lane_id
    }
    for node_id in lane_nodes:
        incoming_step = graph.step_to_node(node_id)
        if incoming_step is None:
            roots.add(node_id)
            continue
        if membership.step_to_lane.get(incoming_step) != lane_id:
            roots.add(node_id)
            continue
        step = graph.steps[incoming_step]
        if any(
            membership.node_to_lane.get(input_node_id) != lane_id
            for input_node_id in step.input_node_ids
        ):
            roots.add(node_id)

    return tuple(sorted(roots))


def lane_membership(
    graph: RunGraph,
    *,
    node_ids: set[str] | None = None,
    step_ids: set[str] | None = None,
    payload_ids: set[str] | None = None,
    root_node_id: str | None = None,
) -> LaneMembership:
    """Derive lane membership for graph records.

    The first WorkEvent that creates a record determines that record's lane.
    Later payload attachments remain their own provenance; they do not move the
    target node or step between lanes.

    ``root_node_id`` makes the membership domain explicit: the run root is
    metadata for the whole run, not a lane-owned work record. Every other node
    and every step may be validated as lane-owned.
    """
    node_ids = set(graph.nodes) if node_ids is None else set(node_ids)
    step_ids = set(graph.steps) if step_ids is None else set(step_ids)
    payload_ids = set(graph.payloads) if payload_ids is None else set(payload_ids)
    run_root = _membership_root_node_id(graph, root_node_id)
    if run_root is not None:
        node_ids.discard(run_root)
    included_ids = node_ids | step_ids | payload_ids

    provenance: dict[str, LaneRecordProvenance] = {}
    created_provenance: dict[str, LaneRecordProvenance] = {}
    node_to_lane: dict[str, str] = {}
    step_to_lane: dict[str, str] = {}
    payload_to_lane: dict[str, str] = {}
    lane_nodes: dict[str, set[str]] = {}
    lane_steps: dict[str, set[str]] = {}
    event_ids: list[str] = []

    def provenance_for(
        event: WorkEvent,
        record_id: str,
        membership_kind: str,
    ) -> LaneRecordProvenance:
        session = graph.lanes.get(event.lane_id)
        lane_name = session.name if session is not None else None
        return LaneRecordProvenance(
            record_id=record_id,
            lane_id=event.lane_id,
            lane_name=lane_name,
            user_id=event.user_id,
            event_id=event.event_id,
            event_type=event.event_type,
            created_at=event.created_at,
            membership_kind=membership_kind,
        )

    def assign_membership(record_id: str, prov: LaneRecordProvenance, *, override: bool) -> None:
        if record_id in node_ids:
            old_lane = node_to_lane.get(record_id)
            if old_lane == prov.lane_id and record_id in provenance:
                if override:
                    provenance[record_id] = prov
                return
            if old_lane is not None:
                lane_nodes.get(old_lane, set()).discard(record_id)
            if override or record_id not in node_to_lane:
                node_to_lane[record_id] = prov.lane_id
                lane_nodes.setdefault(prov.lane_id, set()).add(record_id)
                provenance[record_id] = prov
        elif record_id in step_ids:
            old_lane = step_to_lane.get(record_id)
            if old_lane == prov.lane_id and record_id in provenance:
                if override:
                    provenance[record_id] = prov
                return
            if old_lane is not None:
                lane_steps.get(old_lane, set()).discard(record_id)
            if override or record_id not in step_to_lane:
                step_to_lane[record_id] = prov.lane_id
                lane_steps.setdefault(prov.lane_id, set()).add(record_id)
                provenance[record_id] = prov
        elif record_id in payload_ids:
            if override or record_id not in payload_to_lane:
                payload_to_lane[record_id] = prov.lane_id
                provenance[record_id] = prov

    for event in graph.work_events:
        created = [record_id for record_id in event.created_records if record_id in included_ids]
        adopted = _adopted_record_ids(event, included_ids)
        if not created and not adopted:
            continue
        event_ids.append(event.event_id)
        for record_id in created:
            prov = provenance_for(event, record_id, "created")
            created_provenance.setdefault(record_id, prov)
            assign_membership(record_id, prov, override=False)
        for record_id in adopted:
            prov = provenance_for(event, record_id, "adopted")
            assign_membership(record_id, prov, override=True)

    group_lane_ids = tuple(
        sorted(
            lane_id
            for lane_id in set(lane_nodes) | set(lane_steps)
            if lane_nodes.get(lane_id) or lane_steps.get(lane_id)
        )
    )
    groups = tuple(
        LaneGroup(
            lane_id=lane_id,
            label=lane_label(graph.lanes.get(lane_id), lane_id),
            node_ids=tuple(sorted(lane_nodes.get(lane_id, set()))),
            step_ids=tuple(sorted(lane_steps.get(lane_id, set()))),
        )
        for lane_id in group_lane_ids
    )

    return LaneMembership(
        provenance=provenance,
        created_provenance=created_provenance,
        node_to_lane=node_to_lane,
        step_to_lane=step_to_lane,
        payload_to_lane=payload_to_lane,
        groups=groups,
        event_ids=tuple(event_ids),
    )


def lane_boundaries(
    graph: RunGraph,
    membership: LaneMembership | None = None,
    *,
    root_node_id: str | None = None,
) -> tuple[LaneBoundary, ...]:
    """Return cross-lane step inputs as derived lane boundaries."""
    membership = membership or lane_membership(graph, root_node_id=root_node_id)
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
            sorted(
                node_id
                for node_id, owner in membership.node_to_lane.items()
                if owner == lane_id
            )
        ),
        "step_ids": tuple(
            sorted(
                step_id
                for step_id, owner in membership.step_to_lane.items()
                if owner == lane_id
            )
        ),
    }


def lane_edge_node_ids(
    graph: RunGraph,
    lane_id: str,
    membership: LaneMembership | None = None,
    *,
    root_node_id: str | None = None,
    active_only: bool = True,
) -> tuple[str, ...]:
    """Return terminal nodes for one lane.

    A lane edge is a lane-owned node that has no outgoing active step in the
    same lane. Cross-lane outgoing steps do not make the source non-terminal for
    this lane; they represent another lane continuing from this state.
    """
    membership = membership or lane_membership(graph, root_node_id=root_node_id)
    lane_nodes = {
        node_id
        for node_id, owner in membership.node_to_lane.items()
        if owner == lane_id
    }
    lane_steps = {
        step_id
        for step_id, owner in membership.step_to_lane.items()
        if owner == lane_id
    }
    if active_only:
        lane_nodes -= inactive_node_ids(graph)
        lane_steps -= inactive_step_ids(graph)

    out: list[str] = []
    for node_id in sorted(lane_nodes):
        if not any(step_id in lane_steps for step_id in graph.steps_from_node(node_id)):
            out.append(node_id)
    return tuple(out)


def lane_edge_summaries(
    graph: RunGraph,
    lane_id: str,
    membership: LaneMembership | None = None,
    *,
    root_node_id: str | None = None,
    active_only: bool = True,
) -> tuple[SummaryPayload, ...]:
    """Return summaries attached to terminal nodes in one lane."""
    edge_nodes = set(
        lane_edge_node_ids(
            graph,
            lane_id,
            membership,
            root_node_id=root_node_id,
            active_only=active_only,
        )
    )
    if not edge_nodes:
        return ()
    return tuple(
        payload
        for payload in graph.payloads.values()
        if isinstance(payload, SummaryPayload) and payload.target_id in edge_nodes
    )


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
    run_root = _membership_root_node_id(graph, root_node_id)
    membership = lane_membership(graph, root_node_id=run_root)
    issues: list[LaneValidationIssue] = []

    lane_node_ids: dict[str, set[str]] = {}
    lane_step_ids: dict[str, set[str]] = {}
    for node_id, lane_id in membership.node_to_lane.items():
        lane_node_ids.setdefault(lane_id, set()).add(node_id)
    for step_id, lane_id in membership.step_to_lane.items():
        lane_step_ids.setdefault(lane_id, set()).add(step_id)

    for lane_id, session in graph.lanes.items():
        lane_root = lane_root_node_id(session)
        if lane_root == run_root:
            issues.append(
                LaneValidationIssue(
                    code="run_root_as_lane_root",
                    severity="error",
                    message=f"run root cannot be a lane root: {lane_root}",
                    record_id=lane_root,
                    lane_id=lane_id,
                )
            )
            continue
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

    for lane_id in sorted(set(lane_node_ids) | set(lane_step_ids)):
        nodes = lane_node_ids.get(lane_id, set())
        steps = lane_step_ids.get(lane_id, set())
        roots = lane_root_candidates(
            graph,
            lane_id,
            membership,
            root_node_id=run_root,
        )

        if lane_id == "default" and (nodes or steps):
            issues.append(
                LaneValidationIssue(
                    code="default_lane_membership",
                    severity="warning",
                    message=(
                        f"default lane still owns {len(nodes)} nodes and "
                        f"{len(steps)} steps"
                    ),
                    lane_id=lane_id,
                )
            )

        if not roots and (nodes or steps):
            issues.append(
                LaneValidationIssue(
                    code="lane_without_root",
                    severity="error",
                    message=f"lane {lane_id!r} has records but no root candidate",
                    lane_id=lane_id,
                )
            )
            continue

        if len(roots) > 1:
            issues.append(
                LaneValidationIssue(
                    code="multiple_lane_roots",
                    severity="error",
                    message=(
                        f"lane {lane_id!r} has {len(roots)} root candidates: "
                        + ", ".join(roots)
                    ),
                    lane_id=lane_id,
                )
            )

        reachable_nodes, reachable_steps = _reachable_lane_records(
            graph,
            lane_id,
            roots,
            membership,
        )
        for node_id in sorted(nodes - reachable_nodes):
            issues.append(
                LaneValidationIssue(
                    code="lane_node_unreachable_from_root",
                    severity="error",
                    message=(
                        f"node {node_id} is in lane {lane_id!r} but is not "
                        "reachable from the lane root"
                    ),
                    record_id=node_id,
                    lane_id=lane_id,
                )
            )
        for step_id in sorted(steps - reachable_steps):
            issues.append(
                LaneValidationIssue(
                    code="lane_step_unreachable_from_root",
                    severity="error",
                    message=(
                        f"step {step_id} is in lane {lane_id!r} but is not "
                        "reachable from the lane root"
                    ),
                    record_id=step_id,
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
                    severity="error",
                    message=f"step has no lane provenance: {step_id}",
                    record_id=step_id,
                )
            )
            continue
        if output_lane is None:
            issues.append(
                LaneValidationIssue(
                    code="output_node_without_lane",
                    severity="error",
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
        for lane_id in graph.lanes
        for root in lane_root_candidates(
            graph,
            lane_id,
            membership,
            root_node_id=run_root,
        )
    }
    for node_id in sorted(set(graph.nodes) - {run_root} - set(membership.node_to_lane)):
        issues.append(
            LaneValidationIssue(
                code="node_without_lane",
                severity="error",
                message=f"node has no lane provenance: {node_id}",
                record_id=node_id,
            )
        )

    # The run root is the only legitimately producer-less node. Every other
    # node — including a lane root — must be the output of a step (a Node is
    # born only as a Step's output now that add_node is gone). A producer-less
    # node that a lane treats as its root is a degenerate lane entry.
    for node_id in graph.roots():
        if node_id == run_root:
            continue
        if node_id in lane_roots:
            issues.append(
                LaneValidationIssue(
                    code="lane_root_not_step_output",
                    severity="error",
                    message=(
                        "lane root must be a step output, but is producer-less: "
                        f"{node_id}"
                    ),
                    record_id=node_id,
                    lane_id=membership.node_to_lane.get(node_id),
                )
            )
            continue
        issues.append(
            LaneValidationIssue(
                code="producerless_node_without_root_role",
                severity="error",
                message=(
                    "producer-less node is not the run root or a lane root: "
                    f"{node_id}"
                ),
                record_id=node_id,
            )
        )

    return tuple(issues)


def _reachable_lane_records(
    graph: RunGraph,
    lane_id: str,
    root_node_ids: tuple[str, ...],
    membership: LaneMembership,
) -> tuple[set[str], set[str]]:
    reachable_nodes: set[str] = set()
    reachable_steps: set[str] = set()
    queue = list(root_node_ids)
    seen_nodes: set[str] = set()

    while queue:
        node_id = queue.pop(0)
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)
        if membership.node_to_lane.get(node_id) == lane_id:
            reachable_nodes.add(node_id)

        incoming_step = graph.step_to_node(node_id)
        if (
            incoming_step is not None
            and membership.step_to_lane.get(incoming_step) == lane_id
        ):
            reachable_steps.add(incoming_step)

        for step_id in graph.steps_from_node(node_id):
            if membership.step_to_lane.get(step_id) != lane_id:
                continue
            if step_id in reachable_steps:
                continue
            reachable_steps.add(step_id)
            output_id = graph.step_output(step_id)
            if output_id and output_id not in seen_nodes:
                queue.append(output_id)

    return reachable_nodes, reachable_steps


def _run_root_node_id(graph: RunGraph) -> str | None:
    root = graph.metadata.get("root_node_id")
    return str(root) if root is not None else None


def _membership_root_node_id(graph: RunGraph, root_node_id: str | None) -> str | None:
    return str(root_node_id) if root_node_id is not None else _run_root_node_id(graph)


def lane_export_view(
    graph: RunGraph,
    *,
    node_ids: set[str],
    step_ids: set[str],
    payload_ids: set[str],
    root_node_id: str | None = None,
) -> dict:
    """Return JSON-ready lane data for export/API surfaces."""
    membership = lane_membership(
        graph,
        node_ids=node_ids,
        step_ids=step_ids,
        payload_ids=payload_ids,
        root_node_id=root_node_id,
    )
    event_ids = set(membership.event_ids)
    sessions = [
        session.to_dict()
        for session in sorted(
            graph.lanes.values(),
            key=lambda s: (s.started_at or "", s.lane_id),
        )
    ]
    events = [
        event.to_dict()
        for event in graph.work_events
        if event.event_id in event_ids
    ]
    return {
        "lanes": sessions,
        "work_events": events,
        "record_provenance": {
            record_id: provenance.to_dict()
            for record_id, provenance in sorted(membership.provenance.items())
        },
        "created_provenance": {
            record_id: provenance.to_dict()
            for record_id, provenance in sorted(membership.created_provenance.items())
        },
        "groups": [group.to_dict() for group in membership.groups],
        "lane_boundaries": [
            boundary.to_dict()
            for boundary in lane_boundaries(graph, membership)
            if boundary.step_id in step_ids
        ],
        "lane_edge_summaries": [
            {
                "lane_id": group.lane_id,
                "node_id": summary.target_id,
                "payload_id": summary.payload_id,
                "text": summary.text,
                "metadata": summary.metadata,
            }
            for group in membership.groups
            for summary in lane_edge_summaries(graph, group.lane_id, membership)
            if summary.payload_id in payload_ids and summary.target_id in node_ids
        ],
    }


def _adopted_record_ids(event: WorkEvent, included_ids: set[str]) -> list[str]:
    if event.event_type != "lane_adopted":
        return []
    raw = event.data.get("record_ids")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        record_id = str(value)
        if record_id in included_ids and record_id not in seen:
            seen.add(record_id)
            out.append(record_id)
    return out
