"""Tests for optagent CLI rewind command and RunHandle.rewind."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

import optagent
from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.rewind import run_rewind_command
from optagent.cli.main import main, parse_args
from optagent.core.schema.requirements import Requirement
from optagent.storage.jsonl import JsonlRunStore


def _new_run(run_id: str = "r"):
    return optagent.init(
        Requirement(requirement_id="req_test", target_type="code", target_id="t"),
        run_id=run_id,
    )


def _advance(handle, plan_intent: str, result_id: str) -> str:
    """Helper: plan + observe → returns the new current_observed_state_id."""
    plan = handle.plan(intent=plan_intent)[0]
    from optagent.core.schema.results import ActionResult

    handle.observe(
        plan.plan_id,
        ActionResult(
            result_id=result_id,
            execution_plan_id=plan.plan_id,
            status="completed",
        ),
    )
    return handle.current_observed_state_id


class TestRunHandleRewind:
    """Core API: RunHandle.rewind moves the pointer without touching the DAG."""

    def test_rewind_to_ancestor_moves_current(self):
        run = _new_run()
        s1 = _advance(run, "first", "r_0001")
        _advance(run, "second", "r_0002")

        run.rewind(to_state_id=s1)
        assert run.current_observed_state_id == s1

    def test_rewind_does_not_delete_history(self):
        """Rewind is a pointer move; the TraceDAG keeps every record."""
        run = _new_run()
        _advance(run, "first", "r_0001")
        _advance(run, "second", "r_0002")
        nodes_before = set(run.trace_dag.nodes)
        plans_before = set(run.trace_dag.execution_plans)
        transitions_before = set(run.trace_dag.transitions)

        run.rewind(steps=2)

        assert set(run.trace_dag.nodes) == nodes_before
        assert set(run.trace_dag.execution_plans) == plans_before
        assert set(run.trace_dag.transitions) == transitions_before

    def test_rewind_refreshes_prediction_dag(self):
        run = _new_run()
        _advance(run, "first", "r_0001")
        old_dag_id = run.prediction_dag.dag_id

        run.rewind(steps=1)

        assert run.prediction_dag.anchor_observed_state_id == run.current_observed_state_id
        assert run.prediction_dag.dag_id != old_dag_id

    def test_rewind_steps(self):
        run = _new_run()
        s0 = run.current_observed_state_id
        _advance(run, "first", "r_0001")
        _advance(run, "second", "r_0002")

        run.rewind(steps=2)
        assert run.current_observed_state_id == s0

    def test_rewind_steps_past_root_raises(self):
        run = _new_run()
        with pytest.raises(ValueError, match="root"):
            run.rewind(steps=1)

    def test_rewind_to_non_ancestor_raises(self):
        """Rewind only walks the active path, not sibling branches."""
        run = _new_run()
        s0 = run.current_observed_state_id
        s1 = _advance(run, "first", "r_0001")
        # Now create a sibling branch off s0 by rewinding and observing again.
        run.rewind(to_state_id=s0)
        _advance(run, "alt", "r_0002")

        # current is now s1_alt; s1 (the other branch) is NOT an ancestor.
        with pytest.raises(ValueError, match="not an ancestor"):
            run.rewind(to_state_id=s1)

    def test_rewind_requires_exactly_one_target(self):
        run = _new_run()
        with pytest.raises(ValueError, match="exactly one"):
            run.rewind()
        with pytest.raises(ValueError, match="exactly one"):
            run.rewind(to_state_id="s_obs_0000", steps=1)

    def test_rewind_self_is_noop(self):
        run = _new_run()
        s0 = run.current_observed_state_id
        old_dag_id = run.prediction_dag.dag_id
        run.rewind(to_state_id=s0)
        assert run.current_observed_state_id == s0
        # prediction dag is not refreshed for a no-op
        assert run.prediction_dag.dag_id == old_dag_id

    def test_rewind_rejects_predicted_state(self):
        run = _new_run()
        with pytest.raises(KeyError, match="not an observed state|unknown"):
            run.rewind(to_state_id=run.prediction_dag.root_predicted_state_id)


class TestCliRewind:
    """CLI surface for rewind."""

    def _setup(self, store_dir: Path) -> tuple[str, str, str]:
        result = run_init_command(
            requirement_id="req_test",
            target_type="code",
            target_id="t",
            run_id=None,
            store_dir=str(store_dir),
        )
        run_id = result["run_id"]
        plan = run_plan_command(
            run_id=run_id, planner="default", max_plans=1, store_dir=str(store_dir),
        )["plans"][0]
        run_observe_command(
            run_id=run_id,
            plan_id=plan["plan_id"],
            result_id="r_0001",
            status="completed",
            artifacts=[], raw_outputs=[], logs=[], metrics={}, errors=[],
            store_dir=str(store_dir),
        )
        store = JsonlRunStore(store_dir)
        s_after = store.load_run(run_id).current_observed_state_id
        return run_id, plan["from_observed_state_id"], s_after

    def test_run_rewind_command_to_state(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, s_before, _ = self._setup(store_dir)

            result = run_rewind_command(
                run_id=run_id,
                to_state=s_before,
                steps=None,
                reason=None,
                store_dir=str(store_dir),
            )
            assert result["state"]["state_id"] == s_before
            store = JsonlRunStore(store_dir)
            assert store.load_run(run_id).current_observed_state_id == s_before

    def test_run_rewind_command_steps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, s_before, _ = self._setup(store_dir)

            result = run_rewind_command(
                run_id=run_id,
                to_state=None,
                steps=1,
                reason="undo a bad observe",
                store_dir=str(store_dir),
            )
            assert result["state"]["state_id"] == s_before
            assert result["reason"] == "undo a bad observe"

    def test_cli_parse_args_rewind_to_state(self):
        args = parse_args(["rewind", "--to-state", "s_obs_0000"])
        assert args.command == "rewind"
        assert args.to_state == "s_obs_0000"
        assert args.steps is None

    def test_cli_parse_args_rewind_requires_target(self):
        with pytest.raises(SystemExit):
            parse_args(["rewind"])

    def test_cli_parse_args_rewind_target_is_mutex(self):
        with pytest.raises(SystemExit):
            parse_args(["rewind", "--to-state", "s_obs_0000", "--steps", "1"])

    def test_main_rewind_prints_state_json(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, s_before, _ = self._setup(store_dir)

            exit_code = main([
                "rewind",
                "--run", run_id,
                "--steps", "1",
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            state = json.loads(captured.out)
            assert state["state_id"] == s_before
