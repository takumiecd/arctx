"""Core lane semantics over a RunGraph.

Lanes are the durable work/thought units of a run. The graph records stay
minimal: node/step/payload topology is stored in ``RunGraph``, while lane
membership is derived from append-only ``WorkEvent.created_records``.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from arctx.core.cuts import inactive_node_ids, inactive_step_ids
from arctx.core.run_graph import RunGraph
from arctx.core.schema.payloads import PayloadBase, SummaryPayload
from arctx.core.schema.work import WorkEvent, Lane


# Lane status is a PROJECTION of the append-only work-event log, not a mutable
# field on the lane record. A lane opens at create (status "open") and toggles via
# ``lane_closed`` / ``lane_opened`` events; the lane row on disk stays as first
# written, and the current status is folded from the events on load.
LANE_STATUS_EVENTS = ("lane_closed", "lane_opened")


def _seq_is_authoritative(events) -> bool:
    """True when ``seq`` alone totally orders *events*.

    Mirrors ``arctx.storage.jsonl._seq_is_authoritative``; see it for why.
    """
    seqs = [event.seq for event in events]
    if any(seq is None for seq in seqs):
        return False
    return len(seqs) == len(set(seqs))


def _event_order(event: WorkEvent, *, by_seq: bool = False) -> tuple:
    """Sort key putting later events last.

    ``by_seq`` when the caller has checked that seq totally orders this ledger
    (one branch, every event numbered) — seq is then immune to clock skew
    between machines. Otherwise the wall clock leads, because a union merge
    makes seq collide across branches.
    """
    if by_seq:
        return (event.seq if event.seq is not None else -1, event.created_at or "")
    return (event.created_at or "", event.seq if event.seq is not None else -1)


def apply_lane_status_events(graph: RunGraph) -> None:
    """Fold ``lane_closed`` / ``lane_opened`` events into each lane's status in place.

    Call once after a run loads. The latest close/open event per lane wins:
    ``lane_closed`` → status ``"closed"`` (+ ``closed_at``), ``lane_opened`` →
    status ``"open"`` (clears ``closed_at``). Lanes with no such event keep the
    status on their record ("open" by default).
    """
    by_seq = _seq_is_authoritative(graph.work_events)
    latest: dict[str, WorkEvent] = {}
    for event in graph.work_events:
        if event.event_type not in LANE_STATUS_EVENTS:
            continue
        prev = latest.get(event.lane_id)
        if prev is None or _event_order(event, by_seq=by_seq) >= _event_order(
            prev, by_seq=by_seq
        ):
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
    # Lane membership, derived purely from the event that created each record.
    # A record never moves between lanes.
    provenance: dict[str, LaneRecordProvenance] = field(default_factory=dict)
    node_to_lane: dict[str, str] = field(default_factory=dict)
    step_to_lane: dict[str, str] = field(default_factory=dict)
    payload_to_lane: dict[str, str] = field(default_factory=dict)
    # The reverse index. lane_membership computes it anyway; keeping it turns
    # "which nodes belong to this lane" from a scan of every node into a dict
    # lookup. Lanes grow with steps in real use, so the scan was the quadratic.
    lane_nodes: dict[str, frozenset[str]] = field(default_factory=dict)
    lane_steps: dict[str, frozenset[str]] = field(default_factory=dict)
    lane_payloads: dict[str, frozenset[str]] = field(default_factory=dict)
    groups: tuple[LaneGroup, ...] = ()
    event_ids: tuple[str, ...] = ()

    def nodes_in(self, lane_id: str) -> frozenset[str]:
        """Return the nodes owned by *lane_id*."""
        return self.lane_nodes.get(lane_id, frozenset())

    def steps_in(self, lane_id: str) -> frozenset[str]:
        """Return the steps owned by *lane_id*."""
        return self.lane_steps.get(lane_id, frozenset())

    def payloads_in(self, lane_id: str) -> frozenset[str]:
        """Return the payloads owned by *lane_id*."""
        return self.lane_payloads.get(lane_id, frozenset())


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
    - the output node of a lane-owned entry step with no input from the same
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
    lane_nodes = membership.nodes_in(lane_id)
    for node_id in lane_nodes:
        incoming_step = graph.step_to_node(node_id)
        if incoming_step is None:
            roots.add(node_id)
            continue
        if membership.step_to_lane.get(incoming_step) != lane_id:
            roots.add(node_id)
            continue
        step = graph.steps[incoming_step]
        if not any(
            membership.node_to_lane.get(input_node_id) == lane_id
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
    node_to_lane: dict[str, str] = {}
    step_to_lane: dict[str, str] = {}
    payload_to_lane: dict[str, str] = {}
    lane_nodes: dict[str, set[str]] = {}
    lane_steps: dict[str, set[str]] = {}
    lane_payloads: dict[str, set[str]] = {}
    event_ids: list[str] = []

    def provenance_for(event: WorkEvent, record_id: str) -> LaneRecordProvenance:
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
        )

    def assign_membership(record_id: str, prov: LaneRecordProvenance) -> None:
        if record_id in node_ids:
            if record_id not in node_to_lane:
                node_to_lane[record_id] = prov.lane_id
                lane_nodes.setdefault(prov.lane_id, set()).add(record_id)
                provenance[record_id] = prov
        elif record_id in step_ids:
            if record_id not in step_to_lane:
                step_to_lane[record_id] = prov.lane_id
                lane_steps.setdefault(prov.lane_id, set()).add(record_id)
                provenance[record_id] = prov
        elif record_id in payload_ids:
            if record_id not in payload_to_lane:
                payload_to_lane[record_id] = prov.lane_id
                lane_payloads.setdefault(prov.lane_id, set()).add(record_id)
                provenance[record_id] = prov

    for event in graph.work_events:
        created = [record_id for record_id in event.created_records if record_id in included_ids]
        if not created:
            continue
        event_ids.append(event.event_id)
        for record_id in created:
            assign_membership(record_id, provenance_for(event, record_id))

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
        node_to_lane=node_to_lane,
        step_to_lane=step_to_lane,
        payload_to_lane=payload_to_lane,
        lane_nodes={k: frozenset(v) for k, v in lane_nodes.items()},
        lane_steps={k: frozenset(v) for k, v in lane_steps.items()},
        lane_payloads={k: frozenset(v) for k, v in lane_payloads.items()},
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
    inactive_nodes: set[str] | frozenset[str] | None = None,
    inactive_steps: set[str] | frozenset[str] | None = None,
) -> tuple[str, ...]:
    """Return terminal nodes for one lane.

    A lane edge is a lane-owned node that has no outgoing active step in the
    same lane. Cross-lane outgoing steps do not make the source non-terminal for
    this lane; they represent another lane continuing from this state.

    ``inactive_nodes`` / ``inactive_steps`` let a caller that is already walking
    every lane compute the cut fixpoint once and hand it down. The fixpoint is
    whole-graph, so recomputing it per lane is what made rendering quadratic.
    """
    membership = membership or lane_membership(graph, root_node_id=root_node_id)
    lane_nodes = set(membership.nodes_in(lane_id))
    lane_steps = set(membership.steps_in(lane_id))
    if active_only:
        lane_nodes -= (
            inactive_nodes if inactive_nodes is not None else inactive_node_ids(graph)
        )
        lane_steps -= (
            inactive_steps if inactive_steps is not None else inactive_step_ids(graph)
        )

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
    inactive_nodes: set[str] | frozenset[str] | None = None,
    inactive_steps: set[str] | frozenset[str] | None = None,
) -> tuple[SummaryPayload, ...]:
    """Return summaries attached to terminal nodes in one lane."""
    edge_nodes = set(
        lane_edge_node_ids(
            graph,
            lane_id,
            membership,
            root_node_id=root_node_id,
            active_only=active_only,
            inactive_nodes=inactive_nodes,
            inactive_steps=inactive_steps,
        )
    )
    if not edge_nodes:
        return ()
    return tuple(
        payload
        for payload in graph.payloads.values()
        if isinstance(payload, SummaryPayload) and payload.target_id in edge_nodes
    )


def lane_active_frontiers(
    graph: RunGraph,
    lane_id: str,
    membership: LaneMembership | None = None,
    *,
    root_node_id: str | None = None,
    inactive_nodes: set[str] | frozenset[str] | None = None,
    inactive_steps: set[str] | frozenset[str] | None = None,
) -> tuple[str, ...]:
    """Return this lane's active frontier nodes.

    A frontier is a lane-owned node that is active (:func:`arctx.core.cuts.
    is_active_node`) and has *no active* outgoing step — not even to another
    lane. A cut outgoing step does not count: append-only history means a
    node whose only child was later cut must be able to re-enter the
    frontier, since there is no way to "undo" the child creation other than
    cutting it. This is stricter than :func:`lane_edge_node_ids` (which only
    excludes outgoing steps within the same lane) and is the set of nodes an
    agent could plausibly continue from without an explicit ``--from``.
    """
    membership = membership or lane_membership(graph, root_node_id=root_node_id)
    lane_nodes = membership.nodes_in(lane_id)
    # Both fixpoints are hoisted. `is_active_node` recomputes the whole-graph
    # cut fixpoint on every call, so asking it per node made the everyday
    # `arctx add` -- which resolves the frontier to find its default --from --
    # quadratic in the size of the run.
    if inactive_nodes is None:
        inactive_nodes = inactive_node_ids(graph)
    if inactive_steps is None:
        inactive_steps = inactive_step_ids(graph)
    return tuple(
        node_id
        for node_id in sorted(lane_nodes)
        if node_id not in inactive_nodes
        and all(
            step_id in inactive_steps for step_id in graph.steps_from_node(node_id)
        )
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
    from arctx.core.cuts import nodes_with_multiple_active_producers

    run_root = _membership_root_node_id(graph, root_node_id)
    membership = lane_membership(graph, root_node_id=run_root)
    issues: list[LaneValidationIssue] = []

    # Not a lane rule, but this is the one validator every write path and
    # `arctx doctor` already run, and the state it catches is otherwise
    # completely silent.
    for node_id, producers in nodes_with_multiple_active_producers(graph):
        issues.append(
            LaneValidationIssue(
                code="multiple_active_producers",
                severity="error",
                message=(
                    f"node {node_id} has {len(producers)} active producing "
                    f"steps ({', '.join(producers)}); at most one may be "
                    f"active — retire the wrong one with "
                    f"`arctx cut step <ID>`"
                ),
                record_id=node_id,
                lane_id=membership.step_to_lane.get(producers[0]),
            )
        )

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

    inactive_nodes_all = inactive_node_ids(graph)
    inactive_steps_all = inactive_step_ids(graph)

    for lane_id in sorted(set(lane_node_ids) | set(lane_step_ids)):
        nodes = lane_node_ids.get(lane_id, set())
        steps = lane_step_ids.get(lane_id, set())
        roots = lane_root_candidates(
            graph,
            lane_id,
            membership,
            root_node_id=run_root,
        )

        if lane_id == "default":
            # Hygiene check only: cut records shouldn't keep this warning
            # alive forever, since append-only history can never remove a
            # default-lane record from membership — only cutting it.
            #
            # And it only means anything once the run uses lanes at all. In a
            # run with no named lane, the default lane owning everything is
            # simply where the records are — so warning about it made a brand
            # new user's very first `arctx add` complain about the step it had
            # just written, right after `arctx init` told them to write it.
            uses_lanes = any(
                lane != "default" for lane in set(lane_node_ids) | set(lane_step_ids)
            ) or any(lane != "default" for lane in graph.lanes)
            active_default_nodes = nodes - inactive_nodes_all
            active_default_steps = steps - inactive_steps_all
            if uses_lanes and (active_default_nodes or active_default_steps):
                issues.append(
                    LaneValidationIssue(
                        code="default_lane_membership",
                        severity="warning",
                        message=(
                            f"default lane still owns {len(active_default_nodes)} "
                            f"nodes and {len(active_default_steps)} steps"
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


# ---------------------------------------------------------------------------
# Retrieval: flat lane overviews and search
#
# Lanes are flat (git-branch-like). Retrieval answers exactly three questions:
# "what is happening now" (guide --context), "what has been tried about X"
# (search), "what happened here" (dump/show). Nothing below walks a hierarchy —
# there is none.
# ---------------------------------------------------------------------------


def record_event_rank(graph: RunGraph) -> dict[str, int]:
    """Return record_id → position in the append-only work-event log.

    Record order is the durable ordering signal: jsonl line order is not
    meaningful after a union merge, but ``WorkEvent.created_records`` is an
    append-only ledger. Records with no event are absent from the mapping and
    callers should treat them as rank ``-1`` (oldest).
    """
    rank: dict[str, int] = {}
    for index, event in enumerate(graph.work_events):
        for record_id in event.created_records:
            rank.setdefault(record_id, index)
    return rank


def lane_summary_payloads(
    graph: RunGraph,
    lane_id: str,
    membership: LaneMembership | None = None,
    *,
    root_node_id: str | None = None,
    rank: dict[str, int] | None = None,
) -> tuple[SummaryPayload, ...]:
    """Return the lane's summary payloads oldest-first in work-event order.

    A lane's summaries are the :class:`SummaryPayload` records the lane itself
    created (``lane close`` / ``lane summarize`` both attach one). Ordering
    comes from :func:`record_event_rank`, with the payload's own id as a stable
    tie-break.

    ``rank`` lets a caller walking every lane build that mapping once. It is
    whole-graph, so rebuilding it per lane was quadratic.
    """
    membership = membership or lane_membership(graph, root_node_id=root_node_id)
    if rank is None:
        rank = record_event_rank(graph)
    payloads = [
        payload
        for payload in (
            graph.payloads.get(payload_id)
            for payload_id in membership.payloads_in(lane_id)
        )
        if isinstance(payload, SummaryPayload)
    ]
    payloads.sort(key=lambda p: (rank.get(p.payload_id, -1), p.payload_id))
    return tuple(payloads)


def lane_current_summary(
    graph: RunGraph,
    lane_id: str,
    membership: LaneMembership | None = None,
    *,
    root_node_id: str | None = None,
    rank: dict[str, int] | None = None,
) -> SummaryPayload | None:
    """Return the lane's current summary — the latest one wins."""
    payloads = lane_summary_payloads(
        graph, lane_id, membership, root_node_id=root_node_id, rank=rank
    )
    return payloads[-1] if payloads else None


def lane_purpose(lane: Lane) -> str | None:
    """Return the lane's recorded purpose, if any."""
    purpose = lane.metadata.get("purpose")
    text = str(purpose).strip() if purpose is not None else ""
    return text or None


def collapse_summary(text: str | None, *, limit: int = 160) -> str:
    """Collapse a summary to its first non-empty line, truncated to *limit*."""
    if not text:
        return ""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if len(first) > limit:
        return first[: max(0, limit - 3)].rstrip() + "..."
    return first


@dataclass(frozen=True)
class LaneOverview:
    """Flat, retrieval-oriented projection of one lane."""

    lane_id: str
    name: str | None
    status: str
    purpose: str | None
    started_at: str | None
    closed_at: str | None
    summary_text: str | None
    summary_payload_id: str | None
    summary_node_id: str | None
    node_count: int
    step_count: int
    payload_count: int
    active_frontier_node_ids: tuple[str, ...]

    @property
    def label(self) -> str:
        return self.name or self.lane_id

    @property
    def summary_line(self) -> str:
        return collapse_summary(self.summary_text)

    def to_dict(self) -> dict:
        return {
            "lane_id": self.lane_id,
            "name": self.name,
            "label": self.label,
            "status": self.status,
            "purpose": self.purpose,
            "started_at": self.started_at,
            "closed_at": self.closed_at,
            "summary": self.summary_text,
            "summary_line": self.summary_line,
            "summary_payload_id": self.summary_payload_id,
            "summary_node_id": self.summary_node_id,
            "counts": {
                "nodes": self.node_count,
                "steps": self.step_count,
                "payloads": self.payload_count,
            },
            "active_frontier_node_ids": list(self.active_frontier_node_ids),
        }


def lane_overview(
    graph: RunGraph,
    lane_id: str,
    membership: LaneMembership | None = None,
    *,
    root_node_id: str | None = None,
    inactive_nodes: set[str] | frozenset[str] | None = None,
    inactive_steps: set[str] | frozenset[str] | None = None,
    rank: dict[str, int] | None = None,
) -> LaneOverview:
    """Fold one lane's record into a flat overview."""
    lane = graph.lanes.get(lane_id)
    if lane is None:
        raise KeyError(f"unknown lane: {lane_id}")
    membership = membership or lane_membership(graph, root_node_id=root_node_id)
    summary = lane_current_summary(graph, lane_id, membership, rank=rank)
    # A lane closed while owning no records has no SummaryPayload to carry its
    # conclusion — the close event's reason is the durable fallback text.
    fallback_text = None
    if summary is None and lane.status == "closed":
        for event in reversed(graph.work_events):
            if event.lane_id == lane_id and event.event_type == "lane_closed":
                reason = event.data.get("reason") if event.data else None
                if isinstance(reason, str) and reason.strip():
                    fallback_text = reason
                break
    return LaneOverview(
        lane_id=lane_id,
        name=lane.name,
        status=lane.status,
        purpose=lane_purpose(lane),
        started_at=lane.started_at,
        closed_at=lane.closed_at,
        summary_text=summary.text if summary is not None else fallback_text,
        summary_payload_id=summary.payload_id if summary is not None else None,
        summary_node_id=summary.target_id if summary is not None else None,
        node_count=len(membership.nodes_in(lane_id)),
        step_count=len(membership.steps_in(lane_id)),
        payload_count=len(membership.payloads_in(lane_id)),
        active_frontier_node_ids=lane_active_frontiers(
            graph,
            lane_id,
            membership,
            inactive_nodes=inactive_nodes,
            inactive_steps=inactive_steps,
        ),
    )


def list_lane_overviews(
    graph: RunGraph,
    *,
    root_node_id: str | None = None,
) -> tuple[LaneOverview, ...]:
    """Return every lane as a flat overview, open lanes first, then by start.

    The ordering is the one ``explore`` renders: open lanes are the live work
    surface (like ``git branch`` hiding merged noise), closed lanes are history.
    """
    membership = lane_membership(graph, root_node_id=root_node_id)
    inactive_nodes = inactive_node_ids(graph)
    inactive_steps = inactive_step_ids(graph)
    rank = record_event_rank(graph)
    overviews = [
        lane_overview(
            graph,
            lane_id,
            membership,
            inactive_nodes=inactive_nodes,
            inactive_steps=inactive_steps,
            rank=rank,
        )
        for lane_id in graph.lanes
    ]
    overviews.sort(
        key=lambda item: (
            item.status != "open",
            item.started_at or "",
            item.lane_id,
        )
    )
    return tuple(overviews)


@dataclass(frozen=True)
class LaneSearchHit:
    """One lane matched by :func:`search_lanes`."""

    lane_id: str
    name: str | None
    status: str
    snippet: str
    name_match: bool
    matched_record_ids: tuple[str, ...]
    matched_payload_ids: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "lane_id": self.lane_id,
            "name": self.name,
            "label": self.name or self.lane_id,
            "status": self.status,
            "snippet": self.snippet,
            "name_match": self.name_match,
            "matched_record_ids": list(self.matched_record_ids),
            "matched_payload_ids": list(self.matched_payload_ids),
        }


# Opaque ids and record plumbing are never what a human searches for, and
# leaking them into the haystack produces snippets full of UUID noise. Use
# ``arctx show <ID>`` when you already have an id.
_NON_SEARCHABLE_KEYS = frozenset(
    {
        "payload_id",
        "target_id",
        "target_kind",
        "payload_type",
        "step_id",
        "node_id",
        "input_node_ids",
        "output_node_id",
        "lane_id",
    }
)


def _searchable_text(value: object) -> list[str]:
    if isinstance(value, dict):
        return [
            text
            for key, item in value.items()
            if key not in _NON_SEARCHABLE_KEYS
            for text in _searchable_text(item)
        ]
    if isinstance(value, (list, tuple)):
        return [text for item in value for text in _searchable_text(item)]
    return [str(value)] if value is not None else []


def search_lanes(
    graph: RunGraph,
    query: str,
    *,
    root_node_id: str | None = None,
    snippet_chars: int = 180,
) -> tuple[LaneSearchHit, ...]:
    """Search lane names and the payloads a lane owns.

    Whitespace-separated terms match case-insensitively with AND semantics. The
    haystack for a lane is its name plus every payload it created — both lane
    summaries and payloads attached to the nodes/steps it owns. Search is
    position-independent: there is no current lane and no descent, which is why
    it is the primary retrieval path.

    Hits rank name matches first, then alphabetically by label.
    """
    terms = tuple(term.casefold() for term in query.split() if term.strip())
    if not terms:
        return ()
    membership = lane_membership(graph, root_node_id=root_node_id)
    record_owner: dict[str, str] = {
        **membership.node_to_lane,
        **membership.step_to_lane,
    }

    # Group every payload under the lane that owns it: either the payload was
    # created by the lane, or its target record belongs to the lane.
    by_lane: dict[str, list[PayloadBase]] = {}
    for payload_id, payload in graph.payloads.items():
        owner = membership.payload_to_lane.get(payload_id) or record_owner.get(
            payload.target_id
        )
        if owner is not None:
            by_lane.setdefault(owner, []).append(payload)

    hits: list[LaneSearchHit] = []
    for lane in graph.lanes.values():
        label = lane.name or lane.lane_id
        parts = [label]
        purpose = lane_purpose(lane)
        if purpose:
            parts.append(purpose)
        payloads = by_lane.get(lane.lane_id, [])
        matched_payload_ids: list[str] = []
        matched_record_ids: list[str] = []
        for payload in payloads:
            texts = _searchable_text(payload.to_dict())
            parts.extend(texts)
            folded_payload = "\n".join(texts).casefold()
            if any(term in folded_payload for term in terms):
                matched_payload_ids.append(payload.payload_id)
                matched_record_ids.append(payload.target_id)

        haystack = "\n".join(parts)
        folded = haystack.casefold()
        if not all(term in folded for term in terms):
            continue

        index = folded.find(terms[0])
        start = max(0, index - 45)
        snippet = " ".join(haystack[start : start + snippet_chars].split())
        hits.append(
            LaneSearchHit(
                lane_id=lane.lane_id,
                name=lane.name,
                status=lane.status,
                snippet=snippet,
                name_match=any(term in label.casefold() for term in terms),
                matched_record_ids=tuple(dict.fromkeys(matched_record_ids)),
                matched_payload_ids=tuple(dict.fromkeys(matched_payload_ids)),
            )
        )

    hits.sort(key=lambda hit: (not hit.name_match, str(hit.name or hit.lane_id).casefold()))
    return tuple(hits)


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
    # One cut fixpoint for the whole document, not two per lane.
    inactive_nodes = inactive_node_ids(graph)
    inactive_steps = inactive_step_ids(graph)
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
            for summary in lane_edge_summaries(
                graph,
                group.lane_id,
                membership,
                inactive_nodes=inactive_nodes,
                inactive_steps=inactive_steps,
            )
            if summary.payload_id in payload_ids and summary.target_id in node_ids
        ],
    }


def stale_open_lanes(
    graph: RunGraph,
    *,
    now: "datetime | None" = None,
    idle_days: int = 7,
) -> list[tuple[Lane, str | None, int]]:
    """Open lanes with no writes for *idle_days* or longer, oldest first.

    Working past finished lanes without closing them erodes the record: the
    conclusion never gets written, and ``explore`` fills up with open lanes
    nobody is in. This is the derivation behind the "close your lanes" nudge
    printed by ``lane create`` and shown in ``guide --context``.

    Returns ``(lane, last_activity_iso, idle_days)`` triples. A lane with no
    events at all falls back to ``started_at``; a lane with neither is treated
    as infinitely idle (idle count ``10**6``). The implicit ``default`` lane
    is skipped — it has no lifecycle to manage.
    """
    from datetime import datetime, timezone

    current = now or datetime.now(timezone.utc)
    last_by_lane: dict[str, str] = {}
    for event in graph.work_events:
        if event.created_at:
            previous = last_by_lane.get(event.lane_id, "")
            if event.created_at > previous:
                last_by_lane[event.lane_id] = event.created_at

    stale: list[tuple[Lane, str | None, int]] = []
    for lane in graph.lanes.values():
        if lane.status != "open" or lane.lane_id == "default":
            continue
        last = last_by_lane.get(lane.lane_id) or lane.started_at
        if last:
            try:
                stamp = datetime.fromisoformat(last)
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=timezone.utc)
                idle = (current - stamp).days
            except ValueError:
                idle = 10**6
        else:
            idle = 10**6
        if idle >= idle_days:
            stale.append((lane, last, idle))
    stale.sort(key=lambda item: -item[2])
    return stale
