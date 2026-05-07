"""RunHandle.state_show and state_update implementations."""

from __future__ import annotations

from optagent.core.schema.state import (
    ArtifactRef,
    FindingRef,
    PredictionRef,
    StateNode,
    StateSnapshot,
)


def state_show_impl(self, state_id: str) -> StateNode:
    """Return an observed state node."""
    state = self.trace_dag.nodes.get(state_id)
    if state is None or state.state_kind != "observed":
        raise KeyError(f"unknown observed state_id: {state_id}")
    return state


def state_update_impl(
    self,
    *,
    state_id: str,
    add_knowledge: list[str] | None = None,
    add_open_question: list[str] | None = None,
    add_artifact: list[tuple[str, str, str | None]] | None = None,
    add_prediction: list[tuple[str, str]] | None = None,
    add_branch: list[str] | None = None,
) -> StateNode:
    """Update an observed state's snapshot in place.

    Because :class:`StateNode` is immutable, this creates a replacement
    node with the same ``state_id`` but an updated :class:`StateSnapshot`
    and installs it back into ``trace_dag.nodes``.

    Parameters
    ----------
    add_knowledge:
        List of knowledge summary strings to append as :class:`FindingRef`.
    add_open_question:
        List of open-question strings to append.
    add_artifact:
        List of ``(artifact_id, artifact_type, path)`` tuples to append.
    add_prediction:
        List of ``(prediction_id, summary)`` tuples to append.
    add_branch:
        List of branch identifiers to append.

    Returns
    -------
    The updated :class:`StateNode`.
    """
    self._ensure_active_observed_state(state_id)
    old = self.trace_dag.nodes[state_id]
    old_snap = old.snapshot

    new_knowledge = list(old_snap.knowledge)
    for summary in add_knowledge or []:
        new_knowledge.append(
            FindingRef(
                finding_id=self._next_id("find"),
                summary=summary,
            )
        )

    new_open_questions = list(old_snap.open_questions)
    new_open_questions.extend(add_open_question or [])

    new_artifacts = list(old_snap.artifacts)
    for artifact_id, artifact_type, path in add_artifact or []:
        new_artifacts.append(
            ArtifactRef(
                artifact_id=artifact_id,
                artifact_type=artifact_type,
                path=path,
            )
        )

    new_predictions = list(old_snap.predictions)
    for prediction_id, summary in add_prediction or []:
        new_predictions.append(
            PredictionRef(
                prediction_id=prediction_id,
                summary=summary,
            )
        )

    new_branches = list(old_snap.active_branches)
    new_branches.extend(add_branch or [])

    new_snap = StateSnapshot(
        requirement=old_snap.requirement,
        artifacts=tuple(new_artifacts),
        knowledge=tuple(new_knowledge),
        open_questions=tuple(new_open_questions),
        active_branches=tuple(new_branches),
        predictions=tuple(new_predictions),
        budget=old_snap.budget,
        metadata=old_snap.metadata,
    )

    new_node = StateNode(
        state_id=old.state_id,
        state_kind=old.state_kind,
        snapshot=new_snap,
        snapshot_hash=old.snapshot_hash,
        anchor_observed_state_id=old.anchor_observed_state_id,
        assumptions=old.assumptions,
        confidence=old.confidence,
        status=old.status,
        metadata=old.metadata,
    )
    self.trace_dag.nodes[old.state_id] = new_node
    return new_node
