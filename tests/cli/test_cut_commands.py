"""Tests for cut CLI commands."""

from __future__ import annotations

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.cut import run_cut_command
from optagent.core.cuts import is_active_node, is_inactive_output_transition
from optagent.storage.jsonl import JsonlRunStore


def _init(store_dir: str) -> str:
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_a",
        store_dir=store_dir,
    )
    return "run_a"


def _do_plan_observe(store_dir: str, run_id: str) -> tuple[str, str]:
    it_id = run_plan_command(
        run_id=run_id,
        input_node_ids=["n_0000"],
        action_type="analysis",
        intent="x",
        store_dir=store_dir,
    )["input_transition"]["input_transition_id"]
    ot = run_observe_command(
        run_id=run_id,
        input_transition_id=it_id,
        status="completed",
        artifacts=None, raw_outputs=None, logs=None, metrics=None, errors=None,
        store_dir=store_dir,
    )["output_transition"]
    return it_id, ot["output_transition_id"]


def test_cut_input_transition_marks_ot_and_downstream_inactive(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    it_id, ot_id = _do_plan_observe(store_dir, run_id)

    cut = run_cut_command(
        run_id=run_id,
        target_id=it_id,
        target_kind="input_transition",
        reason="undo plan",
        store_dir=store_dir,
        user_id="alice",
    )["cut"]

    assert cut["target_id"] == it_id
    assert cut["target_kind"] == "input_transition"

    handle = JsonlRunStore(store_dir).load_run(run_id)
    assert is_inactive_output_transition(handle.run_graph, ot_id)


def test_cut_output_transition_marks_only_that_ot_inactive(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    it_id, ot_id = _do_plan_observe(store_dir, run_id)

    cut = run_cut_command(
        run_id=run_id,
        target_id=ot_id,
        target_kind="output_transition",
        reason="bad result",
        store_dir=store_dir,
    )["cut"]

    assert cut["target_id"] == ot_id
    assert cut["target_kind"] == "output_transition"

    handle = JsonlRunStore(store_dir).load_run(run_id)
    assert is_inactive_output_transition(handle.run_graph, ot_id)
    assert is_active_node(handle.run_graph, "n_0000")


def test_cut_duplicate_raises(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    it_id, ot_id = _do_plan_observe(store_dir, run_id)

    run_cut_command(
        run_id=run_id, target_id=it_id, target_kind="input_transition",
        reason=None, store_dir=store_dir,
    )
    with pytest.raises(ValueError):
        run_cut_command(
            run_id=run_id, target_id=it_id, target_kind="input_transition",
            reason=None, store_dir=store_dir,
        )


def test_plan_on_cut_node_raises(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    it_id, ot_id = _do_plan_observe(store_dir, run_id)

    # Get to_node_id before cutting
    handle = JsonlRunStore(store_dir).load_run(run_id)
    ot = handle.run_graph.output_transitions[ot_id]
    to_node_id = ot.to_node_id

    run_cut_command(
        run_id=run_id, target_id=ot_id, target_kind="output_transition",
        reason=None, store_dir=store_dir,
    )

    with pytest.raises(ValueError):
        run_plan_command(
            run_id=run_id,
            input_node_ids=[to_node_id],
            action_type="analysis",
            intent="x",
            store_dir=store_dir,
        )
