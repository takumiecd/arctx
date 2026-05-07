"""RunHandle.rewind implementation.

Rewind moves the current observed-state pointer back to one of its
ancestors and re-anchors the PredictionDAG there. The TraceDAG itself
is append-only and is never modified by rewind: states, transitions,
plans, and results all remain in place. The new active path simply
diverges from the chosen ancestor on the next observe/promote.

Ancestor checks use incoming-edge traversal, not depth comparison, so
sibling branches at the same depth cannot be confused with the active
path.
"""

from __future__ import annotations

from optagent.core.schema.state import StateNode


def rewind_impl(
    self,
    to_state_id: str | None = None,
    *,
    steps: int | None = None,
    reason: str | None = None,
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
        Optional human-readable note. Returned in the result for the
        caller to log; not persisted in this step. Cursor events will
        capture this in a later iteration.

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

    moved = to_state_id != current
    self.current_observed_state_id = to_state_id
    if moved:
        self.refresh(from_state_id=to_state_id)
    return target
