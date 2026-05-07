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
from optagent.core.schema.results import ActionResult
from optagent.storage.jsonl import JsonlRunStore


def _new_run(run_id: str = "r"):
    return optagent.init(
        Requirement(requirement_id="req_test", target_type="code", target_id="t"),
        run_id=run_id,
    )


def _advance(handle, plan_intent: str, result_id: str) -> tuple[str, str]:
    """Helper: plan + observe → returns (new_state_id, observed_transition_id)."""
    plan = handle.plan(intent=plan_intent)[0]
    observed = handle.observe(
        plan.plan_id,
        ActionResult(
            result_id=result_id,
            execution_plan_id=plan.plan_id,
            status="completed",
        ),
    )
    return handle.current_observed_state_id, observed.transition_id


class TestRunHandleRewind:
    """Core API: RunHandle.rewind cuts a transition and moves current to its source."""

    def test_rewind_cuts_transition_and_moves_current(self):
        run = _new_run()
        s0 = run.current_observed_state_id
        _, t1 = _advance(run, "first", "r_0001")

        new_state = run.rewind(t1, reason="bad observe")

        assert new_state.state_id == s0
        assert run.current_observed_state_id == s0
        assert t1 in run.trace_dag.cut_transition_ids()

    def test_rewind_appends_one_cut(self):
        run = _new_run()
        _, t1 = _advance(run, "first", "r_0001")
        run.rewind(t1, reason="undo")

        assert len(run.trace_dag.cuts) == 1
        cut = next(iter(run.trace_dag.cuts.values()))
        assert cut.cut_transition_id == t1
        assert cut.reason == "undo"

    def test_rewind_far_back_cuts_only_target_transition(self):
        """Cutting a transition near the root records only that one edge."""
        run = _new_run()
        s0 = run.current_observed_state_id
        s1, t1 = _advance(run, "a", "r_0001")
        s2, _ = _advance(run, "b", "r_0002")
        s3, _ = _advance(run, "c", "r_0003")

        run.rewind(t1)

        assert len(run.trace_dag.cuts) == 1
        assert run.trace_dag.cut_transition_ids() == {t1}
        # Downstream states are derived as cut.
        assert run.trace_dag.cut_state_ids() == {s1, s2, s3}
        assert run.current_observed_state_id == s0

    def test_rewind_does_not_delete_history(self):
        run = _new_run()
        _advance(run, "first", "r_0001")
        _, t2 = _advance(run, "second", "r_0002")
        nodes_before = set(run.trace_dag.nodes)
        plans_before = set(run.trace_dag.execution_plans)
        transitions_before = set(run.trace_dag.transitions)

        run.rewind(t2)

        assert set(run.trace_dag.nodes) == nodes_before
        assert set(run.trace_dag.execution_plans) == plans_before
        assert set(run.trace_dag.transitions) == transitions_before

    def test_rewind_refreshes_prediction_dag(self):
        run = _new_run()
        _, t1 = _advance(run, "first", "r_0001")
        old_dag_id = run.prediction_dag.dag_id

        run.rewind(t1)

        assert run.prediction_dag.anchor_observed_state_id == run.current_observed_state_id
        assert run.prediction_dag.dag_id != old_dag_id

    def test_rewind_unknown_transition_raises(self):
        run = _new_run()
        with pytest.raises(KeyError):
            run.rewind("t_obs_9999")

    def test_rewind_off_active_path_raises(self):
        """A transition on a sibling branch is not 'on the active path back'.

        Build two parallel branches off s0 by planning twice from it.
        The first transition is alive but unreachable from current.
        """
        run = _new_run()
        s0 = run.current_observed_state_id
        _, t1 = _advance(run, "branch a", "r_0001")
        # Plan again from s0 directly (not from current), then observe.
        plan_b = run.plan(state_id=s0, intent="branch b")[0]
        run.observe(
            plan_b.plan_id,
            ActionResult(
                result_id="r_0002",
                execution_plan_id=plan_b.plan_id,
                status="completed",
            ),
        )
        # current is now on branch B; t1 is alive but on branch A.
        assert t1 not in run.trace_dag.cut_transition_ids()
        with pytest.raises(ValueError, match="not on the active path"):
            run.rewind(t1)

    def test_rewind_already_cut_transition_raises(self):
        run = _new_run()
        _, t1 = _advance(run, "first", "r_0001")
        run.rewind(t1)
        # Try to cut the same transition again from a different branch.
        _advance(run, "alt", "r_0002")
        with pytest.raises(ValueError, match="already cut"):
            run.rewind(t1)

    def test_repeated_rewinds_accumulate_cuts(self):
        run = _new_run()
        s0 = run.current_observed_state_id
        _, t1 = _advance(run, "first", "r_0001")
        run.rewind(t1)
        _, t2 = _advance(run, "second", "r_0002")
        run.rewind(t2)

        assert len(run.trace_dag.cuts) == 2
        cut_tids = run.trace_dag.cut_transition_ids()
        assert cut_tids == {t1, t2}
        assert run.current_observed_state_id == s0

    def test_cut_does_not_modify_existing_records(self):
        run = _new_run()
        _, t1 = _advance(run, "first", "r_0001")

        nodes_before = {sid: run.trace_dag.nodes[sid] for sid in run.trace_dag.nodes}
        trans_before = dict(run.trace_dag.transitions)
        plans_before = dict(run.trace_dag.execution_plans)

        run.rewind(t1)

        for sid, node in nodes_before.items():
            assert run.trace_dag.nodes[sid] is node
        for tid, t in trans_before.items():
            assert run.trace_dag.transitions[tid] is t
        for pid, p in plans_before.items():
            assert run.trace_dag.execution_plans[pid] is p


class TestStorageRoundtrip:
    def test_cut_persists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlRunStore(Path(tmpdir))
            run = _new_run("persist_run")
            _, t1 = _advance(run, "a", "r_0001")
            run.rewind(t1, reason="undo")
            store.save_run(run)

            loaded = store.load_run("persist_run")
            assert len(loaded.trace_dag.cuts) == 1
            cut = next(iter(loaded.trace_dag.cuts.values()))
            assert cut.cut_transition_id == t1
            assert cut.reason == "undo"


class TestCliRewind:
    """CLI surface for rewind."""

    def _setup(self, store_dir: Path) -> tuple[str, str, str]:
        """Returns (run_id, source_state_id, observed_transition_id)."""
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
        observed = run_observe_command(
            run_id=run_id,
            plan_id=plan["plan_id"],
            result_id="r_0001",
            status="completed",
            artifacts=[], raw_outputs=[], logs=[], metrics={}, errors=[],
            store_dir=str(store_dir),
        )
        return run_id, plan["from_observed_state_id"], observed["transition"]["transition_id"]

    def test_run_rewind_command(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, source, t1 = self._setup(store_dir)

            result = run_rewind_command(
                run_id=run_id,
                transition_id=t1,
                reason="undo bad observe",
                store_dir=str(store_dir),
            )
            assert result["state"]["state_id"] == source
            assert result["cut"]["cut_transition_id"] == t1
            assert result["cut"]["reason"] == "undo bad observe"

            # Storage retained the cut.
            loaded = JsonlRunStore(store_dir).load_run(run_id)
            assert loaded.current_observed_state_id == source
            assert t1 in loaded.trace_dag.cut_transition_ids()

    def test_cli_parse_args_rewind(self):
        args = parse_args(["rewind", "t_obs_0001", "--reason", "oops"])
        assert args.command == "rewind"
        assert args.transition_id == "t_obs_0001"
        assert args.reason == "oops"

    def test_cli_parse_args_rewind_requires_transition(self):
        with pytest.raises(SystemExit):
            parse_args(["rewind"])

    def test_main_rewind_prints_state_json(self, capsys):
        with tempfile.TemporaryDirectory() as tmpdir:
            store_dir = Path(tmpdir) / "runs"
            run_id, source, t1 = self._setup(store_dir)

            exit_code = main([
                "rewind", t1,
                "--run", run_id,
                "--store-dir", str(store_dir),
            ])
            assert exit_code == 0
            captured = capsys.readouterr()
            state = json.loads(captured.out)
            assert state["state_id"] == source
