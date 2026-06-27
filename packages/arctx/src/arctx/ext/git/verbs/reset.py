"""RunHandle.git.reset implementation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from arctx.core.cuts import cut_step_ids
from arctx.core.schema.work_helpers import (
    latest_lane_pointer,
    make_lane_pointer_event,
)
from arctx.ext.git.events import make_reset_event
from arctx.ext.git.helpers.repo import resolve_worktree_path
from arctx.ext.git.queries import current_sha, step_by_sha

if TYPE_CHECKING:
    from arctx.core.run.handle import RunHandle


def _compute_discarded_step_ids(
    graph,
    from_node_id: str,
    to_node_id: str,
) -> tuple[str, ...]:
    if from_node_id == to_node_id:
        return ()

    ancestors_of_from = graph.ancestors_of(from_node_id) | {from_node_id}
    ancestors_of_to = graph.ancestors_of(to_node_id) | {to_node_id}

    if to_node_id not in ancestors_of_from:
        raise ValueError(
            f"to_node_id {to_node_id!r} is not an ancestor of "
            f"from_node_id {from_node_id!r}; reset requires a backwards move"
        )

    discarded_nodes = ancestors_of_from - ancestors_of_to

    discarded_t_ids: list[str] = []
    for t_id, step in graph.steps.items():
        if step.output_node_id in discarded_nodes:
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
    lane_id: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Reset to a past node. Does NOT create a new Step."""
    if to_node_id is None and to_sha is None:
        raise ValueError("Either to_node_id or to_sha must be provided")
    if to_node_id is not None and to_sha is not None:
        raise ValueError("to_node_id and to_sha are mutually exclusive")

    graph = self.run_graph
    resolved_repo_path = resolve_worktree_path(repo_path)

    if to_sha is not None:
        t_id = step_by_sha(graph, to_sha)
        if t_id is None:
            raise KeyError(f"no arctx step found for sha {to_sha!r}")
        step = graph.steps[t_id]
        to_node_id = step.output_node_id

    if to_node_id not in graph.nodes:
        raise KeyError(f"unknown node_id: {to_node_id!r}")

    from_node_id: str
    if lane_id is not None:
        sp = latest_lane_pointer(graph, lane_id)
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

    discarded_step_ids = _compute_discarded_step_ids(
        graph, from_node_id, to_node_id
    )

    target_sha: str | None = None
    incoming_t_id = graph.step_to_node(to_node_id)
    if incoming_t_id is not None:
        target_sha = current_sha(graph, incoming_t_id)

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

    current_branch: str | None = branch
    if current_branch is None and lane_id is not None:
        sp = latest_lane_pointer(graph, lane_id)
        if sp is not None:
            current_branch = sp.data.get("current_branch")

    event_id: str | None = None
    if user_id is not None and lane_id is not None:
        self.ensure_lane(user_id=user_id, lane_id=lane_id)

        reset_event = make_reset_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            lane_id=lane_id,
            user_id=user_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            mode=mode,
            discarded_step_ids=discarded_step_ids,
        )
        graph.add_work_event(reset_event)
        event_id = reset_event.event_id

        sp_event = make_lane_pointer_event(
            event_id=self._next_id("we"),
            run_id=self.run_id,
            lane_id=lane_id,
            user_id=user_id,
            current_node_ids=(to_node_id,),
            current_branch=current_branch,
        )
        graph.add_work_event(sp_event)

    if mode == "hard":
        already_cut = cut_step_ids(graph)
        for t_id in discarded_step_ids:
            if t_id in already_cut:
                continue
            from arctx.core.schema.payloads import CutPayload  # noqa: PLC0415
            cut = CutPayload(
                payload_id=self._next_id("pl"),
                target_id=t_id,
                target_kind="step",
                reason=f"discarded by reset to {to_node_id}",
            )
            graph.attach_payload(cut)

    return {
        "to_node_id": to_node_id,
        "from_node_id": from_node_id,
        "discarded_step_ids": list(discarded_step_ids),
        "mode": mode,
        "event_id": event_id,
    }
