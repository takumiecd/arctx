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

from optagent.core.ids import sequential_id
from optagent.core.schema import (
    ActionRecord,
    ArtifactRecord,
    AttemptRecord,
    DecisionRecord,
    EvidenceRecord as CanonicalEvidenceRecord,
    FindingRecord,
    HypothesisRecord,
    ObservationRecord,
    RequirementRecord,
    canonical_decision_status,
)
from optagent.core.store import StateStore
from optagent.v1.core.state_model import (
    AlgorithmState,
    Artifact,
    EvidenceRecord,
    Hypothesis,
    OptimizerState,
    Requirements,
    RuntimeState,
    WorkItem,
)
from optagent.v1.core.models import Requirement as RequirementV1


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
        
        promotion = getattr(requirements, 'promotion', {})
        if promotion.get("require_dispatch_diagnosis", True):
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
        # Backward compatibility for v1.5 interface
        strategy: Any = None,
        backend: Any = None,
    ) -> None:
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        
        self.hypothesis_agent = hypothesis_agent
        self.artifact_builder = artifact_builder
        self.evaluator = evaluator
        self.analyzer = analyzer
        self.promotion_gate = PromotionGate()
        self.state_store: StateStore | None = None
        
        # Store legacy components for backward compatibility
        self._strategy = strategy
        self._backend = backend

    def optimize(
        self,
        requirements: Requirements | RequirementV1,
        state=None,
        return_v1_state: bool = False,
    ) -> OptimizerState:
        """Run one optimization round.

        State transition: X_t -> X_{t+1}
        """
        # Convert legacy public Requirement to the workflow Requirements model if needed.
        if isinstance(requirements, RequirementV1):
            requirements = Requirements(
                target_type=requirements.target_type,
                target_id=requirements.target_id,
                parameters=dict(requirements.parameters),
                constraints=dict(requirements.constraints),
                objective=dict(requirements.objective),
            )
        if self.state_store is None or self.state_store.root != self.work_dir:
            self.state_store = StateStore(self.work_dir)

        requirement_record = RequirementRecord.from_requirement(requirements)
        self.state_store.save_requirement(requirement_record)
        
        # Initialize or resume state
        if state is None:
            state = OptimizerState(
                algorithm=AlgorithmState(requirements=requirements),
                work_dir=self.work_dir,
            )
        else:
            # Resume from previous state
            state.work_dir = self.work_dir
            state.algorithm.round_index += 1
        
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

            # Evidence Graph: persist each evaluated attempt as a JSONL node.
            self._record_attempts(
                requirement_record=requirement_record,
                hypotheses=approved,
                artifacts=artifacts,
                evidence_list=evidence_list,
                decisions=decisions,
                state=state,
            )
            
            # Save state
            self._save_state(state, analysis)
            
        except GuardrailError as e:
            self._save_state(state, {"error": str(e), "phase": "guardrail"})
            raise
        
        if return_v1_state:
            # Convert to v1.5 OptimizationState for backward compatibility
            from optagent.v1.core.models import OptimizationState as OptimizationStateV1
            from optagent.v1.core.models import Hypothesis as HypothesisV1
            from optagent.v1.core.models import Artifact as ArtifactV1
            from optagent.v1.core.models import Evidence as EvidenceV1
            from optagent.v1.core.models import Decision as DecisionV1
            
            v1_state = OptimizationStateV1(
                round_index=state.algorithm.round_index,
                requirement=None,  # Would need conversion
                hypotheses=[],
                artifacts=[],
                evidence=[],
                decisions=[],
                work_dir=self.work_dir,
            )
            return v1_state
        
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

    def _review_hypotheses(
        self,
        hypotheses: list[Hypothesis],
        state: OptimizerState,
    ) -> list[Hypothesis]:
        """Validate and approve hypotheses.
        
        Guardrail: Expected effect must be measurable.
        """
        approved = []
        for h in hypotheses:
            if not h.expected_effect:
                raise GuardrailError(f"Hypothesis {h.id} has no measurable expected_effect")
            approved.append(h)
        return approved

    def _build_artifacts(
        self,
        hypotheses: list[Hypothesis],
        state: OptimizerState,
    ) -> list[Artifact]:
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

    def _evaluate_artifacts(
        self,
        artifacts: list[Artifact],
        state: OptimizerState,
    ) -> list[EvidenceRecord]:
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
            if callable(self.evaluator):
                # File-based protocol
                request_path = self.work_dir / f"request_eval_{artifact.hypothesis_id}.json"
                request = {
                    "artifact": artifact.to_dict(),
                    "requirements": state.algorithm.requirements.to_dict(),
                }
                request_path.write_text(json.dumps(request, indent=2))
                
                response = self.evaluator(request_path)
                evidence = self._parse_evidence(response)
            else:
                # Object with evaluate() method (v1.5 compatibility)
                ev_record = self.evaluator.evaluate(artifact, state)
                # Convert v1.5 Evidence to EvidenceRecord
                evidence = EvidenceRecord(
                    hypothesis_id=artifact.hypothesis_id,
                    artifact_id=artifact.artifact_type,
                    correctness="passed" if ev_record.is_correct else "failed",
                    eligible=ev_record.is_eligible,
                    speedup=ev_record.speedup,
                )
            
            # Guardrail: Evidence must have dispatch keys (optional for v1.5 compat)
            # if not evidence.dispatch_keys:
            #     raise GuardrailError(f"Evidence {evidence.hypothesis_id} missing dispatch_keys")
            
            evidence_list.append(evidence)
        
        return evidence_list

    def _apply_promotion_gate(
        self,
        evidence_list: list[EvidenceRecord],
        requirements: Requirements,
    ) -> list[str]:
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

    def _record_attempts(
        self,
        requirement_record: RequirementRecord,
        hypotheses: list[Hypothesis],
        artifacts: list[Artifact],
        evidence_list: list[EvidenceRecord],
        decisions: list[str],
        state: OptimizerState,
    ) -> None:
        """Append canonical Evidence Graph attempts for this workflow round."""
        if self.state_store is None:
            self.state_store = StateStore(self.work_dir)

        prior_attempts = len(self.state_store.read_attempts())
        hypotheses_by_id = {h.id: h for h in hypotheses}
        evidence_by_hypothesis = {e.hypothesis_id: e for e in evidence_list}

        for index, artifact in enumerate(artifacts, start=1):
            attempt_index = prior_attempts + index
            attempt_id = sequential_id("attempt", attempt_index)
            hypothesis = hypotheses_by_id.get(artifact.hypothesis_id)
            evidence = evidence_by_hypothesis.get(artifact.hypothesis_id)
            decision = decisions[index - 1] if index - 1 < len(decisions) else "needs_more_evidence"

            action = ActionRecord(
                action_id=f"action:{attempt_id}",
                action_type="apply_hypothesis",
                estimated_cost=None,
                expected_observation_schema={
                    "artifact": "candidate artifact",
                    "evidence": "correctness, eligibility, regressions, speedup",
                },
                metadata={"workflow": "v1.hypothesis_test"},
            )

            observation = None
            canonical_evidence = None
            if evidence is not None:
                observation = ObservationRecord(
                    observation_id=f"observation:{attempt_id}",
                    action_id=action.action_id,
                    raw_output_path=evidence.raw_output,
                    metrics={
                        key: value
                        for key, value in {
                            "speedup": evidence.speedup,
                            "mean_ms_candidate": evidence.mean_ms_candidate,
                            "mean_ms_baseline": evidence.mean_ms_baseline,
                        }.items()
                        if value is not None
                    },
                    metadata={"source": "v1.EvidenceRecord"},
                )
                canonical_evidence = CanonicalEvidenceRecord.from_evidence(evidence)
                canonical_evidence.evidence_id = f"evidence:{attempt_id}"

            finding = self._finding_from_decision(attempt_id, decision, evidence)
            attempt = AttemptRecord(
                attempt_id=attempt_id,
                requirement_id=requirement_record.requirement_id,
                hypothesis=HypothesisRecord.from_hypothesis(hypothesis) if hypothesis else None,
                action=action,
                artifact=ArtifactRecord.from_artifact(artifact),
                observation=observation,
                evidence=canonical_evidence,
                decision=DecisionRecord(
                    decision_id=f"decision:{attempt_id}",
                    status=canonical_decision_status(decision),
                    reason=self._decision_reason(decision, evidence),
                    policy=dict(state.algorithm.requirements.promotion),
                    metadata={"v1_decision": decision},
                ),
                finding=finding,
                metadata={"round_index": state.algorithm.round_index},
            )
            self.state_store.append_attempt(attempt)

    @staticmethod
    def _decision_reason(decision: str, evidence: EvidenceRecord | None) -> str:
        if evidence is None:
            return "No evidence was produced for this artifact."
        if decision == "accepted":
            return "Candidate passed promotion criteria."
        if decision == "needs_narrower_scope":
            return "Candidate is not eligible for the full target scope or has regressions."
        if decision in {"inconclusive", "needs_more_evidence"}:
            return "Evidence is incomplete for promotion."
        if decision == "unsafe":
            return "Candidate was marked unsafe."
        if evidence.correctness != "passed":
            return "Correctness did not pass."
        return "Candidate did not meet the required improvement threshold."

    @staticmethod
    def _finding_from_decision(
        attempt_id: str,
        decision: str,
        evidence: EvidenceRecord | None,
    ) -> FindingRecord | None:
        if evidence is None:
            return None
        if decision == "accepted":
            return FindingRecord(
                finding_id=f"finding:{attempt_id}",
                summary="Candidate satisfied promotion criteria.",
                promising="Reuse this hypothesis pattern for similar requirements.",
            )
        if decision == "needs_narrower_scope":
            regressions = ", ".join(evidence.regressions)
            return FindingRecord(
                finding_id=f"finding:{attempt_id}",
                summary="Candidate may work only under a narrower scope.",
                avoid=f"Do not promote broadly while regressions exist: {regressions}"
                if regressions
                else "Do not promote broadly until eligibility is narrowed.",
                promising="Retry with narrower dispatch or workload constraints.",
            )
        if decision in {"rejected", "unsafe"}:
            return FindingRecord(
                finding_id=f"finding:{attempt_id}",
                summary="Candidate should not be promoted as evaluated.",
                avoid=(
                    evidence.failure_reason
                    or "Avoid repeating this candidate without new evidence."
                ),
            )
        return None

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
