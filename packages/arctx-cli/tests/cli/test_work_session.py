"""Tests for work-session CLI helpers."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.step import run_step_command
from arctx_cli.commands.work_session import (
    run_work_session_env_command,
    run_work_session_list_command,
    run_work_session_start_command,
)


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init(td: str) -> dict:
    return run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_ws",
        store_dir=_store_dir(td),
    )


def test_start_creates_named_work_session():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        result = run_work_session_start_command(
            run_id="run_ws",
            work_session_id="ws_a",
            user_id="user_a",
            store_dir=_store_dir(td),
        )

        assert result["work_session_id"] == "ws_a"
        listed = run_work_session_list_command(run_id="run_ws", store_dir=_store_dir(td))
        assert [s["work_session_id"] for s in listed["work_sessions"]] == ["ws_a"]


def test_env_new_creates_unique_work_session():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        result = run_work_session_env_command(
            run_id="run_ws",
            work_session_id=None,
            create_new=True,
            user_id="user",
            store_dir=_store_dir(td),
        )

        assert result["work_session_id"].startswith("ws_")
        listed = run_work_session_list_command(run_id="run_ws", store_dir=_store_dir(td))
        assert listed["work_sessions"][0]["work_session_id"] == result["work_session_id"]


def test_env_requires_id_without_new():
    with pytest.raises(ValueError, match="work_session_id is required"):
        run_work_session_env_command(
            run_id="run_ws",
            work_session_id=None,
            create_new=False,
            user_id="user",
            store_dir="/tmp/unused",
        )


def test_two_fixed_work_sessions_keep_events_separate():
    with tempfile.TemporaryDirectory() as td:
        init_result = _init(td)
        root_id = init_result["root_node_id"]
        run_work_session_start_command(
            run_id="run_ws",
            work_session_id="ws_a",
            user_id="worker",
            store_dir=_store_dir(td),
        )
        run_work_session_start_command(
            run_id="run_ws",
            work_session_id="ws_b",
            user_id="worker",
            store_dir=_store_dir(td),
        )

        run_step_command(
            run_id="run_ws",
            input_node_ids=[root_id],
            payload_type="suggestion",
            content={"proposal": "a"},
            store_dir=_store_dir(td),
            user_id="worker",
            work_session_id="ws_a",
        )
        run_step_command(
            run_id="run_ws",
            input_node_ids=[root_id],
            payload_type="suggestion",
            content={"proposal": "b"},
            store_dir=_store_dir(td),
            user_id="worker",
            work_session_id="ws_b",
        )

        from arctx_cli.context import resolve_store

        handle = resolve_store(_store_dir(td)).load_run("run_ws")
        event_sessions = [event.work_session_id for event in handle.run_graph.work_events]
        assert event_sessions == ["ws_a", "ws_b"]
