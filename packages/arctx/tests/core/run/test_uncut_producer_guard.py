"""uncut must not hand a node a second active producer.

`reparent` is the only writer that gives an existing node more than one
producing Step, and it keeps at most one of them active. `uncut` guards that
invariant -- but it used to accept a competing producer that was merely
inactive *by propagation*. Propagated inactivity is revocable: uncut the
upstream node and the producer returns, and now both are active. `lane
validate` and `doctor` both reported healthy while trace and export showed a
merged lineage that never happened.
"""

from __future__ import annotations

import pytest

from arctx import init
from arctx.core.cuts import inactive_step_ids
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement


def _tp() -> StepPayload:
    return StepPayload(payload_id="_", target_id="_", type="note")


def _reparented_run():
    handle = init(Requirement(requirement_id="r", target_type="task", target_id="t"))
    handle.ensure_lane(user_id="u", lane_id="L")
    kw = dict(user_id="u", lane_id="L")
    a = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    b = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    first = handle.add_step([a], _tp(), **kw)
    second = handle.reparent(first.output_node_id, [b], _tp(), **kw)
    return handle, first, second, b


def _active_producers(handle, node_id):
    inactive = inactive_step_ids(handle.run_graph)
    return [p for p in handle.run_graph.producers_of(node_id) if p not in inactive]


def test_uncut_refuses_when_the_competitor_is_only_propagation_inactive():
    handle, first, second, b = _reparented_run()
    kw = dict(user_id="u", lane_id="L")

    # Cutting b makes `second` inactive by propagation -- revocable, not retired.
    handle.cut(b, target_kind="node", **kw)
    assert second.step_id in inactive_step_ids(handle.run_graph)

    with pytest.raises(ValueError, match="already has an active producer"):
        handle.uncut(first.step_id, target_kind="step", **kw)


def test_the_invariant_holds_after_the_propagation_is_undone():
    handle, first, second, b = _reparented_run()
    kw = dict(user_id="u", lane_id="L")
    node_id = first.output_node_id

    handle.cut(b, target_kind="node", **kw)
    with pytest.raises(ValueError):
        handle.uncut(first.step_id, target_kind="step", **kw)
    handle.uncut(b, target_kind="node", **kw)

    assert len(_active_producers(handle, node_id)) == 1


def test_uncut_still_works_once_the_competitor_is_explicitly_cut():
    handle, first, second, _b = _reparented_run()
    kw = dict(user_id="u", lane_id="L")
    node_id = first.output_node_id

    handle.cut(second.step_id, target_kind="step", **kw)
    handle.uncut(first.step_id, target_kind="step", **kw)

    assert _active_producers(handle, node_id) == [first.step_id]
