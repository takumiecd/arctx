"""RunHandle.reset implementation.

Reset rolls back the session pointer to a past node WITHOUT creating a new
Transition or Node (analogous to ``git reset`` which moves HEAD without making
a commit).

Per REDESIGN §10.3:
- Append ResetEvent (WorkEvent)
- Append SessionPointerEvent with to_node_id as the new current
- For mode="hard" only: attach CutPayload to each discarded transition
- Run ``git reset --<mode> <sha>`` (unless dry_run=True)
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from stag.core.cuts import cut_transition_ids
from stag.core.schema.work_helpers import (
    latest_session_pointer,
    make_reset_event,
    make_session_pointer_event,
)

if TYPE_CHECKING:
    from stag.core.run.handle import RunHandle


def _compute_discarded_transition_ids(
    graph,
    from_node_id: str,
    to_node_id: str,
) -> tuple[str, ...]:
    """Return transition IDs on the path from to_node_id up to from_node_id.

    Strategy: walk backwards from from_node_id via transition_by_output_node
    until we reach to_node_id. Collect each transition encountered along the
    way. The transition whose output_node_id is to_node_id is NOT included
    (to_node stays active). The transitions whose output_node_id is from_node_id
    or an intermediate node IS included.

    Raises ValueError if to_node_id is not an ancestor of from_node_id (or
    equal to it).
    """
    # to_node_id must be an ancestor of from_node_id OR be from_node_id itself.
    # If to_node == from_node, there's nothing to discard.
    if from_node_id == to_node_id:
        return ()

    ancestors_of_from = graph.ancestors_of(from_node_id) | {from_node_id}
    ancestors_of_to = graph.ancestors_of(to_node_id) | {to_node_id}

    if to_node_id not in ancestors_of_from:
        raise ValueError(
            f"to_node_id {to_node_id!r} is not an ancestor of "
            f"from_node_id {from_node_id!r}; reset requires a backwards move"
        )

    # Nodes that are in from's ancestry but not in to's ancestry
    # (excluding to_node itself) are the "discarded" node range.
    discarded_nodes = ancestors_of_from - ancestors_of_to

    discarded_t_ids: list[str] = []
    for t_id, transition in graph.transitions.items():
        if transition.output_node_id in discarded_nodes:
            discarded_t_ids.append(t_id)

    return tuple(discarded_t_ids)


def reset_impl(
    self: "RunHandle",
    *,
    to_node_id: str | None = None,
    to_sha: str | None = None,
    mode: Literal["hard", "mixed", "soft"] = "hard",
    branch: str | None = None,
    repo_path: Path | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Reset to a past node. Does NOT create a new Transition.

    Steps (per REDESIGN §10.3):
    1. Resolve to_node_id (from arg or via transition_by_sha + output_node lookup).
    2. Resolve from_node_id from the latest SessionPointerEvent for the session.
       Falls back to root_node_id if no SessionPointerEvent exists.
    3. Validate that to_node_id is an ancestor of from_node_id.
    4. Compute discarded_transition_ids: transitions whose output_node_id lies
       strictly between from_node_id and to_node_id on the backwards path.
    5. Run ``git reset --<mode> <sha>`` (unless dry_run=True).
       The sha is derived from the latest GitChangePayload on the transition
       whose output_node_id == to_node_id, if available.
    6. Append ResetEvent(from_node_id, to_node_id, mode, discarded_transition_ids).
    7. Append SessionPointerEvent(current_node_ids=(to_node_id,), current_branch=...).
    8. If mode == "hard": attach CutPayload to each discarded transition (skip
       already-cut transitions silently).

    Parameters
    ----------
    to_node_id:
        Target node to reset to. Mutually exclusive with to_sha.
    to_sha:
        Commit SHA to reset to; looked up via RunGraph.transition_by_sha to
        find the associated transition, then uses its output_node_id.
    mode:
        "hard" | "mixed" | "soft". Only "hard" attaches CutPayloads.
    branch:
        Override the current branch name for the SessionPointerEvent.
        If None, inherited from the latest SessionPointerEvent.
    repo_path:
        Path to the git repository root. Defaults to cwd.
    user_id:
        User ID for attribution. If None, work events are not recorded.
    work_session_id:
        Work session ID. If None, work events are not recorded.
    dry_run:
        If True, skip the actual ``git reset`` call.

    Returns
    -------
    dict with keys: to_node_id, from_node_id, discarded_transition_ids,
    mode, event_id (or None if no work events recorded).
    """
    if to_node_id is None and to_sha is None:
        raise ValueError("Either to_node_id or to_sha must be provided")
    if to_node_id is not None and to_sha is not None:
        raise ValueError("to_node_id and to_sha are mutually exclusive")

    graph = self.run_graph
    resolved_repo_path = repo_path or Path.cwd()

    # ------------------------------------------------------------------
    # 1. Resolve to_node_id.
    # ------------------------------------------------------------------
    if to_sha is not None:
        # transition_by_sha scans payloads for GitChangePayload with that sha.
        t_id = graph.transition_by_sha(to_sha)
        if t_id is None:
            raise KeyError(f"no stag transition found for sha {to_sha!r}")
        transition = graph.transitions[t_id]
        to_node_id = transition.output_node_id

    if to_node_id not in graph.nodes:
        raise KeyError(f"unknown node_id: {to_node_id!r}")

    # ------------------------------------------------------------------
    # 2. Resolve from_node_id.
    # ------------------------------------------------------------------
    from_node_id: str
    if work_session_id is not None:
        sp = latest_session_pointer(graph, work_session_id)
        if sp is not None:
            raw = sp.data.get("current_node_ids") or []
            ids = [str(n) for n in raw]
            if ids:
                from_node_id = ids[0]
            else:
                from_node_id = self.root_node_id
        else:
            from_node_id = self.root_node_id
    else:
        from_node_id = self.root_node_id

    # ------------------------------------------------------------------
    # 3. Validate + compute discarded transitions.
    # ------------------------------------------------------------------
    discarded_transition_ids = _compute_discarded_transition_ids(
        graph, from_node_id, to_node_id
    )

    # ------------------------------------------------------------------
    # 4. Resolve the git sha for to_node_id (needed for git reset).
    # ------------------------------------------------------------------
    target_sha: str | None = None
    incoming_t_id = graph.transition_by_output_node.get(to_node_id)
    if incoming_t_id is not None:
        target_sha = graph.current_sha(incoming_t_id)

    # ------------------------------------------------------------------
    # 5. Run git reset (unless dry_run).
    # ------------------------------------------------------------------
    if not dry_run and target_sha is not None:
        result = subprocess.run(
            ["git", "reset", f"--{mode}", target_sha],
            cwd=str(resolved_repo_path),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                ["git", "reset", f"--{mode}", target_sha],
                result.stdout,
                result.stderr,
            )

    # ------------------------------------------------------------------
    # 6. Resolve current_branch for SessionPointerEvent.
    # ------------------------------------------------------------------
    current_branch: str | None = branch
    if current_branch is None and work_session_id is not None:
        sp = latest_session_pointer(graph, work_session_id)
        if sp is not None:
            current_branch = sp.data.get("current_branch")

    # ------------------------------------------------------------------
    # 7. Ensure work session.
    # ------------------------------------------------------------------
    event_id: str | None = None
    if user_id is not None and work_session_id is not None:
        self.ensure_work_session(user_id=user_id, work_session_id=work_session_id)

        # Append ResetEvent.
        reset_event = make_reset_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            work_session_id=work_session_id,
            user_id=user_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            mode=mode,
            discarded_transition_ids=discarded_transition_ids,
        )
        graph.add_work_event(reset_event)
        event_id = reset_event.event_id

        # Append SessionPointerEvent.
        sp_event = make_session_pointer_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            work_session_id=work_session_id,
            user_id=user_id,
            current_node_ids=(to_node_id,),
            current_branch=current_branch,
        )
        graph.add_work_event(sp_event)

    # ------------------------------------------------------------------
    # 8. CutPayload for discarded transitions (hard only).
    # ------------------------------------------------------------------
    if mode == "hard":
        already_cut = cut_transition_ids(graph)
        for t_id in discarded_transition_ids:
            if t_id in already_cut:
                continue
            from stag.core.schema.payloads import CutPayload  # noqa: PLC0415
            cut = CutPayload(
                payload_id=self._next_id("pl"),
                target_id=t_id,
                target_kind="transition",
                reason=f"discarded by reset to {to_node_id}",
            )
            graph.attach_payload(cut)

    return {
        "to_node_id": to_node_id,
        "from_node_id": from_node_id,
        "discarded_transition_ids": list(discarded_transition_ids),
        "mode": mode,
        "event_id": event_id,
    }
