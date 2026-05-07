"""Run handle definition and initialization."""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.ids import sequential_id, slugify, timestamp_id
from optagent.core.schema.cursor import (
    DEFAULT_ACTOR_ID,
    DEFAULT_CURSOR_ID,
    Actor,
    Cursor,
)
from optagent.core.schema.requirements import Requirement
from optagent.core.schema.state import StateNode, StateSnapshot
from optagent.core.dag import PredictionDAG, TraceDAG


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
    actors: dict[str, Actor] = field(default_factory=dict)
    cursors: dict[str, Cursor] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return sequential_id(prefix, self._counters[prefix])

    @property
    def current_observed_state(self) -> StateNode:
        return self.trace_dag.nodes[self.current_observed_state_id]

    def _ensure_active_observed_state(self, state_id: str) -> None:
        """Reject state IDs that are unknown or sit inside a cut subtree.

        Writers (plan, promote, observe) must call this on whichever
        observed state they are about to grow from. Reading APIs that
        only inspect history do not need to call it.
        """
        if state_id not in self.trace_dag.nodes:
            raise KeyError(f"unknown observed state_id: {state_id}")
        if self.trace_dag.is_cut_state(state_id):
            raise ValueError(
                f"state is in a cut branch: {state_id}; "
                "rewind cut this subtree, so no new plans/observations can extend it"
            )

    def _set_current_observed(self, state_id: str) -> None:
        """Move the run's observed pointer and keep the main cursor in sync.

        ``current_observed_state_id`` is the legacy single-cursor pointer
        and remains the source of truth for now. The main cursor is the
        forward-compat surface that callers will read against once the
        cursor model fully takes over; until then we mirror the value.
        """
        self.current_observed_state_id = state_id
        main = self.cursors.get(DEFAULT_CURSOR_ID)
        if main is not None and main.state_kind == "observed":
            main.current_state_id = state_id

    def save(self, store) -> object:
        """Save this run through a storage adapter."""
        return store.save_run(self)


def init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle:
    """Create a new in-memory run with TraceDAG and PredictionDAG roots."""

    rid = run_id or timestamp_id(f"run_{slugify(requirement.requirement_id)}")
    initial_snapshot = StateSnapshot(requirement=requirement)
    observed = StateNode(
        state_id="s_obs_0000",
        state_kind="observed",
        snapshot=initial_snapshot,
        snapshot_hash=initial_snapshot.compute_hash(),
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
    default_actor = Actor(
        actor_id=DEFAULT_ACTOR_ID,
        actor_type="human",
        name="default user",
    )
    main_cursor = Cursor(
        cursor_id=DEFAULT_CURSOR_ID,
        owner_actor_id=DEFAULT_ACTOR_ID,
        current_state_id=observed.state_id,
        state_kind="observed",
        name="main",
        purpose="default cursor for the human user",
    )
    return RunHandle(
        run_id=rid,
        requirement=requirement,
        trace_dag=trace_dag,
        prediction_dag=prediction_dag,
        current_observed_state_id=observed.state_id,
        actors={default_actor.actor_id: default_actor},
        cursors={main_cursor.cursor_id: main_cursor},
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
            "cut": 0,
        },
    )


# Attach methods from submodules so RunHandle stays thin.
from optagent.core.run.helpers import (  # noqa: E402
    find_plan_impl as _find_plan,
    make_predicted_state_impl as _make_predicted_state,
    plan_from_state_id_impl as _plan_from_state_id,
    predicted_depth_for_plan_impl as _predicted_depth_for_plan,
)
from optagent.core.run.observe import observe_impl as _observe_impl  # noqa: E402
from optagent.core.run.plan import (  # noqa: E402
    extend_impl as _extend_impl,
    plan_impl as _plan_impl,
)
from optagent.core.run.predict import (  # noqa: E402
    predict_impl as _predict_impl,
    select_prediction_impl as _select_prediction_impl,
)
from optagent.core.run.promote import (  # noqa: E402
    _append_observed_transition as _append_observed_transition_impl,
    promote_impl as _promote_impl,
)
from optagent.core.run.trace import refresh_impl as _refresh_impl, trace_impl as _trace_impl  # noqa: E402
from optagent.core.run.derive import derive_impl as _derive_impl  # noqa: E402
from optagent.core.run.rewind import rewind_impl as _rewind_impl  # noqa: E402
from optagent.core.run.snapshot import snapshot_rebuild_impl as _snapshot_rebuild_impl  # noqa: E402
from optagent.core.run.state_impl import (  # noqa: E402
    state_show_impl as _state_show_impl,
    state_update_impl as _state_update_impl,
)

RunHandle._find_plan = _find_plan
RunHandle._make_predicted_state = _make_predicted_state
RunHandle._plan_from_state_id = _plan_from_state_id
RunHandle._predicted_depth_for_plan = _predicted_depth_for_plan
RunHandle._append_observed_transition = _append_observed_transition_impl
RunHandle.plan = _plan_impl
RunHandle.extend = _extend_impl
RunHandle.predict = _predict_impl
RunHandle.select_prediction = _select_prediction_impl
RunHandle.promote = _promote_impl
RunHandle.observe = _observe_impl
RunHandle.result = _observe_impl
RunHandle.trace = _trace_impl
RunHandle.history = _trace_impl
RunHandle.refresh = _refresh_impl
RunHandle.derive = _derive_impl
RunHandle.rewind = _rewind_impl
RunHandle.state_show = _state_show_impl
RunHandle.state_update = _state_update_impl
RunHandle.snapshot_rebuild = _snapshot_rebuild_impl
