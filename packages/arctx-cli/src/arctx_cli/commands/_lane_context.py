"""Shared helpers for resolving the current lane and its active frontiers.

Both ``arctx add`` (defaulting ``--from`` to the current lane's frontier) and
``arctx guide`` (reporting "Active Frontiers in Lane") need the same three
steps: resolve the active lane id (env / --lane / repo pointer), look up the
``Lane`` object by id or name, and compute its active frontier nodes. Keeping
this in one place means both commands agree on lane resolution order and on
what counts as a frontier.
"""

from __future__ import annotations

from dataclasses import dataclass


def find_lane(handle, name_or_id: str):
    """Resolve a Lane object by lane_id or by name. Returns None if absent."""
    lane = handle.run_graph.lanes.get(name_or_id)
    if lane is not None:
        return lane
    for candidate in handle.run_graph.lanes.values():
        if candidate.name == name_or_id:
            return candidate
    return None


@dataclass(frozen=True)
class LaneFrontierContext:
    """Resolution result: the lane id/name that was requested, the Lane object
    found for it (if any), and its active frontier node ids."""

    lane_id: str
    lane_name: str | None
    frontier_node_ids: tuple[str, ...]


def resolve_lane_frontiers(handle, lane_id: str) -> LaneFrontierContext:
    """Resolve ``lane_id`` (id or name) to its active frontier nodes.

    ``lane_id`` should already be resolved via the canonical chain (explicit
    flag / ``ARCTX_LANE_ID`` / repo pointer) — see
    ``arctx_cli.context.resolve_lane_id_from_args``. This helper only does the
    graph-level lookup: Lane object + frontier computation.
    """
    from arctx.core.lanes import lane_active_frontiers

    lane = find_lane(handle, lane_id)
    if lane is None:
        return LaneFrontierContext(lane_id=lane_id, lane_name=None, frontier_node_ids=())
    frontiers = lane_active_frontiers(handle.run_graph, lane.lane_id)
    return LaneFrontierContext(
        lane_id=lane.lane_id, lane_name=lane.name, frontier_node_ids=frontiers
    )


def root_frontier_fallback(handle) -> str | None:
    """Return the run root node id if it is usable as a default ``--from``.

    The run root is deliberately excluded from lane membership (it is run
    metadata, not a lane-owned record — see ``lane_membership``), so
    ``lane_active_frontiers`` never includes it and a brand-new run always
    reports zero frontiers for every lane. That makes the very first
    ``arctx add`` on a fresh run fail without ``--from`` even though the root
    is the only possible input.

    Returns the root node id when it is both active (not cut) and itself a
    frontier (no outgoing steps yet, from *any* lane) — i.e. nothing has been
    recorded against it yet. Returns ``None`` otherwise, so callers fall back
    to the existing "no active frontiers" error.
    """
    from arctx.core.cuts import is_active_node

    root_node_id = handle.root_node_id
    if not root_node_id or root_node_id not in handle.run_graph.nodes:
        return None
    if not is_active_node(handle.run_graph, root_node_id):
        return None
    if handle.run_graph.steps_from_node(root_node_id):
        return None
    return root_node_id


def describe_frontier_candidates(handle, node_ids) -> list[str]:
    """Format frontier node ids as ``n_xxx (type_a, type_b)`` lines, like guide."""
    lines = []
    for node_id in node_ids:
        payloads = handle.run_graph.payloads_for_node(node_id)
        types = [p.payload_type for p in payloads]
        type_str = f" ({', '.join(types)})" if types else ""
        lines.append(f"{node_id}{type_str}")
    return lines
