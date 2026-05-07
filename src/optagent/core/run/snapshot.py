"""RunHandle.snapshot_rebuild implementation."""

from __future__ import annotations

from optagent.core.schema.state import (
    ArtifactRef,
    FindingRef,
    StateNode,
    StateSnapshot,
)


def snapshot_rebuild_impl(
    self,
    state_id: str,
) -> StateNode:
    """Rebuild the StateSnapshot for an observed state from its history.

    Walks backwards from *state_id* through observed transitions and
    regenerates the snapshot's ``artifacts`` and ``knowledge`` fields
    from ``ActionResult`` and ``DerivedRecord`` data.

    Parameters
    ----------
    state_id:
        Target observed state.

    Returns
    -------
    The updated :class:`StateNode` with a rebuilt snapshot.

    Raises
    ------
    KeyError
        If the state_id does not exist or is not an observed state.
    """
    if state_id not in self.trace_dag.nodes:
        raise KeyError(f"unknown state_id: {state_id}")

    target = self.trace_dag.nodes[state_id]
    if target.state_kind != "observed":
        raise KeyError(f"state_id is not observed: {state_id}")
    self._ensure_active_observed_state(state_id)

    artifacts: list[ArtifactRef] = []
    knowledge: list[FindingRef] = []

    cursor = state_id
    while True:
        incoming = self.trace_dag.past_transition_ids(cursor)
        if not incoming:
            break
        transition = self.trace_dag.transitions[incoming[-1]]
        result = transition.action_result

        for path in result.artifacts:
            artifacts.append(
                ArtifactRef(
                    artifact_id=path,
                    artifact_type="artifact",
                    path=path,
                )
            )
        for path in result.raw_outputs:
            artifacts.append(
                ArtifactRef(
                    artifact_id=path,
                    artifact_type="raw_output",
                    path=path,
                )
            )
        for path in result.logs:
            artifacts.append(
                ArtifactRef(
                    artifact_id=path,
                    artifact_type="log",
                    path=path,
                )
            )

        for record in transition.derived_records:
            if record.derived_type in ("finding", "summary", "evidence", "decision"):
                text = record.payload.get("text", "")
                summary = text if isinstance(text, str) else str(record.payload)
                knowledge.append(
                    FindingRef(
                        finding_id=record.derived_id,
                        summary=summary,
                        scope=record.derived_type,
                        metadata={"generator": record.generator},
                    )
                )

        cursor = transition.from_observed_state_id

    old_snap = target.snapshot
    new_snap = StateSnapshot(
        requirement=old_snap.requirement,
        artifacts=tuple(artifacts),
        knowledge=tuple(knowledge),
        open_questions=old_snap.open_questions,
        active_branches=old_snap.active_branches,
        predictions=old_snap.predictions,
        budget=old_snap.budget,
        metadata=old_snap.metadata,
    )

    new_node = StateNode(
        state_id=target.state_id,
        state_kind=target.state_kind,
        snapshot=new_snap,
        snapshot_hash=new_snap.compute_hash(),
        anchor_observed_state_id=target.anchor_observed_state_id,
        assumptions=target.assumptions,
        confidence=target.confidence,
        status=target.status,
        metadata=target.metadata,
    )
    self.trace_dag.nodes[state_id] = new_node
    return new_node
