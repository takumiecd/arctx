"""Integration tests for S9: parallel-session guard in CLI commands.

Tests verify that:
1. stag commit (via run_commit_command) raises ParallelSessionConflict when
   another session has advanced the branch tip.
2. After updating to the correct tip (stag use equivalent), commit succeeds.
"""

from __future__ import annotations

import pytest

from stag_cli.ext.git.commit import run_commit_command
from stag_cli.commands.init import run_init_command
from stag_api.ext.git.verbs._forward_transition import ParallelSessionConflict
from stag_api.core.schema.work_helpers import make_session_pointer_event


def _store_dir(tmp_path) -> str:
    return str(tmp_path / "stag_home" / "runs")


def _init_run(tmp_path, run_id: str = "run_guard_test") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
        extensions=["git"],
    )


class TestCommitGuardCLI:
    def test_session_b_commit_fails_after_session_a_advances(self, tmp_path):
        """session B gets ParallelSessionConflict if session A already committed."""
        sd = _store_dir(tmp_path)
        _init_run(tmp_path, run_id="run_guard_cli")

        # Session A commits successfully.
        result_a = run_commit_command(
            message="session A first commit",
            branch="main",
            run_id="run_guard_cli",
            store_dir=sd,
            user_id="alice",
            work_session_id="ws_a",
            dry_run=True,
            head_commit="sha_a1",
        )
        assert "transition_id" in result_a

        # Session B tries to commit — its pointer was never updated, so it's
        # still at root while the branch tip is at t_a.output_node_id.
        # Importantly, ws_b has no SessionPointerEvent → current = (root,).
        with pytest.raises(ParallelSessionConflict):
            run_commit_command(
                message="session B conflict commit",
                branch="main",
                run_id="run_guard_cli",
                store_dir=sd,
                user_id="bob",
                work_session_id="ws_b",
                dry_run=True,
                head_commit="sha_b1",
            )

    def test_session_b_commit_succeeds_after_adopting_tip(self, tmp_path):
        """session B can commit once it adopts the current branch tip."""
        from stag_cli.context import resolve_store  # noqa: PLC0415

        sd = _store_dir(tmp_path)
        _init_run(tmp_path, run_id="run_adopt_tip")

        # Session A commits.
        result_a = run_commit_command(
            message="session A commit",
            branch="main",
            run_id="run_adopt_tip",
            store_dir=sd,
            user_id="alice",
            work_session_id="ws_a",
            dry_run=True,
            head_commit="sha_a",
        )
        tip_node = result_a["output_node_id"]

        # Simulate session B adopting the tip via stag use <tip_node>:
        # inject a SessionPointerEvent pointing to the new tip.
        store = resolve_store(sd)
        handle = store.load_run("run_adopt_tip")
        handle.ensure_work_session(user_id="bob", work_session_id="ws_b")
        sp_event = make_session_pointer_event(
            event_id=handle._next_id("we"),
            run_id=handle.run_id,
            work_session_id="ws_b",
            user_id="bob",
            current_node_ids=(tip_node,),
            current_branch="main",
        )
        handle.run_graph.add_work_event(sp_event)
        store.save_run(handle)

        # Session B can now commit successfully.
        result_b = run_commit_command(
            message="session B after adopting tip",
            branch="main",
            run_id="run_adopt_tip",
            store_dir=sd,
            user_id="bob",
            work_session_id="ws_b",
            dry_run=True,
            head_commit="sha_b",
        )
        assert "transition_id" in result_b
        assert result_b["output_node_id"] != tip_node

    def test_first_commit_on_branch_no_guard(self, tmp_path):
        """First commit on a fresh branch (no BranchTipEvent) always passes."""
        sd = _store_dir(tmp_path)
        _init_run(tmp_path, run_id="run_first_branch")

        result = run_commit_command(
            message="very first commit",
            branch="new-feature",
            run_id="run_first_branch",
            store_dir=sd,
            user_id="alice",
            work_session_id="ws_a",
            dry_run=True,
            head_commit="sha_first",
        )
        assert "transition_id" in result
