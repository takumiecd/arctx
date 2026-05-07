"""RunHandle.rewind implementation."""

from __future__ import annotations

from datetime import datetime, timezone

from optagent.core.schema.transitions import TraceCut


def rewind_impl(
    self,
    transition_id: str,
    *,
    from_state_id: str,
    reason: str | None = None,
    user_id: str | None = None,
) -> TraceCut:
    """Append a cut event for an observed transition.

    ``from_state_id`` is the explicit validation point. The target
    transition must be reachable by walking backward from it along
    active incoming edges.
    """
    transition = self.trace_dag.transitions.get(transition_id)
    if transition is None:
        raise KeyError(f"unknown observed transition_id: {transition_id}")

    if transition_id in self.trace_dag.cut_transition_ids():
        raise ValueError(f"transition already cut: {transition_id}")

    self._ensure_active_observed_state(from_state_id)
    if not _is_on_active_path_back(
        self, transition_id=transition_id, from_state_id=from_state_id
    ):
        raise ValueError(
            f"{transition_id} is not on the active path from {from_state_id}; "
            "rewind only cuts transitions reachable backwards from from_state_id."
        )

    cut = TraceCut(
        cut_id=self._next_id("cut"),
        cut_at=datetime.now(timezone.utc).isoformat(),
        rewound_to_state_id=transition.from_observed_state_id,
        cut_transition_id=transition_id,
        reason=reason,
        user_id=user_id,
    )
    self.trace_dag.add_cut(cut)
    return cut


def _is_on_active_path_back(self, *, transition_id: str, from_state_id: str) -> bool:
    """Walk backwards from *from_state_id* via active incoming edges.

    Already-cut transitions are skipped: an edge that has been cut is
    no longer part of any active path, so the walk must not cross it
    when deciding whether *transition_id* is reachable.
    """
    cut_tids = self.trace_dag.cut_transition_ids()
    seen: set[str] = set()
    frontier: list[str] = [from_state_id]
    while frontier:
        sid = frontier.pop()
        if sid in seen:
            continue
        seen.add(sid)
        for tid in self.trace_dag.past_transition_ids(sid):
            if tid in cut_tids:
                continue
            if tid == transition_id:
                return True
            frontier.append(self.trace_dag.transitions[tid].from_observed_state_id)
    return False
