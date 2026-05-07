"""RunHandle.rewind implementation.

Rewind cuts a specific observed transition. The TraceDAG is left
otherwise untouched: states, transitions, plans, results, and derived
records all stay where they are. A single ``TraceCut`` record is
appended to mark the cut, and the current observed-state pointer
moves to the source of the cut transition.

Active vs cut membership is derived at read time from the cut log.
This is the only piece of state that grows; existing records are
never modified.
"""

from __future__ import annotations

from datetime import datetime, timezone

from optagent.core.schema.transitions import TraceCut


def rewind_impl(
    self,
    transition_id: str,
    *,
    reason: str | None = None,
) -> TraceCut:
    """Cut the observed transition *transition_id* and rewind to its source.

    The transition must be on the active path walking backward from
    the current observed state. After the call, ``current_observed_state_id``
    is set to ``transition.from_observed_state_id`` and the
    PredictionDAG is re-anchored there.

    Parameters
    ----------
    transition_id:
        Observed transition to cut.
    reason:
        Optional human-readable note. Persisted on the resulting
        :class:`TraceCut`.

    Returns
    -------
    The :class:`TraceCut` record that was appended to the TraceDAG.
    The new current observed state ID is available as
    ``cut.rewound_to_state_id``.

    Raises
    ------
    KeyError
        If the transition does not exist or is not an observed transition.
    ValueError
        If the transition is not on the active path from the current
        observed state, or if it has already been cut.

    Side effects
    ------------
    - Appends one ``TraceCut`` to ``trace_dag.cuts``.
    - Moves ``current_observed_state_id`` to the source of the cut.
    - Replaces ``prediction_dag`` with a fresh DAG anchored at the new
      current state.
    """
    transition = self.trace_dag.transitions.get(transition_id)
    if transition is None:
        raise KeyError(f"unknown observed transition_id: {transition_id}")

    if transition_id in self.trace_dag.cut_transition_ids():
        raise ValueError(f"transition already cut: {transition_id}")

    current = self.current_observed_state_id
    if not _is_on_active_path_back(self, transition_id=transition_id, from_state_id=current):
        raise ValueError(
            f"{transition_id} is not on the active path from {current}; "
            "rewind only cuts transitions reachable backwards from the current state."
        )

    cut = TraceCut(
        cut_id=self._next_id("cut"),
        cut_at=datetime.now(timezone.utc).isoformat(),
        rewound_to_state_id=transition.from_observed_state_id,
        cut_transition_id=transition_id,
        reason=reason,
    )
    self.trace_dag.add_cut(cut)

    self.current_observed_state_id = transition.from_observed_state_id
    self.refresh(from_state_id=transition.from_observed_state_id)
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
