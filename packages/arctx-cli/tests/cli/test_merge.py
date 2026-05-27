"""Integration tests for arctx merge CLI."""

from __future__ import annotations

from pathlib import Path

import pytest

from arctx_cli.commands.init import run_init_command
from arctx_cli.context import resolve_store
from arctx.core.schema.work_helpers import make_session_pointer_event


def _store_dir(tmp_path: Path) -> str:
    return str(tmp_path / "arctx_home" / "runs")


def _init_arctx(tmp_path: Path, run_id: str = "run_merge_cli") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
        extensions=["git"],
        no_hooks=True,
    )


def _build_two_branch_run(handle, ws_main: str = "ws_main", ws_feat: str = "ws_feat"):
    """Commit on main and feature branches; return (n_main, n_feat)."""
    handle.ensure_work_session(user_id="user", work_session_id=ws_main)
    handle.ensure_work_session(user_id="user", work_session_id=ws_feat)
    root_id = handle.root_node_id

    t_main = handle.git.commit(
        message="main commit", branch="main",
        user_id="user", work_session_id=ws_main,
        head_commit="sha_main", dry_run=True,
    )
    n_main = t_main.output_node_id

    # Reset feature session to root.
    sp = make_session_pointer_event(
        event_id=handle._next_id("we"),
        run_id=handle.run_id,
        work_session_id=ws_feat,
        user_id="user",
        current_node_ids=(root_id,),
        current_branch="feature",
    )
    handle.run_graph.add_work_event(sp)

    t_feat = handle.git.commit(
        message="feature commit", branch="feature",
        user_id="user", work_session_id=ws_feat,
        head_commit="sha_feat", dry_run=True,
    )
    n_feat = t_feat.output_node_id
    return n_main, n_feat


class TestMergeCLIIntegration:
    def test_merge_records_multi_input_transition(self, tmp_path):
        """run_merge_command creates a multi-input transition with MergePayload."""
        from arctx_cli.ext.git.merge import run_merge_command
        from arctx.ext.git.payloads import MergePayload

        _init_arctx(tmp_path, run_id="run_mg1")
        sd = _store_dir(tmp_path)

        store = resolve_store(sd)
        handle = store.load_run("run_mg1")
        n_main, n_feat = _build_two_branch_run(handle)
        store.save_run(handle)

        result = run_merge_command(
            other=f"node:{n_feat}",
            message="merge feature",
            branch="main",
            run_id="run_mg1",
            store_dir=sd,
            user_id="user",
            work_session_id="ws_main",
            join=False,
            dry_run=True,
            head_commit="sha_merged_1",
        )

        assert "transition_id" in result
        assert n_main in result["input_node_ids"]
        assert n_feat in result["input_node_ids"]
        assert result["merge_payload_type"] == "merge"

        handle2 = resolve_store(sd).load_run("run_mg1")
        merge_pls = handle2.run_graph.payloads_for_transition(
            result["transition_id"], payload_type="merge"
        )
        assert len(merge_pls) == 1
        assert isinstance(merge_pls[0], MergePayload)

    def test_join_records_join_payload(self, tmp_path):
        """arctx merge --join records JoinPayload not MergePayload."""
        from arctx_cli.ext.git.merge import run_merge_command
        from arctx.core.schema.payloads import JoinPayload

        _init_arctx(tmp_path, run_id="run_join1")
        sd = _store_dir(tmp_path)

        store = resolve_store(sd)
        handle = store.load_run("run_join1")
        n_main, n_feat = _build_two_branch_run(handle)
        store.save_run(handle)

        result = run_merge_command(
            other=f"node:{n_feat}",
            message="join",
            branch="main",
            run_id="run_join1",
            store_dir=sd,
            user_id="user",
            work_session_id="ws_main",
            join=True,
            dry_run=True,
            head_commit="sha_join_1",
        )

        assert result["merge_payload_type"] == "join"

        handle2 = resolve_store(sd).load_run("run_join1")
        join_pls = handle2.run_graph.payloads_for_transition(
            result["transition_id"], payload_type="join"
        )
        assert len(join_pls) == 1
        assert isinstance(join_pls[0], JoinPayload)

        # No MergePayload.
        merge_pls = handle2.run_graph.payloads_for_transition(
            result["transition_id"], payload_type="merge"
        )
        assert len(merge_pls) == 0

    def test_commit_with_merge_flag(self, tmp_path):
        """run_commit_command --merge drives merge via commit CLI."""
        from arctx_cli.ext.git.commit import run_commit_command
        from arctx.ext.git.payloads import MergePayload

        _init_arctx(tmp_path, run_id="run_cm1")
        sd = _store_dir(tmp_path)

        store = resolve_store(sd)
        handle = store.load_run("run_cm1")
        n_main, n_feat = _build_two_branch_run(handle)
        store.save_run(handle)

        result = run_commit_command(
            message="merge feature into main",
            branch="main",
            run_id="run_cm1",
            store_dir=sd,
            user_id="user",
            work_session_id="ws_main",
            merge=f"node:{n_feat}",
            join=False,
            dry_run=True,
            head_commit="sha_cm_merge",
        )

        assert "transition_id" in result
        assert result.get("merge") is not None

        handle2 = resolve_store(sd).load_run("run_cm1")
        t = handle2.run_graph.transitions[result["transition_id"]]
        assert n_main in t.input_node_ids
        assert n_feat in t.input_node_ids

        merge_pls = handle2.run_graph.payloads_for_transition(
            result["transition_id"], payload_type="merge"
        )
        assert len(merge_pls) == 1
        assert isinstance(merge_pls[0], MergePayload)

    def test_merge_by_branch_name(self, tmp_path):
        """run_merge_command resolves branch tip via BranchTipEvent."""
        from arctx_cli.ext.git.merge import run_merge_command

        _init_arctx(tmp_path, run_id="run_brname")
        sd = _store_dir(tmp_path)

        store = resolve_store(sd)
        handle = store.load_run("run_brname")
        n_main, n_feat = _build_two_branch_run(handle)
        store.save_run(handle)

        # Merge by branch name "feature" (auto-detect format).
        result = run_merge_command(
            other="feature",
            message=None,
            branch="main",
            run_id="run_brname",
            store_dir=sd,
            user_id="user",
            work_session_id="ws_main",
            join=False,
            dry_run=True,
            head_commit="sha_br_merge",
        )

        handle2 = resolve_store(sd).load_run("run_brname")
        t = handle2.run_graph.transitions[result["transition_id"]]
        assert n_feat in t.input_node_ids

    def test_merge_graph_has_correct_output_node(self, tmp_path):
        """Output node of merge transition should be new, different from both inputs."""
        from arctx_cli.ext.git.merge import run_merge_command

        _init_arctx(tmp_path, run_id="run_graph_out")
        sd = _store_dir(tmp_path)

        store = resolve_store(sd)
        handle = store.load_run("run_graph_out")
        n_main, n_feat = _build_two_branch_run(handle)
        store.save_run(handle)

        result = run_merge_command(
            other=f"node:{n_feat}",
            message=None,
            branch="main",
            run_id="run_graph_out",
            store_dir=sd,
            user_id="user",
            work_session_id="ws_main",
            join=False,
            dry_run=True,
            head_commit="sha_out",
        )

        assert result["output_node_id"] != n_main
        assert result["output_node_id"] != n_feat
        assert result["output_node_id"] not in result["input_node_ids"]

    def test_merge_unknown_branch_returns_error(self, tmp_path):
        """Merging a nonexistent branch name should raise an exception."""
        from arctx_cli.ext.git.merge import run_merge_command

        _init_arctx(tmp_path, run_id="run_unk")
        sd = _store_dir(tmp_path)

        with pytest.raises(Exception, match="(no BranchTipEvent|cannot resolve)"):
            run_merge_command(
                other="branch:nonexistent",
                message=None,
                branch="main",
                run_id="run_unk",
                store_dir=sd,
                user_id="user",
                work_session_id="ws_main",
                dry_run=True,
                head_commit="sha_unk",
            )

    def test_merge_dump_shows_join_correctly(self, tmp_path):
        """After merge, arctx dump should show the multi-input transition."""
        from arctx_cli.ext.git.merge import run_merge_command

        _init_arctx(tmp_path, run_id="run_dump")
        sd = _store_dir(tmp_path)

        store = resolve_store(sd)
        handle = store.load_run("run_dump")
        n_main, n_feat = _build_two_branch_run(handle)
        store.save_run(handle)

        result = run_merge_command(
            other=f"node:{n_feat}",
            message="merge",
            branch="main",
            run_id="run_dump",
            store_dir=sd,
            user_id="user",
            work_session_id="ws_main",
            join=False,
            dry_run=True,
            head_commit="sha_dump",
        )

        handle2 = resolve_store(sd).load_run("run_dump")
        t = handle2.run_graph.transitions[result["transition_id"]]
        assert len(t.input_node_ids) == 2
