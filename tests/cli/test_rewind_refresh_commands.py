"""Detailed tests for rewind and refresh CLI commands."""

from __future__ import annotations

import pytest

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.refresh import run_refresh_command
from optagent.cli.commands.rewind import run_rewind_command
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


def _observed_transition(store_dir: str, run_id: str) -> dict:
    plan_id = run_plan_command(
        run_id=run_id,
        planner="planner",
        max_plans=1,
        store_dir=store_dir,
        from_node_id="n_0000",
    )["plans"][0]["plan_id"]
    return run_observe_command(
        run_id=run_id,
        plan_id=plan_id,
        status="completed",
        artifacts=None,
        raw_outputs=None,
        logs=None,
        metrics=None,
        errors=None,
        store_dir=store_dir,
    )["transition"]


def test_rewind_appends_cut_and_blocks_cut_subtree(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    transition = _observed_transition(store_dir, run_id)

    cut = run_rewind_command(
        run_id=run_id,
        transition_id=transition["transition_id"],
        from_node_id=transition["to_node_id"],
        reason="wrong branch",
        store_dir=store_dir,
        user_id="alice",
    )["cut"]

    assert cut["target_id"] == transition["transition_id"]
    assert cut["rewound_to_node_id"] == transition["from_node_id"]
    assert cut["reason"] == "wrong branch"
    assert cut["user_id"] == "alice"

    with pytest.raises(ValueError):
        run_plan_command(
            run_id=run_id,
            planner="planner",
            max_plans=1,
            store_dir=store_dir,
            from_node_id=transition["to_node_id"],
        )


def test_rewind_rejects_duplicate_and_non_ancestor_transition(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    transition = _observed_transition(store_dir, run_id)

    with pytest.raises(ValueError):
        run_rewind_command(
            run_id=run_id,
            transition_id=transition["transition_id"],
            from_node_id="n_0000",
            reason=None,
            store_dir=store_dir,
        )

    run_rewind_command(
        run_id=run_id,
        transition_id=transition["transition_id"],
        from_node_id=transition["to_node_id"],
        reason=None,
        store_dir=store_dir,
    )
    with pytest.raises(ValueError):
        run_rewind_command(
            run_id=run_id,
            transition_id=transition["transition_id"],
            from_node_id=transition["to_node_id"],
            reason=None,
            store_dir=store_dir,
        )


def test_refresh_replaces_predicted_dag_and_reanchors_to_observed_node(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    transition = _observed_transition(store_dir, run_id)
    before = JsonlRunStore(store_dir).load_run(run_id).predicted_dag.dag_id

    refreshed = run_refresh_command(
        run_id=run_id,
        from_node_id=transition["to_node_id"],
        store_dir=store_dir,
    )["predicted_dag"]

    after = JsonlRunStore(store_dir).load_run(run_id).predicted_dag
    assert refreshed["dag_id"] != before
    assert refreshed["metadata"]["anchor_node_id"] == transition["to_node_id"]
    assert after.dag_id == refreshed["dag_id"]
    assert after.metadata["root_node_id"] in after.nodes
