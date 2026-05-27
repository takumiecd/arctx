"""Tests for arctx show transition with --history flag."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import arctx as arctx
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.show import run_show_command
from arctx_cli.context import resolve_store
from arctx.core.schema.graph import Node, Transition
from arctx.core.schema.payloads import TransitionPayload
from arctx.ext.git.payloads import DiffSummary, GitChangePayload
from arctx.core.schema.requirements import Requirement


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init_run(td: str, run_id: str = "run_show") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(td),
        extensions=["git"],
        no_hooks=True,
    )


def _make_handle_with_two_git_payloads(td: str, run_id: str = "run_show"):
    """Create a run with one transition and two GitChangePayloads appended."""
    store = resolve_store(_store_dir(td))
    handle = store.load_run(run_id)

    # Create a transition with dry_run commit.
    handle.ensure_work_session(user_id="user", work_session_id="ws")
    t = handle.git.commit(
        message="initial",
        branch="main",
        user_id="user",
        work_session_id="ws",
        head_commit="sha_v1",
        dry_run=True,
    )

    # Manually append a second GitChangePayload (simulating amend).
    p2 = GitChangePayload(
        payload_id=handle._next_id("pl"),
        target_id=t.transition_id,
        branch="main",
        head_commit="sha_v2",
        diff_summary=DiffSummary(1, 2, 0),
    )
    handle.run_graph.attach_payload(p2)

    store.save_run(handle)
    return t.transition_id


class TestShowTransitionDefault:
    def test_git_change_field_present(self, tmp_path):
        td = str(tmp_path)
        _init_run(td)
        t_id = _make_handle_with_two_git_payloads(td)

        result = run_show_command(
            run_id="run_show",
            node_id=None,
            transition_id=t_id,
            payload_id=None,
            with_payloads=False,
            outputs=False,
            history=False,
            store_dir=_store_dir(td),
        )

        assert "git_change" in result
        assert result["git_change"] is not None

    def test_default_shows_latest_sha(self, tmp_path):
        td = str(tmp_path)
        _init_run(td)
        t_id = _make_handle_with_two_git_payloads(td)

        result = run_show_command(
            run_id="run_show",
            node_id=None,
            transition_id=t_id,
            payload_id=None,
            with_payloads=False,
            outputs=False,
            history=False,
            store_dir=_store_dir(td),
        )

        assert result["git_change"]["head_commit"] == "sha_v2"

    def test_history_flag_shows_all(self, tmp_path):
        td = str(tmp_path)
        _init_run(td)
        t_id = _make_handle_with_two_git_payloads(td)

        result = run_show_command(
            run_id="run_show",
            node_id=None,
            transition_id=t_id,
            payload_id=None,
            with_payloads=False,
            outputs=False,
            history=True,
            store_dir=_store_dir(td),
        )

        assert "git_change_history" in result
        assert len(result["git_change_history"]) == 2
        shas = [p["head_commit"] for p in result["git_change_history"]]
        assert shas == ["sha_v1", "sha_v2"]

    def test_no_git_change_returns_none(self, tmp_path):
        td = str(tmp_path)
        _init_run(td)

        store = resolve_store(_store_dir(td))
        handle = store.load_run("run_show")
        # Create a transition without GitChangePayload (use a generic payload).
        dummy_payload = TransitionPayload(
            payload_id="pl_dummy",
            target_id="__placeholder__",
            type="note",
        )
        t = handle.transition(
            input_node_ids=(handle.root_node_id,),
            payload=dummy_payload,
        )
        store.save_run(handle)

        result = run_show_command(
            run_id="run_show",
            node_id=None,
            transition_id=t.transition_id,
            payload_id=None,
            with_payloads=False,
            outputs=False,
            history=False,
            store_dir=_store_dir(td),
        )

        assert result["git_change"] is None

    def test_history_flag_empty_when_no_git_change(self, tmp_path):
        td = str(tmp_path)
        _init_run(td)

        store = resolve_store(_store_dir(td))
        handle = store.load_run("run_show")
        dummy_payload = TransitionPayload(
            payload_id="pl_dummy2",
            target_id="__placeholder__",
            type="note",
        )
        t = handle.transition(
            input_node_ids=(handle.root_node_id,),
            payload=dummy_payload,
        )
        store.save_run(handle)

        result = run_show_command(
            run_id="run_show",
            node_id=None,
            transition_id=t.transition_id,
            payload_id=None,
            with_payloads=False,
            outputs=False,
            history=True,
            store_dir=_store_dir(td),
        )

        assert result["git_change_history"] == []
