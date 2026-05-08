"""Detailed tests for state and snapshot CLI commands."""

from __future__ import annotations

import pytest

from optagent.cli.commands.derive import run_derive_command
from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.snapshot import run_snapshot_command
from optagent.cli.commands.state import (
    _parse_artifact,
    _parse_prediction,
    run_state_command,
)
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


def test_state_parse_helpers_validate_shape():
    assert _parse_artifact("a:log:path.txt") == ("a", "log", "path.txt")
    assert _parse_artifact("a:log:") == ("a", "log", None)
    assert _parse_prediction("p:summary") == ("p", "summary")

    with pytest.raises(ValueError):
        _parse_artifact("missing-kind")
    with pytest.raises(ValueError):
        _parse_prediction("missing-summary")


def test_state_update_appends_snapshot_payload_with_structured_refs(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)

    result = run_state_command(
        run_id=run_id,
        store_dir=store_dir,
        node_id="n_0000",
        add_knowledge=["learned something"],
        add_open_question=["what next?"],
        add_artifact=["artifact:log:path.txt"],
        add_prediction=["pred:likely faster"],
        add_branch=["branch-a"],
    )["snapshot"]

    snap = result["snapshot"]
    assert result["target_id"] == "n_0000"
    assert snap["knowledge"][0]["summary"] == "learned something"
    assert snap["open_questions"] == ["what next?"]
    assert snap["artifacts"][0]["artifact_id"] == "artifact"
    assert snap["artifacts"][0]["artifact_type"] == "log"
    assert snap["artifacts"][0]["path"] == "path.txt"
    assert snap["predictions"][0]["prediction_id"] == "pred"
    assert snap["active_branches"] == ["branch-a"]

    handle = JsonlRunStore(store_dir).load_run(run_id)
    assert len(handle.observed_dag.payloads_for("n_0000", payload_type="snapshot")) == 2


def test_snapshot_rebuild_aggregates_artifacts_and_findings(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_id = _init(store_dir)
    plan_id = run_plan_command(
        run_id=run_id,
        planner="planner",
        max_plans=1,
        store_dir=store_dir,
        from_node_id="n_0000",
    )["plans"][0]["plan_id"]
    transition = run_observe_command(
        run_id=run_id,
        plan_id=plan_id,
        status="completed",
        artifacts=["artifact.bin"],
        raw_outputs=["raw.txt"],
        logs=["stderr.log"],
        metrics=None,
        errors=None,
        store_dir=store_dir,
    )["transition"]
    run_derive_command(
        run_id=run_id,
        transition_id=transition["transition_id"],
        derived_type="finding",
        payload={"text": "useful finding"},
        payload_id=None,
        generator="test",
        confidence=None,
        store_dir=store_dir,
    )

    rebuilt = run_snapshot_command(
        run_id=run_id,
        node_id=transition["to_node_id"],
        rebuild=True,
        store_dir=store_dir,
    )
    snapshot = rebuilt["snapshot"]

    assert [a["artifact_id"] for a in snapshot["artifacts"]] == [
        "artifact.bin",
        "raw.txt",
        "stderr.log",
    ]
    assert snapshot["knowledge"][0]["summary"] == "useful finding"
    assert rebuilt["metadata"]["source"] == "snapshot_rebuild"
