"""Tests for the stag migrate command."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

import pytest

from stag.cli.commands.init import run_init_command
from stag.cli.commands.plan import run_plan_command
from stag.cli.commands.observe import run_observe_command
from stag.cli.commands.migrate import run_migrate_command
from stag.cli.main import parse_args
from stag.storage.jsonl import JsonlRunStore
from stag.storage.sqlite import SqliteRunStore


def _init_jsonl_run(store_dir: str, run_id: str = "run_test") -> str:
    """Create a jsonl-backed run with a plan and observation."""
    run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t1",
        run_id=run_id,
        store_dir=store_dir,
    )
    it = run_plan_command(
        run_id=run_id,
        input_node_ids=["n_0000"],
        action_type="analysis",
        intent="test intent",
        store_dir=store_dir,
    )["input_transition"]
    run_observe_command(
        run_id=run_id,
        input_transition_id=it["input_transition_id"],
        status="completed",
        artifacts=None,
        raw_outputs=None,
        logs=None,
        metrics=None,
        errors=None,
        store_dir=store_dir,
    )
    return run_id


class TestMigrateSingleRun:
    def test_single_run_creates_db(self):
        with tempfile.TemporaryDirectory() as td:
            rid = _init_jsonl_run(td)
            result = run_migrate_command(
                to="sqlite", store_dir=td, run_id=rid, all_runs=False, force=False
            )
            assert result == {"migrated": [rid], "skipped": [], "failed": []}
            assert (Path(td) / rid / "run.db").exists()

    def test_single_run_data_equivalent(self):
        with tempfile.TemporaryDirectory() as td:
            rid = _init_jsonl_run(td)
            src = JsonlRunStore(td).load_run(rid)
            run_migrate_command(
                to="sqlite", store_dir=td, run_id=rid, all_runs=False, force=False
            )
            dst = SqliteRunStore(td).load_run(rid)

            assert dst.run_id == src.run_id
            assert dst.requirement.requirement_id == src.requirement.requirement_id
            assert dst.requirement.target_type == src.requirement.target_type
            assert dst.requirement.target_id == src.requirement.target_id
            assert set(dst.run_graph.nodes) == set(src.run_graph.nodes)
            assert set(dst.run_graph.input_transitions) == set(src.run_graph.input_transitions)
            assert set(dst.run_graph.output_transitions) == set(src.run_graph.output_transitions)
            assert set(dst.run_graph.payloads) == set(src.run_graph.payloads)
            assert set(dst.run_graph.views) == set(src.run_graph.views)
            assert dict(dst._counters) == dict(src._counters)


class TestMigrateAllRuns:
    def test_all_migrates_both(self):
        with tempfile.TemporaryDirectory() as td:
            rid1 = _init_jsonl_run(td, run_id="run_a")
            rid2 = _init_jsonl_run(td, run_id="run_b")
            result = run_migrate_command(
                to="sqlite", store_dir=td, run_id=None, all_runs=True, force=False
            )
            assert set(result["migrated"]) == {rid1, rid2}
            assert result["skipped"] == []
            assert result["failed"] == []
            assert (Path(td) / rid1 / "run.db").exists()
            assert (Path(td) / rid2 / "run.db").exists()


class TestMigrateSkipAndForce:
    def test_skip_existing_db(self):
        with tempfile.TemporaryDirectory() as td:
            rid = _init_jsonl_run(td)
            run_migrate_command(
                to="sqlite", store_dir=td, run_id=rid, all_runs=False, force=False
            )
            # Second call: should skip
            result = run_migrate_command(
                to="sqlite", store_dir=td, run_id=rid, all_runs=False, force=False
            )
            assert result == {"migrated": [], "skipped": [rid], "failed": []}

    def test_force_overwrites_existing_db(self):
        with tempfile.TemporaryDirectory() as td:
            rid = _init_jsonl_run(td)
            run_migrate_command(
                to="sqlite", store_dir=td, run_id=rid, all_runs=False, force=False
            )
            # Force should succeed and report migrated
            result = run_migrate_command(
                to="sqlite", store_dir=td, run_id=rid, all_runs=False, force=True
            )
            assert result == {"migrated": [rid], "skipped": [], "failed": []}
            assert (Path(td) / rid / "run.db").exists()


class TestMigrateSkipNonJsonlRun:
    def test_skip_run_without_nodes_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            run_dir = Path(td) / "ghost_run"
            run_dir.mkdir()
            # Write only run.json (no nodes.jsonl) so list_runs would find it
            import json
            (run_dir / "run.json").write_text(
                json.dumps(
                    {
                        "run_id": "ghost_run",
                        "requirement": {
                            "requirement_id": "r",
                            "target_type": "task",
                            "target_id": "t",
                        },
                        "counters": {},
                    }
                )
            )
            result = run_migrate_command(
                to="sqlite", store_dir=td, run_id="ghost_run", all_runs=False, force=False
            )
            assert result["skipped"] == ["ghost_run"]
            assert result["migrated"] == []


class TestMigrateArgparseValidation:
    def test_run_and_all_mutually_exclusive(self):
        with pytest.raises(SystemExit):
            parse_args(["migrate", "--to", "sqlite", "--run", "r1", "--all"])

    def test_neither_run_nor_all_required(self):
        with pytest.raises(SystemExit):
            parse_args(["migrate", "--to", "sqlite"])

    def test_invalid_to_choice(self):
        with pytest.raises(SystemExit):
            parse_args(["migrate", "--to", "jsonl", "--run", "r1"])
