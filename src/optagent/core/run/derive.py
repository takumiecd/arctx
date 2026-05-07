"""RunHandle.derive implementation."""

from __future__ import annotations

from optagent.core.schema.derived import DerivedRecord
from optagent.core.schema.transitions import ObservedTransition
from optagent.core.types import JSONValue


def derive_impl(
    self,
    transition_id: str,
    derived_type: str,
    payload: dict[str, JSONValue],
    *,
    derived_id: str | None = None,
    generator: str = "cli",
    confidence: float | None = None,
    user_id: str | None = None,
) -> DerivedRecord:
    """Attach a derived record to an observed transition.

    Parameters
    ----------
    transition_id:
        Identifier of the observed transition to annotate.
    derived_type:
        Type of derived record (e.g. ``"finding"``, ``"evidence"``,
        ``"decision"``, ``"observation"``, ``"prediction_error"``,
        ``"state_delta"``, ``"summary"``).
    payload:
        Key-value content for the derived record.
    derived_id:
        Optional explicit identifier.  If ``None``, one is generated
        automatically.
    generator:
        Label for the source that created the record.
    confidence:
        Optional confidence score in ``[0, 1]``.

    Returns
    -------
    The created :class:`DerivedRecord`.

    Raises
    ------
    KeyError
        If the *transition_id* does not exist in the trace DAG.
    """
    if transition_id not in self.trace_dag.transitions:
        raise KeyError(f"unknown transition_id: {transition_id}")

    record = DerivedRecord(
        derived_id=derived_id or self._next_id("d"),
        source_transition_id=transition_id,
        derived_type=derived_type,  # type: ignore[arg-type]
        payload=payload,
        generator=generator,
        confidence=confidence,
        metadata={"user_id": user_id} if user_id is not None else {},
    )

    old = self.trace_dag.transitions[transition_id]
    new = ObservedTransition(
        transition_id=old.transition_id,
        transition_kind=old.transition_kind,
        execution_plan_id=old.execution_plan_id,
        from_observed_state_id=old.from_observed_state_id,
        to_observed_state_id=old.to_observed_state_id,
        action_result=old.action_result,
        matched_predicted_transition_id=old.matched_predicted_transition_id,
        prediction_match=old.prediction_match,
        derived_records=old.derived_records + (record,),
        metadata=old.metadata,
    )
    self.trace_dag.transitions[transition_id] = new
    return record
