"""Compatibility layer: v1.5 OptimizerState ↔ v2 State."""

from __future__ import annotations

from optagent.core.state_model import (
    OptimizerState as OptimizerStateV1,
    AlgorithmState,
    Requirements,
    EvidenceRecord,
)
from optagent.v2.state import State, ArtifactSet, Artifact, Transition, Knowledge, Observation


def state_v1_to_v2(optimizer_state: OptimizerStateV1) -> State:
    """Convert v1.5 OptimizerState to v2 State."""
    artifacts = [
        Artifact(artifact_id=a.hypothesis_id, content=a.to_dict())
        for a in optimizer_state.algorithm.hypotheses
    ]
    artifact_set = ArtifactSet(candidates=artifacts)

    trajectory = []
    for ev in optimizer_state.algorithm.evidence:
        trajectory.append(Transition(
            action=None,
            observation=Observation(
                action_id=ev.hypothesis_id,
                metrics={"speedup": ev.speedup or 0.0},
            ),
            reward_contribution={"speedup": ev.speedup or 0.0},
            cost=0.0,
        ))

    return State(
        requirement=optimizer_state.algorithm.requirements,
        artifact=artifact_set,
        trajectory=trajectory,
        knowledge=Knowledge(),
    )


def state_v2_to_v1(state: State) -> OptimizerStateV1:
    """Convert v2 State back to v1.5 OptimizerState."""
    requirements = state.requirement if isinstance(state.requirement, Requirements) else Requirements(
        target_type="unknown",
        target_id="unknown",
    )

    hypotheses = []
    evidence = []
    for t in state.trajectory:
        if t.observation:
            ev = EvidenceRecord(
                hypothesis_id=t.observation.action_id,
                artifact_id=t.observation.action_id,
                speedup=t.reward_contribution.get("speedup"),
            )
            evidence.append(ev)

    return OptimizerStateV1(
        algorithm=AlgorithmState(
            requirements=requirements,
            hypotheses=hypotheses,
            evidence=evidence,
            round_index=len(state.trajectory),
        )
    )
