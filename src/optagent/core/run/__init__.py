"""Run handle and initialization."""

from optagent.core.run.handle import RunHandle, init
from optagent.core.run.ops import (  # noqa: F401
    _append_observed_transition,
    _find_plan,
    _make_predicted_state,
    _new_prediction_dag,
    _plan_from_state_id,
    _predicted_depth_for_plan,
    observe_impl,
    plan_impl,
    predict_impl,
    promote_impl,
    refresh_impl,
    select_prediction_impl,
    trace_impl,
)

RunHandle._find_plan = _find_plan
RunHandle._make_predicted_state = _make_predicted_state
RunHandle._plan_from_state_id = _plan_from_state_id
RunHandle._predicted_depth_for_plan = _predicted_depth_for_plan
RunHandle._append_observed_transition = _append_observed_transition
RunHandle.plan = plan_impl
RunHandle.predict = predict_impl
RunHandle.select_prediction = select_prediction_impl
RunHandle.promote = promote_impl
RunHandle.observe = observe_impl
RunHandle.result = observe_impl
RunHandle.trace = trace_impl
RunHandle.history = trace_impl
RunHandle.refresh = refresh_impl

__all__ = ["RunHandle", "init"]
