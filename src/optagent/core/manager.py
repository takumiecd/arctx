"""ManagerAgent - Orchestrator for optimization workflow.

Based on kernel_optimizer_architecture.md state model.

ManagerAgent does NOT implement everything itself. It:
1. Manages requirements, dispatch keys, baselines
2. Delegates to child agents via file-based protocol
3. Validates structured outputs (H, B, C)
4. Makes decisions via PromotionGate
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from optagent.core.state_model import (
    AlgorithmState,
    Artifact,
    EvidenceRecord,
    Hypothesis,
    OptimizerState,
    Requirements,
    RuntimeState,
    WorkItem,
)


class GuardrailError(Exception):
    """Guardrail violation - stop or retry."""
    pass


class PromotionGate:
    """Decides whether to promote a candidate based on evidence."""

    def decide(self, evidence: EvidenceRecord, requirements: Requirements) -> str:
        """Return one of: accepted, rejected, needs_narrower_scope, inconclusive."""
        if evidence.correctness != "passed":
            return "rejected"
        
        if not evidence.eligible:
            return "needs_narrower_scope"
        
        if evidence.regressions:
            return "needs_narrower_scope"
        
        min_speedup = requirements.objective.get("min_speedup", 1.05)
        if evidence.speedup is None or evidence.speedup < min_speedup:
            return "rejected"
        
        if requirements.promotion.get("require_dispatch_diagnosis", True):
            if not evidence.raw_output:
                return "inconclusive"
        
        return "accepted"


class ManagerAgent:
    """Orchestrates optimization using state model X_t = (R, H_<t, C_<t)."""

    def __init__(
        self,
        work_dir: str | Path,
        hypothesis_agent: Callable | None = None,
        artifact_builder: Callable | None = None,
        evaluator: Callable | None = None,
        analyzer: Callable | None = None,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        self.hypothesis_agent = hypothesis_agent
        self.artifact_builder = artifact_builder
        self.evaluator = evaluator
        self.analyzer = analyzer
        self.promotion_gate = PromotionGate()

    def optimize(self, requirements: Requirements) -> OptimizerState:
        """Run one optimization round.
        
        State transition: X_t -> X_{t+1}
        """
        # Initialize state
        state = OptimizerState(
            algorithm=AlgorithmState(requirements=requirements),
            work_dir=self.work_dir,
        )
        
        try:
            # Phase 1: Resolve targets and baselines
            self._resolve_targets(state)
            
            # Phase 2: Generate hypotheses (parallel possible)
            hypotheses = self._generate_hypotheses(state)
            state.algorithm.hypotheses.extend(hypotheses)
            
            # Phase 3: Review hypotheses
            approved = self._review_hypotheses(hypotheses, state)
            
            # Phase 4: Build artifacts (parallel possible with isolation)
            artifacts = self._build_artifacts(approved, state)
            
            # Phase 5: Evaluate artifacts
            evidence_list = self._evaluate_artifacts(artifacts, state)
            state.algorithm.evidence.extend(evidence_list)
            
            # Phase 6: Apply promotion gate
            decisions = self._apply_promotion_gate(evidence_list, requirements)
            
            # Phase 7: Analyze and decide next action
            analysis = self._analyze_results(state, decisions)
            
            # Save state
            self._save_state(state, analysis)
            
        except GuardrailError as e:
            self._save_state(state, {"error": str(e), "phase": "guardrail"})
            raise
        
        return state

    def _resolve_targets(self, state: OptimizerState) -> None:
        """Resolve dispatch targets and baselines.
        
        Guardrail: Must resolve before proceeding.
        """
        # This would integrate with kernel registry for kernel optimization
        # For now, record that we've attempted resolution
        state.runtime.queue.append(WorkItem(
            id="resolve_targets",
            phase="setup",
            status="done",
            metadata={"resolved": True},
        ))

    def _generate_hypotheses(self, state: OptimizerState) -> list[Hypothesis]:
        """Generate hypotheses using child agent.
        
        H_t = propose(R, H_<t, C_<t)
        """
        if self.hypothesis_agent is None:
            # Default: single basic hypothesis
            return [Hypothesis(
                id=f"h_{state.algorithm.round_index}_default",
                claim="Default optimization hypothesis",
                proposed_change="Apply standard optimizations",
                expected_effect="Improve performance for target conditions",
            )]
        
        # File-based protocol
        request_path = self.work_dir / f"request_hypothesis_{state.algorithm.round_index}.json"
        request = {
            "requirements": state.algorithm.requirements.to_dict(),
            "prior_hypotheses": [h.to_dict() for h in state.algorithm.hypotheses],
            "prior_evidence": [e.to_dict() for e in state.algorithm.evidence],
        }
        request_path.write_text(json.dumps(request, indent=2))
        
        # Call child agent
        response = self.hypothesis_agent(request_path)
        
        # Parse structured response
        hypotheses = self._parse_hypotheses(response)
        
        # Guardrail: Check hypotheses relate to target
        for h in hypotheses:
            if not self._hypothesis_relates_to_target(h, state.algorithm.requirements):
                raise GuardrailError(f"Hypothesis {h.id} does not relate to target")
        
        return hypotheses

    def _review_hypotheses(self, hypotheses: list[Hypothesis], state: OptimizerState) -> list[Hypothesis]:
        """Validate and approve hypotheses.
        
        Guardrail: Expected effect must be measurable.
        """
        approved = []
        for h in hypotheses:
            if not h.expected_effect:
                raise GuardrailError(f"Hypothesis {h.id} has no measurable expected_effect")
            approved.append(h)
        return approved

    def _build_artifacts(self, hypotheses: list[Hypothesis], state: OptimizerState) -> list[Artifact]:
        """Build isolated artifacts from approved hypotheses.
        
        B_t = materialize(H_t)
        """
        if self.artifact_builder is None:
            # Default mock artifact
            return [
                Artifact(
                    hypothesis_id=h.id,
                    artifact_type="mock",
                    registry_policy="declare_only",
                )
                for h in hypotheses
            ]
        
        artifacts = []
        for h in hypotheses:
            # File-based protocol
            request_path = self.work_dir / f"request_artifact_{h.id}.json"
            request = {
                "hypothesis": h.to_dict(),
                "requirements": state.algorithm.requirements.to_dict(),
            }
            request_path.write_text(json.dumps(request, indent=2))
            
            response = self.artifact_builder(request_path)
            artifact = self._parse_artifact(response)
            
            # Guardrail: Check for unexpected file changes
            if artifact.registry_policy == "publish":
                raise GuardrailError(
                    f"Artifact {artifact.hypothesis_id} uses publish before promotion"
                )
            
            artifacts.append(artifact)
        
        return artifacts

    def _evaluate_artifacts(self, artifacts: list[Artifact], state: OptimizerState) -> list[EvidenceRecord]:
        """Evaluate artifacts against baselines.
        
        C_t = evaluate(B_t, R)
        """
        if self.evaluator is None:
            # Default mock evidence
            return [
                EvidenceRecord(
                    hypothesis_id=a.hypothesis_id,
                    artifact_id=a.artifact_type,
                    correctness="passed",
                    eligible=True,
                    speedup=1.0,
                )
                for a in artifacts
            ]
        
        evidence_list = []
        for artifact in artifacts:
            request_path = self.work_dir / f"request_eval_{artifact.hypothesis_id}.json"
            request = {
                "artifact": artifact.to_dict(),
                "requirements": state.algorithm.requirements.to_dict(),
            }
            request_path.write_text(json.dumps(request, indent=2))
            
            response = self.evaluator(request_path)
            evidence = self._parse_evidence(response)
            
            # Guardrail: Evidence must have dispatch keys
            if not evidence.dispatch_keys:
                raise GuardrailError(f"Evidence {evidence.hypothesis_id} missing dispatch_keys")
            
            evidence_list.append(evidence)
        
        return evidence_list

    def _apply_promotion_gate(self, evidence_list: list[EvidenceRecord], requirements: Requirements) -> list[str]:
        """Apply promotion gate to evidence.
        
        D_t = decide(C_t, R)
        """
        decisions = []
        for evidence in evidence_list:
            decision = self.promotion_gate.decide(evidence, requirements)
            evidence.decision_recommendation = decision
            decisions.append(decision)
        return decisions

    def _analyze_results(self, state: OptimizerState, decisions: list[str]) -> dict[str, Any]:
        """Analyze results and recommend next action."""
        if self.analyzer is None:
            return {"decisions": decisions, "converged": False}
        
        request = {
            "state": state.to_dict(),
            "decisions": decisions,
        }
        return self.analyzer(request)

    def _save_state(self, state: OptimizerState, analysis: dict[str, Any]) -> None:
        """Save state to disk for resume."""
        state_path = self.work_dir / f"state_round_{state.algorithm.round_index}.json"
        state_data = {
            "algorithm": state.algorithm.to_dict(),
            "analysis": analysis,
            "timestamp": time.time(),
        }
        state_path.write_text(json.dumps(state_data, indent=2, default=str))

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_hypotheses(path: Path) -> list[Hypothesis]:
        """Parse structured hypothesis response."""
        data = json.loads(path.read_text())
        if isinstance(data, list):
            return [Hypothesis(**h) for h in data]
        return [Hypothesis(**data)]

    @staticmethod
    def _parse_artifact(path: Path) -> Artifact:
        """Parse structured artifact response."""
        data = json.loads(path.read_text())
        return Artifact(**data)

    @staticmethod
    def _parse_evidence(path: Path) -> EvidenceRecord:
        """Parse structured evidence response."""
        data = json.loads(path.read_text())
        return EvidenceRecord(**data)

    @staticmethod
    def _hypothesis_relates_to_target(h: Hypothesis, requirements: Requirements) -> bool:
        """Check if hypothesis relates to target requirements."""
        if not h.target_keys:
            return True  # No target keys means general hypothesis
        # Check if target_keys overlap with requirements
        target_id = requirements.target_id
        return any(target_id in key for key in h.target_keys)
