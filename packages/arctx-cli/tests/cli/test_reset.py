"""Integration tests for arctx reset CLI.

These tests use the handle API directly (with dry_run=True) to set up arctx
state, then call run_reset_command to verify persistence.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from arctx_cli.commands.init import run_init_command
from arctx_cli.ext.git.reset import run_reset_command
from arctx_cli.context import resolve_store
from arctx.core.cuts import is_inactive_step
from arctx.core.schema.work_helpers import RESET_EVENT, LANE_POINTER_EVENT, latest_lane_pointer


def _store_dir(tmp_path: Path) -> str:
    return str(tmp_path / "arctx_home" / "runs")


def _init_arctx(tmp_path: Path, run_id: str = "run_test") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
        extensions=["git"],
        no_hooks=True,
    )


def _build_chain(handle, length: int, user_id: str = "alice", ws_id: str = "ws") -> list[dict]:
    """Build a commit chain in handle and return list of {step_id, output_node_id}."""
    handle.ensure_lane(user_id=user_id, lane_id=ws_id)
    results = []
    for i in range(length):
        t = handle.git.commit(
            message=f"commit {i + 1}",
            branch="main",
            user_id=user_id,
            lane_id=ws_id,
            head_commit=f"sha_{i + 1}",
            dry_run=True,
        )
        results.append({"step_id": t.step_id, "output_node_id": t.output_node_id})
    return results


class TestResetCLIIntegration:
    def test_hard_reset_cuts_steps(self, tmp_path):
        """arctx reset --hard <n1> cuts t2/t3 and rolls back current."""
        _init_arctx(tmp_path, run_id="run_rs")
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_rs")

        commits = _build_chain(handle, 3, user_id="alice", ws_id="ws_rs")
        store.save_run(handle)

        r1, r2, r3 = commits

        # Reset to n1 (output of r1).
        result = run_reset_command(
            to_node_id=r1["output_node_id"],
            to_sha=None,
            mode="hard",
            branch=None,
            run_id="run_rs",
            store_dir=_store_dir(tmp_path),
            user_id="alice",
            lane_id="ws_rs",
            dry_run=True,
        )

        assert result["to_node_id"] == r1["output_node_id"]
        assert r2["step_id"] in result["discarded_step_ids"]
        assert r3["step_id"] in result["discarded_step_ids"]

        # Reload and verify.
        handle2 = store.load_run("run_rs")
        assert is_inactive_step(handle2.run_graph, r2["step_id"])
        assert is_inactive_step(handle2.run_graph, r3["step_id"])

    def test_hard_reset_updates_lane_pointer(self, tmp_path):
        _init_arctx(tmp_path, run_id="run_sp")
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_sp")

        commits = _build_chain(handle, 2, user_id="alice", ws_id="ws_sp")
        store.save_run(handle)

        r1, r2 = commits

        run_reset_command(
            to_node_id=r1["output_node_id"],
            to_sha=None,
            mode="hard",
            branch=None,
            run_id="run_sp",
            store_dir=_store_dir(tmp_path),
            user_id="alice",
            lane_id="ws_sp",
            dry_run=True,
        )

        handle2 = store.load_run("run_sp")
        sp = latest_lane_pointer(handle2.run_graph, "ws_sp")
        assert sp is not None
        assert r1["output_node_id"] in sp.data["current_node_ids"]

    def test_mixed_mode_no_cut(self, tmp_path):
        """mode=mixed does not cut discarded steps."""
        _init_arctx(tmp_path, run_id="run_mx")
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_mx")

        commits = _build_chain(handle, 2, user_id="alice", ws_id="ws_mx")
        store.save_run(handle)

        r1, r2 = commits

        run_reset_command(
            to_node_id=r1["output_node_id"],
            to_sha=None,
            mode="mixed",
            branch=None,
            run_id="run_mx",
            store_dir=_store_dir(tmp_path),
            user_id="alice",
            lane_id="ws_mx",
            dry_run=True,
        )

        handle2 = store.load_run("run_mx")
        assert not is_inactive_step(handle2.run_graph, r2["step_id"])

    def test_soft_mode_no_cut(self, tmp_path):
        """mode=soft does not cut discarded steps."""
        _init_arctx(tmp_path, run_id="run_sf")
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_sf")

        commits = _build_chain(handle, 2, user_id="bob", ws_id="ws_sf")
        store.save_run(handle)

        r1, r2 = commits

        run_reset_command(
            to_node_id=r1["output_node_id"],
            to_sha=None,
            mode="soft",
            branch=None,
            run_id="run_sf",
            store_dir=_store_dir(tmp_path),
            user_id="bob",
            lane_id="ws_sf",
            dry_run=True,
        )

        handle2 = store.load_run("run_sf")
        assert not is_inactive_step(handle2.run_graph, r2["step_id"])

    def test_reset_event_recorded_in_store(self, tmp_path):
        _init_arctx(tmp_path, run_id="run_ev")
        store = resolve_store(_store_dir(tmp_path))
        handle = store.load_run("run_ev")

        commits = _build_chain(handle, 2, user_id="carol", ws_id="ws_ev")
        store.save_run(handle)

        r1, r2 = commits

        run_reset_command(
            to_node_id=r1["output_node_id"],
            to_sha=None,
            mode="hard",
            branch=None,
            run_id="run_ev",
            store_dir=_store_dir(tmp_path),
            user_id="carol",
            lane_id="ws_ev",
            dry_run=True,
        )

        handle2 = store.load_run("run_ev")
        reset_events = [
            e for e in handle2.run_graph.work_events if e.event_type == RESET_EVENT
        ]
        assert len(reset_events) == 1
        assert reset_events[0].data["to_node_id"] == r1["output_node_id"]
        assert reset_events[0].data["mode"] == "hard"
