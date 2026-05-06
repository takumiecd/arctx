"""Compatibility layer: v1.5 OptimizerState ↔ v2 State (§15)."""

from __future__ import annotations

from optagent.legacy.v1.core.state_model import (
    OptimizerState as OptimizerStateV1,
    AlgorithmState,
    Requirements,
    EvidenceRecord,
)
from optagent.legacy.v2.state import State, ArtifactSet, Artifact, Transition, Knowledge, Observation
from optagent.legacy.v2.action import ApplyHypothesis


def state_v1_to_v2(optimizer_state: OptimizerStateV1) -> State:
    """Convert v1.5 OptimizerState to v2 State, preserving hypothesis info as Actions (§15)."""
    artifacts = [
        Artifact(artifact_id=a.hypothesis_id, content=a.to_dict())
        for a in optimizer_state.algorithm.hypotheses
    ]
    artifact_set = ArtifactSet(candidates=artifacts)

    trajectory = []
    for ev in optimizer_state.algorithm.evidence:
        # Convert hypothesis to ApplyHypothesis action (§15)
        action = ApplyHypothesis(
            hypothesis_id=ev.hypothesis_id,
            hypothesis_content=ev.hypothesis_id,  # Placeholder; real content from hypothesis
        )

        trajectory.append(Transition(
            action=action,  # Now preserved, not None (§15)
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
    """Convert v2 State back to v1.5 OptimizerState, reconstructing hypotheses from Actions (§15)."""
    requirements = state.requirement if isinstance(state.requirement, Requirements) else Requirements(
        target_type="unknown",
        target_id="unknown",
    )

    hypotheses = []
    evidence = []
    for t in state.trajectory:
        # Reconstruct hypothesis from action if available (§15)
        hypothesis_id = None
        if t.action and isinstance(t.action, ApplyHypothesis):
            hypothesis_id = t.action.hypothesis_id
        elif t.observation:
            hypothesis_id = t.observation.action_id

        if hypothesis_id:
            ev = EvidenceRecord(
                hypothesis_id=hypothesis_id,
                artifact_id=hypothesis_id,
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
