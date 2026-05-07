"""RunHandle.rewind implementation.

Rewind moves the current observed-state pointer back to one of its
ancestors and re-anchors the PredictionDAG there. It also appends a
``TraceCut`` record to the TraceDAG marking the outgoing transition
from the ancestor that led to the now-abandoned subtree.

The TraceDAG records themselves (states, transitions, plans, results,
derived records) are never modified or deleted. The cut log is the
only piece of state that grows, and it is append-only. Active vs cut
membership is derived at read time from the cut log; this lets the DAG
remain a faithful audit of what was tried while consumers can filter
to the live subset.

Ancestor checks use incoming-edge traversal, not depth comparison, so
sibling branches at the same depth cannot be confused with the active
path.
"""

from __future__ import annotations

from datetime import datetime, timezone

from optagent.core.schema.state import StateNode
from optagent.core.schema.transitions import TraceCut


def rewind_impl(
    self,
    to_state_id: str | None = None,
    *,
    steps: int | None = None,
    reason: str | None = None,
    actor_id: str | None = None,
) -> StateNode:
    """Move ``current_observed_state_id`` back to an ancestor.

    Exactly one of *to_state_id* and *steps* must be provided.

    Parameters
    ----------
    to_state_id:
        Target observed state. Must be an ancestor of (or equal to) the
        current observed state.
    steps:
        Walk *steps* incoming transitions from the current state and
        rewind to the resulting ancestor.
    reason:
        Optional human-readable note. Persisted on the resulting
        :class:`TraceCut` for audit.
    actor_id:
        Optional actor that triggered the rewind. Forward-compat slot
        for the cursor/actor model; persisted on the cut record.

    Returns
    -------
    The :class:`StateNode` now pointed to by ``current_observed_state_id``.

    Raises
    ------
    ValueError
        If neither or both of *to_state_id*/*steps* are given, if
        *steps* is non-positive or walks past the root, or if
        *to_state_id* is not an ancestor of the current state.
    KeyError
        If *to_state_id* does not exist or is not an observed state.

    Side effects
    ------------
    - Appends one ``TraceCut`` to ``trace_dag.cuts`` (skipped when
      target equals current — a self-rewind has no edge to cut).
    - Replaces ``prediction_dag`` with a fresh DAG anchored at the new
      current state (skipped on self-rewind).
    """
    if (to_state_id is None) == (steps is None):
        raise ValueError("rewind requires exactly one of to_state_id or steps")

    current = self.current_observed_state_id

    if steps is not None:
        if steps < 1:
            raise ValueError(f"steps must be >= 1, got {steps}")
        cursor = current
        for _ in range(steps):
            incoming = self.trace_dag.past_transition_ids(cursor)
            if not incoming:
                raise ValueError(
                    f"cannot rewind {steps} step(s) from {current}: "
                    f"hit trace root at {cursor}"
                )
            cursor = self.trace_dag.transitions[incoming[-1]].from_observed_state_id
        to_state_id = cursor

    target = self.trace_dag.nodes.get(to_state_id)
    if target is None:
        raise KeyError(f"unknown state_id: {to_state_id}")
    if target.state_kind != "observed":
        raise KeyError(f"not an observed state: {to_state_id}")

    if not self.trace_dag.is_ancestor(to_state_id, current):
        raise ValueError(
            f"{to_state_id} is not an ancestor of {current}; "
            "rewind only walks the active path. Use a switch/move "
            "operation to move to a sibling branch."
        )

    if to_state_id == current:
        return target

    cut_transition_id = _find_cut_edge(self, target_id=to_state_id, current_id=current)
    cut = TraceCut(
        cut_id=self._next_id("cut"),
        cut_at=datetime.now(timezone.utc).isoformat(),
        rewound_to_state_id=to_state_id,
        cut_transition_id=cut_transition_id,
        reason=reason,
        actor_id=actor_id,
    )
    self.trace_dag.add_cut(cut)

    self.current_observed_state_id = to_state_id
    self.refresh(from_state_id=to_state_id)
    return target


def _find_cut_edge(self, *, target_id: str, current_id: str) -> str:
    """Walk backwards from ``current_id`` until landing on ``target_id``.

    The transition whose ``from_observed_state_id`` is *target_id* is
    the immediate downstream edge from the rewind target — that's what
    gets recorded as cut. Cuts to ancestors further back simply name
    the corresponding edge for that hop; downstream states are still
    derived as cut because they sit forward of this edge.
    """
    cursor = current_id
    last_transition_id: str | None = None
    while cursor != target_id:
        incoming = self.trace_dag.past_transition_ids(cursor)
        if not incoming:
            raise ValueError(
                f"{target_id} not reachable from {current_id} via incoming edges"
            )
        transition = self.trace_dag.transitions[incoming[-1]]
        last_transition_id = transition.transition_id
        cursor = transition.from_observed_state_id
    if last_transition_id is None:
        raise ValueError(
            f"no edge to cut between {target_id} and {current_id}"
        )
    return last_transition_id
