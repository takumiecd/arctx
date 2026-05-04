"""ManagerAgent - Generalized optimization orchestrator."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from optagent.core.models import (
    Artifact,
    Decision,
    Evidence,
    Hypothesis,
    OptimizationConfig,
    Requirement,
)
from optagent.core.state import OptimizationState
from optagent.core.workflow import Workflow, WorkflowStep


class ManagerAgent:
    """Orchestrates optimization workflows across any domain.
    
    The ManagerAgent is strategy-agnostic. It delegates domain-specific
    work to pluggable components:
    - Strategy: Defines how to analyze targets, generate hypotheses, etc.
    - Backend: LLM or other optimization provider
    - Evaluator: Measures performance of artifacts
    """

    def __init__(
        self,
        strategy: Any,
        backend: Any,
        evaluator: Any,
        config: OptimizationConfig | None = None,
        work_dir: str | Path = ".optagent",
    ) -> None:
        self.strategy = strategy
        self.backend = backend
        self.evaluator = evaluator
        self.config = config or OptimizationConfig()
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        self.workflow = Workflow()
        self._register_default_hooks()

    def optimize(
        self,
        requirement: Requirement,
        state: OptimizationState | None = None,
    ) -> OptimizationState:
        """Run one full optimization round.
        
        If state is provided, it is resumed (round_index is incremented).
        """
        if state is None:
            state = OptimizationState()
        
        state.round_index += 1
        state.requirement = requirement
        state.work_dir = self.work_dir

        try:
            # Execute workflow steps
            context = {"state": state, "config": self.config}
            
            for step in self.workflow.get_default_steps():
                context = self.workflow.execute_step(step, context)
            
        finally:
            # Always save state
            self._save_state(state)

        return state

    def _register_default_hooks(self) -> None:
        """Register default workflow hooks."""
        self.workflow.register_hook(WorkflowStep.INITIALIZE, self._hook_initialize)
        self.workflow.register_hook(WorkflowStep.ANALYZE_TARGET, self._hook_analyze)
        self.workflow.register_hook(WorkflowStep.PROPOSE_HYPOTHESES, self._hook_propose)
        self.workflow.register_hook(WorkflowStep.GENERATE_ARTIFACTS, self._hook_generate)
        self.workflow.register_hook(WorkflowStep.EVALUATE_ARTIFACTS, self._hook_evaluate)
        self.workflow.register_hook(WorkflowStep.VALIDATE_RESULTS, self._hook_validate)
        self.workflow.register_hook(WorkflowStep.MAKE_DECISION, self._hook_decide)
        self.workflow.register_hook(WorkflowStep.FINALIZE, self._hook_finalize)

    # ------------------------------------------------------------------
    # Default hooks
    # ------------------------------------------------------------------

    def _hook_initialize(self, context: dict[str, Any]) -> dict[str, Any]:
        """Initialize optimization context."""
        state = context["state"]
        self.strategy.initialize(state)
        return context

    def _hook_analyze(self, context: dict[str, Any]) -> dict[str, Any]:
        """Analyze optimization target."""
        state = context["state"]
        analysis = self.strategy.analyze(state.requirement)
        context["analysis"] = analysis
        return context

    def _hook_propose(self, context: dict[str, Any]) -> dict[str, Any]:
        """Propose optimization hypotheses."""
        state = context["state"]
        analysis = context.get("analysis", {})
        
        hypotheses = self.backend.propose_hypotheses(state, analysis)
        state.hypotheses.extend(hypotheses)
        context["hypotheses"] = hypotheses
        return context

    def _hook_generate(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate artifacts from hypotheses."""
        state = context["state"]
        hypotheses = context.get("hypotheses", [])
        
        artifacts: list[Artifact] = []
        for hypothesis in hypotheses:
            artifact = self.backend.generate_artifact(hypothesis, state)
            artifacts.append(artifact)
        
        state.artifacts.extend(artifacts)
        context["artifacts"] = artifacts
        return context

    def _hook_evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
        """Evaluate generated artifacts."""
        state = context["state"]
        artifacts = context.get("artifacts", [])
        
        evidence_list: list[Evidence] = []
        for artifact in artifacts:
            evidence = self.evaluator.evaluate(artifact, state)
            evidence_list.append(evidence)
        
        state.evidence.extend(evidence_list)
        context["evidence"] = evidence_list
        return context

    def _hook_validate(self, context: dict[str, Any]) -> dict[str, Any]:
        """Validate evaluation results."""
        state = context["state"]
        evidence_list = context.get("evidence", [])
        
        for evidence in evidence_list:
            if self.config.require_correctness and not evidence.is_correct:
                context["validation_failed"] = True
                break
        
        return context

    def _hook_decide(self, context: dict[str, Any]) -> dict[str, Any]:
        """Make final optimization decision."""
        state = context["state"]
        evidence_list = context.get("evidence", [])
        
        if context.get("validation_failed"):
            decision = Decision(
                round_index=state.round_index,
                accepted=False,
                reason="Validation failed: some artifacts were incorrect",
            )
        else:
            # Find best speedup
            best_speedup = None
            best_artifact = None
            for evidence in evidence_list:
                if evidence.speedup is not None:
                    if best_speedup is None or evidence.speedup > best_speedup:
                        best_speedup = evidence.speedup
                        best_artifact = evidence
            
            if best_speedup and best_speedup >= self.config.target_speedup:
                decision = Decision(
                    round_index=state.round_index,
                    accepted=True,
                    reason=f"Best speedup: {best_speedup:.2f}x",
                    promoted=(best_artifact.artifact_id,) if best_artifact else (),
                )
            else:
                best_str = f"{best_speedup:.2f}x" if best_speedup is not None else "N/A"
                decision = Decision(
                    round_index=state.round_index,
                    accepted=False,
                    reason=f"No sufficient improvement (best: {best_str}, target: {self.config.target_speedup}x)",
                )
        
        state.decisions.append(decision)
        context["decision"] = decision
        return context

    def _hook_finalize(self, context: dict[str, Any]) -> dict[str, Any]:
        """Finalize optimization round."""
        state = context["state"]
        decision = context.get("decision")
        
        if decision and decision.accepted and self.config.allow_promotion:
            self.strategy.apply_changes(state)
        
        return context

    def _save_state(self, state: OptimizationState) -> None:
        """Persist state to work_dir."""
        if state.work_dir:
            path = state.work_dir / f"state_round_{state.round_index}.json"
            state.to_file(path)
