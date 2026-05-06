"""§2 State Schema — domain-agnostic optimization state.

Corresponds to PLANNING_AND_RL.md §2.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional, Protocol


@dataclass
class Artifact:
    """Single candidate artifact."""
    artifact_id: str
    content: Any
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactSet:
    """Collection of candidate artifacts with Pareto front tracking."""
    candidates: List[Artifact] = field(default_factory=list)
    pareto_front: List[Artifact] = field(default_factory=list)
    incumbent: Optional[Artifact] = None


@dataclass
class Observation:
    """Result of executing an action."""
    action_id: str
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Transition:
    """One step in the optimization trajectory."""
    action: Optional[Any] = None  # Action protocol (imported from action.py to avoid circular)
    observation: Optional[Observation] = None
    reward_contribution: dict[str, float] = field(default_factory=dict)
    cost: float = 0.0
    timestamp: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Knowledge:
    """Learned information accumulated during optimization."""
    ruled_out_regions: List[Any] = field(default_factory=list)
    calibration: dict[str, Any] = field(default_factory=dict)
    invariants: List[Any] = field(default_factory=list)
    surrogate_models: dict[str, Any] = field(default_factory=dict)


@dataclass
class State:
    """Optimization state X_t = (requirement, artifact, trajectory, knowledge)."""
    requirement: Any  # Domain-specific requirement spec
    artifact: ArtifactSet = field(default_factory=ArtifactSet)
    trajectory: List[Transition] = field(default_factory=list)
    knowledge: Knowledge = field(default_factory=Knowledge)

    def advance(self, action: Any, observation: Observation, reward_spec: Optional[Any] = None) -> "State":
        """Transition to next state by executing action and observing result (§1).

        Returns a new State with:
        - Updated trajectory (appended transition)
        - Updated artifact (new candidate added, pareto_front recomputed if possible)
        - Preserved knowledge (can be updated separately via learning)

        Args:
            action: The action that produced this transition
            observation: The observed result of the action
            reward_spec: Optional RewardSpec for incumbent comparison

        Returns:
            New State representing the transitioned state
        """
        from copy import deepcopy

        new_state = deepcopy(self)

        # Create the artifact from the action
        new_artifact = action.apply(new_state)

        # Store observation metrics in artifact metadata for Pareto/value calculations
        if observation.metrics:
            new_artifact.metadata["metrics"] = observation.metrics

        # Add to candidates if not already present
        if new_artifact.artifact_id not in [a.artifact_id for a in new_state.artifact.candidates]:
            new_state.artifact.candidates.append(new_artifact)

        # Update incumbent based on reward_spec or simple Pareto logic
        if observation.metrics:
            if new_state.artifact.incumbent is None:
                # First artifact becomes incumbent
                new_state.artifact.incumbent = new_artifact
            elif reward_spec:
                # Use reward spec to compare
                from optagent.legacy.v2.reward import RewardSpec
                if isinstance(reward_spec, RewardSpec):
                    incumbent_eval = reward_spec.evaluate(new_state, Observation(
                        action_id="incumbent",
                        metrics=new_state.artifact.incumbent.metadata.get("metrics", {}),
                    ))
                    new_artifact_eval = reward_spec.evaluate(new_state, observation)

                    # Update if new artifact is better (higher scalar reward)
                    if new_artifact_eval.aggregated_scalar > incumbent_eval.aggregated_scalar:
                        new_state.artifact.incumbent = new_artifact
            else:
                # Fall back to simple Pareto: prefer non-dominated solutions
                # For now, just keep the first incumbent (no update without reward_spec)
                pass

        # Append transition to trajectory
        transition = Transition(
            action=action,
            observation=observation,
            reward_contribution=observation.metrics,
            cost=action.cost(new_state),
            timestamp=len(new_state.trajectory),
        )
        new_state.trajectory.append(transition)

        return new_state


