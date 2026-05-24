"""End-to-end CLI test with STAG_STORE=sqlite."""

from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from stag.cli.commands.init import run_init_command
from stag.cli.commands.anchor import run_anchor_command
from stag.cli.commands.cut import run_cut_command
from stag.cli.commands.note import run_note_command
from stag.cli.commands.observe import run_observe_command
from stag.cli.commands.plan import run_plan_command
from stag.cli.commands.predict import run_predict_command
from stag.cli.commands.view import cli_view
from stag.cli.context import resolve_store
from stag.core.run.dump import DumpOptions, dump


def test_sqlite_init_plan_dump(monkeypatch):
    monkeypatch.setenv("STAG_STORE", "sqlite")
    with tempfile.TemporaryDirectory() as td:
        # init
        result = run_init_command(
            requirement_id="r1",
            target_type="task",
            target_id="t1",
            run_id="run_e2e",
            store_dir=td,
        )
        run_id = result["run_id"]
        root = result["root_node_id"]
        assert run_id == "run_e2e"

        # plan
        plan_result = run_plan_command(
            run_id=run_id,
            input_node_ids=[root],
            action_type="analysis",
            intent="e2e test",
            store_dir=td,
        )
        assert "input_transition" in plan_result

        # dump — outline format via underlying API
        store = resolve_store(td)
        handle = store.load_run(run_id)
        output = dump(handle, "outline", DumpOptions())
        assert root in output

        # run.db exists, nodes.jsonl does NOT
        run_dir = Path(td) / run_id
        assert (run_dir / "run.db").exists(), "run.db should exist for sqlite backend"
        assert not (run_dir / "nodes.jsonl").exists(), "nodes.jsonl should not exist for sqlite backend"


def test_sqlite_plan_uses_append_batch_for_work_events(monkeypatch):
    monkeypatch.setenv("STAG_STORE", "sqlite")
    with tempfile.TemporaryDirectory() as td:
        result = run_init_command(
            requirement_id="r1",
            target_type="task",
            target_id="t1",
            run_id="run_append",
            store_dir=td,
        )

        plan_result = run_plan_command(
            run_id=result["run_id"],
            input_node_ids=[result["root_node_id"]],
            action_type="analysis",
            intent="append plan",
            store_dir=td,
            user_id="alice",
            work_session_id="ws_agent_a",
        )

        store = resolve_store(td)
        handle = store.load_run(result["run_id"])
        it_id = plan_result["input_transition"]["input_transition_id"]
        assert it_id in handle.run_graph.input_transitions
        assert handle.run_graph.work_sessions["ws_agent_a"].user_id == "alice"
        assert len(handle.run_graph.work_events) == 1
        event = handle.run_graph.work_events[0]
        assert event.seq == 1
        assert event.event_type == "plan_created"
        assert event.target_id == it_id


def test_sqlite_mutating_commands_use_append_batches(monkeypatch):
    monkeypatch.setenv("STAG_STORE", "sqlite")
    with tempfile.TemporaryDirectory() as td:
        result = run_init_command(
            requirement_id="r1",
            target_type="task",
            target_id="t1",
            run_id="run_all_append",
            store_dir=td,
        )
        run_id = result["run_id"]
        root = result["root_node_id"]

        plan = run_plan_command(
            run_id=run_id,
            input_node_ids=[root],
            action_type="analysis",
            intent="append plan",
            store_dir=td,
            user_id="alice",
            work_session_id="ws_agent_a",
        )["input_transition"]
        it_id = plan["input_transition_id"]

        predictions = run_predict_command(
            run_id=run_id,
            input_transition_id=it_id,
            max_outcomes=2,
            store_dir=td,
            user_id="alice",
            work_session_id="ws_agent_a",
        )["output_transitions"]

        observed = run_observe_command(
            run_id=run_id,
            input_transition_id=it_id,
            status="completed",
            artifacts=None,
            raw_outputs=None,
            logs=None,
            metrics=None,
            errors=None,
            matched_prediction_output_id=predictions[0]["output_transition_id"],
            store_dir=td,
            user_id="alice",
            work_session_id="ws_agent_a",
        )["output_transition"]

        run_note_command(
            run_id=run_id,
            node_id=observed["to_node_id"],
            text="keep this state",
            tags=["review"],
            store_dir=td,
            user_id="alice",
            work_session_id="ws_agent_a",
        )

        run_cut_command(
            run_id=run_id,
            target_id=predictions[1]["output_transition_id"],
            target_kind="output_transition",
            reason="not needed",
            store_dir=td,
            user_id="alice",
            work_session_id="ws_agent_a",
        )

        anchor = run_anchor_command(
            run_id=run_id,
            from_node_id=observed["to_node_id"],
            label="branch here",
            store_dir=td,
            user_id="alice",
            work_session_id="ws_agent_a",
        )["anchor"]

        store = resolve_store(td)
        handle = store.load_run(run_id)
        event_types = [event.event_type for event in handle.run_graph.work_events]
        assert event_types == [
            "plan_created",
            "prediction_created",
            "result_observed",
            "note_added",
            "cut_added",
            "plan_created",
            "result_observed",
        ]
        assert [event.seq for event in handle.run_graph.work_events] == list(range(1, 8))
        assert anchor["input_transition_id"] in handle.run_graph.input_transitions
        assert anchor["output_transition_id"] in handle.run_graph.output_transitions


def test_sqlite_view_create_uses_append_batch(monkeypatch, capsys):
    monkeypatch.setenv("STAG_STORE", "sqlite")
    with tempfile.TemporaryDirectory() as td:
        result = run_init_command(
            requirement_id="r1",
            target_type="task",
            target_id="t1",
            run_id="run_view_append",
            store_dir=td,
        )

        rc = cli_view(
            SimpleNamespace(
                view_command="create",
                name="review",
                root_node=result["root_node_id"],
                run=result["run_id"],
                store_dir=td,
                user="alice",
                work_session="ws_view",
            )
        )
        assert rc == 0
        capsys.readouterr()

        store = resolve_store(td)
        handle = store.load_run(result["run_id"])
        assert "review" in handle.run_graph.views
        assert handle.run_graph.work_events[-1].event_type == "view_created"
        assert handle.run_graph.work_events[-1].seq == 1
