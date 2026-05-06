"""Minimal run API for PredictionDAG and TraceDAG operations."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from typing import Literal

from optagent.core.ids import sequential_id, slugify, timestamp_id
from optagent.core.schema import (
    ActionResult,
    DerivedRecord,
    ExecutionPlan,
    ObservedTransition,
    PredictionMatch,
    PredictionPath,
    PredictionPlan,
    PredictionSelection,
    PredictedTransition,
    Requirement,
    StateNode,
    StateSnapshot,
    TraceContext,
)
from optagent.core.tree import PredictionDAG, TraceDAG


def _snapshot_hash(snapshot: StateSnapshot) -> str:
    encoded = json.dumps(snapshot.to_dict(), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass
class RunHandle:
    """In-memory handle for one optimization/problem-solving run.

    This class implements the canonical API shape without choosing a real
    planner, predictor, executor, or storage backend. Those can be layered on
    top while preserving the source-of-truth records.
    """

    run_id: str
    requirement: Requirement
    trace_dag: TraceDAG
    prediction_dag: PredictionDAG
    current_observed_state_id: str
    _counters: dict[str, int] = field(default_factory=dict)

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return sequential_id(prefix, self._counters[prefix])

    @property
    def current_observed_state(self) -> StateNode:
        return self.trace_dag.nodes[self.current_observed_state_id]

    def plan(
        self,
        state_id: str,
        *,
        planner: str | None = None,
        max_plans: int | None = None,
    ) -> list[ExecutionPlan | PredictionPlan]:
        """Create executable or predictive plans from the given state."""

        count = max(1, max_plans or 1)
        plans: list[ExecutionPlan | PredictionPlan] = []
        for index in range(count):
            if state_id in self.trace_dag.nodes:
                plan = ExecutionPlan(
                    plan_id=self._next_id("p_exec"),
                    plan_kind="execution",
                    from_observed_state_id=state_id,
                    action_type="analysis",
                    intent="inspect current state and propose next useful action",
                    metadata={
                        "planner": planner or "default",
                        "ordinal": index,
                    },
                )
                self.trace_dag.add_execution_plan(plan)
            elif state_id in self.prediction_dag.nodes:
                plan = PredictionPlan(
                    plan_id=self._next_id("p_pred"),
                    plan_kind="prediction",
                    from_predicted_state_id=state_id,
                    action_type="analysis",
                    intent="inspect predicted state and extend the future scenario",
                    metadata={
                        "planner": planner or "default",
                        "ordinal": index,
                    },
                )
                self.prediction_dag.add_plan(plan)
            else:
                raise KeyError(f"unknown state_id: {state_id}")
            plans.append(plan)
        return plans

    def predict(
        self,
        plan_id: str,
        *,
        predictor: str | None = None,
        max_outcomes: int | None = None,
    ) -> list[PredictedTransition]:
        """Expand the PredictionDAG with predicted outcomes for a plan."""

        plan = self._find_plan(plan_id)
        if isinstance(plan, ExecutionPlan) and plan.plan_id not in self.prediction_dag.plans:
            self.prediction_dag.add_plan(plan)
        count = max(1, max_outcomes or 1)
        transitions: list[PredictedTransition] = []
        for index in range(count):
            predicted_state = self._make_predicted_state(plan, index)
            depth = self._predicted_depth_for_plan(plan) + 1
            self.prediction_dag.add_node(predicted_state, depth=depth)
            transition = PredictedTransition(
                transition_id=self._next_id("t_pred"),
                transition_kind="predicted",
                parent_plan_id=plan.plan_id,
                parent_plan_kind=plan.plan_kind,
                from_state_id=self._plan_from_state_id(plan),
                outcome_id=f"outcome_{index + 1}",
                outcome_label="default predicted outcome",
                predicted_result={
                    "status": "unknown",
                    "predictor": predictor or "default",
                },
                predicted_state_delta=dict(plan.expected_state_delta),
                to_predicted_state_id=predicted_state.state_id,
                metadata={"ordinal": index},
            )
            self.prediction_dag.add_transition(transition)
            transitions.append(transition)
        return transitions

    def select_prediction(
        self,
        *,
        predicted_transition_id: str | None = None,
        predicted_transition_ids: list[str] | None = None,
        to_predicted_state_id: str | None = None,
        reason: str = "",
    ) -> PredictionSelection:
        """Select predicted transitions for later promotion or comparison."""

        selected = list(predicted_transition_ids or ())
        if predicted_transition_id is not None:
            selected.append(predicted_transition_id)
        if to_predicted_state_id is not None:
            selected.extend(
                transition_id
                for transition_id, transition in self.prediction_dag.transitions.items()
                if transition.to_predicted_state_id == to_predicted_state_id
            )
        if not selected:
            raise ValueError("select_prediction requires at least one predicted transition")
        for transition_id in selected:
            if transition_id not in self.prediction_dag.transitions:
                raise KeyError(f"unknown predicted_transition_id: {transition_id}")
        return PredictionSelection(
            selection_id=self._next_id("sel_pred"),
            selected_transition_ids=tuple(dict.fromkeys(selected)),
            reason=reason,
        )

    def promote(
        self,
        *,
        mode: Literal["plan", "transition"],
        prediction_plan_id: str | None = None,
        prediction_path: PredictionPath | None = None,
        observed_state_id: str | None = None,
        predicted_transition_id: str | None = None,
        action_result: ActionResult | None = None,
        execution_plan_id: str | None = None,
        derived_records: list[DerivedRecord] | None = None,
    ) -> list[ExecutionPlan] | ObservedTransition:
        """Promote prediction-side records into trace-side grounded records."""

        if mode == "plan":
            return self._promote_plan(
                prediction_plan_id=prediction_plan_id,
                prediction_path=prediction_path,
                observed_state_id=observed_state_id,
            )
        if mode == "transition":
            if predicted_transition_id is None or action_result is None:
                raise ValueError(
                    "promote(mode='transition') requires predicted_transition_id and action_result"
                )
            return self._promote_transition(
                predicted_transition_id=predicted_transition_id,
                action_result=action_result,
                execution_plan_id=execution_plan_id,
                derived_records=derived_records or [],
            )
        raise ValueError(f"unsupported promote mode: {mode}")

    def observe(
        self,
        execution_plan_id: str,
        action_result: ActionResult,
        *,
        derived_records: list[DerivedRecord] | None = None,
    ) -> ObservedTransition:
        """Record an execution result without matching it to a prediction."""

        plan = self.trace_dag.execution_plans.get(execution_plan_id)
        if plan is None:
            raise KeyError(f"unknown execution_plan_id: {execution_plan_id}")
        if action_result.execution_plan_id != execution_plan_id:
            raise ValueError("ActionResult.execution_plan_id must match execution_plan_id")
        return self._append_observed_transition(
            plan=plan,
            action_result=action_result,
            matched_predicted_transition_id=None,
            prediction_match=None,
            derived_records=derived_records or [],
        )

    result = observe

    def refresh(
        self,
        *,
        from_state_id: str | None = None,
        mode: str = "reset",
    ) -> PredictionDAG:
        """Re-anchor the PredictionDAG to an observed state."""

        observed_state_id = from_state_id or self.current_observed_state_id
        observed_state = self.trace_dag.nodes.get(observed_state_id)
        if observed_state is None or observed_state.state_kind != "observed":
            raise KeyError(f"unknown observed state_id: {observed_state_id}")
        if mode not in {"reset", "stale"}:
            raise ValueError("refresh mode must be 'reset' or 'stale'")
        if mode == "stale":
            self.prediction_dag.stale = True
        self.prediction_dag = self._new_prediction_dag(observed_state)
        return self.prediction_dag

    def trace(
        self,
        state_id: str | None = None,
        *,
        depth: int | None = None,
        include_derived: bool = True,
        include_raw_refs: bool = True,
    ) -> TraceContext:
        """Walk observed history backwards from a state."""

        current_id = state_id or self.current_observed_state_id
        if current_id not in self.trace_dag.nodes:
            raise KeyError(f"unknown observed state_id: {current_id}")

        remaining = depth
        cursor = current_id
        past_state_ids: list[str] = []
        transition_ids: list[str] = []
        execution_plan_ids: list[str] = []
        result_ids: list[str] = []
        matched_predicted_ids: list[str] = []
        derived_ids: list[str] = []
        artifact_refs: list[str] = []

        while remaining is None or remaining > 0:
            incoming = self.trace_dag.past_transition_ids(cursor)
            if not incoming:
                break
            transition = self.trace_dag.transitions[incoming[-1]]
            transition_ids.append(transition.transition_id)
            execution_plan_ids.append(transition.execution_plan_id)
            result_ids.append(transition.action_result.result_id)
            past_state_ids.append(transition.from_observed_state_id)
            if transition.matched_predicted_transition_id is not None:
                matched_predicted_ids.append(transition.matched_predicted_transition_id)
            if include_derived:
                derived_ids.extend(record.derived_id for record in transition.derived_records)
            if include_raw_refs:
                artifact_refs.extend(transition.action_result.artifacts)
                artifact_refs.extend(transition.action_result.raw_outputs)
                artifact_refs.extend(transition.action_result.logs)
            cursor = transition.from_observed_state_id
            if remaining is not None:
                remaining -= 1

        return TraceContext(
            current_state_id=current_id,
            past_state_ids=tuple(past_state_ids),
            observed_transition_ids=tuple(transition_ids),
            execution_plan_ids=tuple(execution_plan_ids),
            action_result_ids=tuple(result_ids),
            matched_predicted_transition_ids=tuple(matched_predicted_ids),
            derived_record_ids=tuple(derived_ids),
            artifact_refs=tuple(artifact_refs),
        )

    history = trace

    def _find_plan(self, plan_id: str) -> ExecutionPlan | PredictionPlan:
        if plan_id in self.trace_dag.execution_plans:
            return self.trace_dag.execution_plans[plan_id]
        if plan_id in self.prediction_dag.plans:
            return self.prediction_dag.plans[plan_id]
        raise KeyError(f"unknown plan_id: {plan_id}")

    def _plan_from_state_id(self, plan: ExecutionPlan | PredictionPlan) -> str:
        if isinstance(plan, ExecutionPlan):
            return plan.from_observed_state_id
        return plan.from_predicted_state_id

    def _predicted_depth_for_plan(self, plan: ExecutionPlan | PredictionPlan) -> int:
        state_id = self._plan_from_state_id(plan)
        return self.prediction_dag.node_depths.get(state_id, 0)

    def _make_predicted_state(
        self,
        plan: ExecutionPlan | PredictionPlan,
        outcome_index: int,
    ) -> StateNode:
        anchor_id = (
            plan.from_observed_state_id
            if isinstance(plan, ExecutionPlan)
            else self.prediction_dag.anchor_observed_state_id
        )
        anchor = self.trace_dag.nodes[anchor_id]
        return StateNode(
            state_id=self._next_id("s_pred"),
            state_kind="predicted",
            snapshot=anchor.snapshot,
            snapshot_hash=anchor.snapshot_hash,
            anchor_observed_state_id=anchor_id,
            assumptions=tuple(plan.assumptions),
            confidence=getattr(plan, "confidence", None),
            metadata={
                "source_plan_id": plan.plan_id,
                "outcome_index": outcome_index,
            },
        )

    def _promote_plan(
        self,
        *,
        prediction_plan_id: str | None,
        prediction_path: PredictionPath | None,
        observed_state_id: str | None,
    ) -> list[ExecutionPlan]:
        target_observed_state_id = observed_state_id or self.current_observed_state_id
        if target_observed_state_id not in self.trace_dag.nodes:
            raise KeyError(f"unknown observed_state_id: {target_observed_state_id}")

        plan_ids: list[str] = []
        selected_by_plan: dict[str, str] = {}
        source_path_id: str | None = None
        if prediction_path is not None:
            source_path_id = prediction_path.path_id
            for step in prediction_path.steps:
                plan_ids.append(step.prediction_plan_id)
                selected_by_plan[step.prediction_plan_id] = step.selected_predicted_transition_id
        if prediction_plan_id is not None:
            plan_ids.append(prediction_plan_id)
        if not plan_ids:
            raise ValueError("promote(mode='plan') requires prediction_plan_id or prediction_path")

        promoted: list[ExecutionPlan] = []
        for plan_id in plan_ids:
            source_plan = self.prediction_dag.plans.get(plan_id)
            if not isinstance(source_plan, PredictionPlan):
                raise KeyError(f"unknown prediction_plan_id: {plan_id}")
            execution_plan = ExecutionPlan(
                plan_id=self._next_id("p_exec"),
                plan_kind="execution",
                from_observed_state_id=target_observed_state_id,
                action_type=source_plan.action_type,
                intent=source_plan.intent,
                inputs=dict(source_plan.inputs),
                expected_observation=dict(source_plan.expected_observation),
                expected_state_delta=dict(source_plan.expected_state_delta),
                estimated_cost=dict(source_plan.estimated_cost),
                safety_policy=dict(source_plan.safety_policy),
                assumptions=tuple(source_plan.assumptions),
                metadata={
                    **source_plan.metadata,
                    "source_prediction_plan_id": source_plan.plan_id,
                    "source_prediction_path_id": source_path_id,
                    "selected_predicted_transition_id": selected_by_plan.get(plan_id),
                    "promotion_id": self._next_id("promotion"),
                },
            )
            self.trace_dag.add_execution_plan(execution_plan)
            promoted.append(execution_plan)
        return promoted

    def _promote_transition(
        self,
        *,
        predicted_transition_id: str,
        action_result: ActionResult,
        execution_plan_id: str | None,
        derived_records: list[DerivedRecord],
    ) -> ObservedTransition:
        predicted_transition = self.prediction_dag.transitions.get(predicted_transition_id)
        if predicted_transition is None:
            raise KeyError(f"unknown predicted_transition_id: {predicted_transition_id}")
        if execution_plan_id is None:
            execution_plan = self._execution_plan_for_predicted_transition(predicted_transition)
            action_result = replace(
                action_result,
                execution_plan_id=execution_plan.plan_id,
            )
        else:
            execution_plan = self.trace_dag.execution_plans.get(execution_plan_id)
            if execution_plan is None:
                raise KeyError(f"unknown execution_plan_id: {execution_plan_id}")
        if action_result.execution_plan_id != execution_plan.plan_id:
            raise ValueError("ActionResult.execution_plan_id must match the ExecutionPlan")
        return self._append_observed_transition(
            plan=execution_plan,
            action_result=action_result,
            matched_predicted_transition_id=predicted_transition.transition_id,
            prediction_match=PredictionMatch(
                matched_predicted_transition_id=predicted_transition.transition_id,
                match_status="compatible",
                prediction_error={},
            ),
            derived_records=derived_records,
        )

    def _execution_plan_for_predicted_transition(
        self,
        predicted_transition: PredictedTransition,
    ) -> ExecutionPlan:
        parent_plan = self._find_plan(predicted_transition.parent_plan_id)
        if isinstance(parent_plan, ExecutionPlan):
            return parent_plan
        promoted = self._promote_plan(
            prediction_plan_id=parent_plan.plan_id,
            prediction_path=None,
            observed_state_id=self.current_observed_state_id,
        )
        return promoted[0]

    def _append_observed_transition(
        self,
        *,
        plan: ExecutionPlan,
        action_result: ActionResult,
        matched_predicted_transition_id: str | None,
        prediction_match: PredictionMatch | None,
        derived_records: list[DerivedRecord],
    ) -> ObservedTransition:
        next_state = StateNode(
            state_id=self._next_id("s_obs"),
            state_kind="observed",
            snapshot=self.trace_dag.nodes[plan.from_observed_state_id].snapshot,
            snapshot_hash=self.trace_dag.nodes[plan.from_observed_state_id].snapshot_hash,
        )
        next_depth = self.trace_dag.node_depths.get(plan.from_observed_state_id, 0) + 1
        self.trace_dag.add_node(next_state, depth=next_depth)
        transition = ObservedTransition(
            transition_id=self._next_id("t_obs"),
            transition_kind="observed",
            execution_plan_id=plan.plan_id,
            from_observed_state_id=plan.from_observed_state_id,
            to_observed_state_id=next_state.state_id,
            action_result=action_result,
            matched_predicted_transition_id=matched_predicted_transition_id,
            prediction_match=prediction_match,
            derived_records=tuple(derived_records),
        )
        self.trace_dag.append_transition(transition)
        self.current_observed_state_id = next_state.state_id
        return transition

    def _new_prediction_dag(self, observed_state: StateNode) -> PredictionDAG:
        root = StateNode(
            state_id=self._next_id("s_pred"),
            state_kind="predicted",
            snapshot=observed_state.snapshot,
            snapshot_hash=observed_state.snapshot_hash,
            anchor_observed_state_id=observed_state.state_id,
        )
        dag = PredictionDAG(
            dag_id=self._next_id("prediction_dag"),
            anchor_observed_state_id=observed_state.state_id,
            root_predicted_state_id=root.state_id,
        )
        dag.add_node(root, depth=0)
        return dag


def init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle:
    """Create a new in-memory run with TraceDAG and PredictionDAG roots."""

    rid = run_id or timestamp_id(f"run_{slugify(requirement.requirement_id)}")
    initial_snapshot = StateSnapshot(requirement=requirement)
    observed = StateNode(
        state_id="s_obs_0000",
        state_kind="observed",
        snapshot=initial_snapshot,
        snapshot_hash=_snapshot_hash(initial_snapshot),
    )
    trace_dag = TraceDAG(dag_id=f"{rid}_trace")
    trace_dag.add_node(observed, depth=0)
    predicted_root = StateNode(
        state_id="s_pred_0000",
        state_kind="predicted",
        snapshot=observed.snapshot,
        snapshot_hash=observed.snapshot_hash,
        anchor_observed_state_id=observed.state_id,
    )
    prediction_dag = PredictionDAG(
        dag_id=f"{rid}_prediction",
        anchor_observed_state_id=observed.state_id,
        root_predicted_state_id=predicted_root.state_id,
    )
    prediction_dag.add_node(predicted_root, depth=0)
    handle = RunHandle(
        run_id=rid,
        requirement=requirement,
        trace_dag=trace_dag,
        prediction_dag=prediction_dag,
        current_observed_state_id=observed.state_id,
        _counters={
            "s_obs": 0,
            "s_pred": 0,
            "p_exec": 0,
            "p_pred": 0,
            "t_obs": 0,
            "t_pred": 0,
            "sel_pred": 0,
            "promotion": 0,
            "prediction_dag": 0,
        },
    )
    return handle
