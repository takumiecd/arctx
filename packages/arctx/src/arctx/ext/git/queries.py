"""Git-specific graph queries.

These helpers intentionally live in the git extension so ``arctx.core`` remains
focused on generic DAG structure and payload attachment.
"""

from __future__ import annotations

from arctx.core.run_graph import RunGraph
from arctx.ext.git.payloads import GitChangePayload


def branch_members(graph: RunGraph, branch: str) -> set[str]:
    """Return node IDs in the latest recorded git branch ancestry."""
    from arctx.core.schema.work_helpers import latest_branch_tip

    tip_event = latest_branch_tip(graph, branch)
    if tip_event is None:
        return set()
    tip_node_id = str(tip_event.data.get("tip_node_id", ""))
    if not tip_node_id or tip_node_id not in graph.nodes:
        return set()
    return graph.ancestors_of(tip_node_id) | {tip_node_id}


def current_sha(graph: RunGraph, step_id: str) -> str | None:
    """Return the latest GitChangePayload head commit for a step."""
    git_payloads = graph.payloads_for_step(
        step_id, payload_type="git_change"
    )
    if not git_payloads:
        return None
    latest = git_payloads[-1]
    assert isinstance(latest, GitChangePayload)
    return latest.head_commit


def step_by_sha(graph: RunGraph, sha: str) -> str | None:
    """Find the step whose latest GitChangePayload head commit matches."""
    result: str | None = None
    for step_id in graph.steps:
        if current_sha(graph, step_id) == sha:
            result = step_id
    return result
