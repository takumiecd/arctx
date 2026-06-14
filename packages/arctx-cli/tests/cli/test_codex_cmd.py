"""Tests for the codex CLI command (hook recording + install)."""

from __future__ import annotations

import io
import json
import os
import tempfile
from pathlib import Path

import pytest

from arctx_cli.ext.codex import (
    build_hooks_config,
    merge_hooks_into_settings,
    run_codex_hook_command,
    run_codex_install_command,
)
from arctx_cli.commands.init import run_init_command
from arctx_cli.context import resolve_store
from arctx_cli.main import main


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init(td: str) -> dict:
    cwd = os.getcwd()
    os.chdir(td)
    try:
        return run_init_command(
            requirement_id="req",
            target_type="task",
            target_id="target",
            run_id="run_codex",
            store_dir=_store_dir(td),
        )
    finally:
        os.chdir(cwd)


def _event(name: str, session_id: str = "s1", **extra) -> dict:
    return {"hook_event_name": name, "session_id": session_id, **extra}


def test_hook_command_records_prompt_and_tool_use():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        prompt = run_codex_hook_command(
            event=_event("UserPromptSubmit", prompt="optimize the kernel"),
            run_id="run_codex",
            store_dir=_store_dir(td),
            user_id="codex",
        )
        tool = run_codex_hook_command(
            event=_event(
                "PostToolUse",
                tool_name="Bash",
                tool_input={"command": "pytest -q"},
                tool_output="ok",
            ),
            run_id="run_codex",
            store_dir=_store_dir(td),
            user_id="codex",
        )

        handle = resolve_store(_store_dir(td)).load_run("run_codex")
        assert prompt["step_id"] in handle.run_graph.steps
        tool_step = handle.run_graph.steps[tool["step_id"]]
        assert tool_step.input_node_ids == (prompt["output_node_id"],)
        assert "ws_codex_s1" in handle.run_graph.work_sessions


def test_hook_command_persists_session_start_metadata():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        result = run_codex_hook_command(
            event=_event(
                "SessionStart",
                transcript_path="/t/a.jsonl",
                source="startup",
                model="gpt-5.5",
            ),
            run_id="run_codex",
            store_dir=_store_dir(td),
            user_id="codex",
        )
        assert result == {"event": "SessionStart", "work_session_id": "ws_codex_s1"}

        handle = resolve_store(_store_dir(td)).load_run("run_codex")
        session = handle.run_graph.work_sessions["ws_codex_s1"]
        assert session.metadata["agent"]["harness"] == "codex"
        assert session.metadata["agent"]["model"] == "gpt-5.5"


def test_hook_command_unknown_run_raises():
    with tempfile.TemporaryDirectory() as td, pytest.raises(KeyError, match="unknown run_id"):
        run_codex_hook_command(
            event=_event("UserPromptSubmit", prompt="x"),
            run_id="missing",
            store_dir=_store_dir(td),
            user_id="u",
        )


def test_hook_cli_is_fail_safe(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.delenv("ARCTX_RUN_ID", raising=False)
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert main(["codex", "hook", "--run", "missing", "--store-dir", _store_dir(td)]) == 0

        monkeypatch.setattr(
            "sys.stdin", io.StringIO(json.dumps(_event("UserPromptSubmit", prompt="x")))
        )
        assert main(["codex", "hook", "--run", "missing", "--store-dir", _store_dir(td)]) == 0

        monkeypatch.setattr(
            "sys.stdin", io.StringIO(json.dumps(_event("UserPromptSubmit", prompt="x")))
        )
        assert (
            main(
                [
                    "codex",
                    "hook",
                    "--strict",
                    "--run",
                    "missing",
                    "--store-dir",
                    _store_dir(td),
                ]
            )
            == 1
        )


def test_hook_cli_records_from_argv(monkeypatch, capsys):
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        monkeypatch.delenv("ARCTX_RUN_ID", raising=False)
        rc = main(
            [
                "codex",
                "hook",
                json.dumps(_event("UserPromptSubmit", prompt="hello")),
                "--run",
                "run_codex",
                "--store-dir",
                _store_dir(td),
            ]
        )
        assert rc == 0
        assert capsys.readouterr().out == ""

        handle = resolve_store(_store_dir(td)).load_run("run_codex")
        assert len(handle.run_graph.steps) == 1


def test_install_writes_hooks_and_is_idempotent():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / ".codex" / "hooks.json"
        first = run_codex_install_command(
            hooks_path=str(path), global_hooks=False, matcher="Bash"
        )
        assert first["changed"] is True
        settings = json.loads(path.read_text(encoding="utf-8"))
        for event in ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop"):
            assert event in settings["hooks"]
        assert settings["hooks"]["PostToolUse"][0]["matcher"] == "Bash"

        second = run_codex_install_command(
            hooks_path=str(path), global_hooks=False, matcher="Bash"
        )
        assert second["changed"] is False
        assert json.loads(path.read_text(encoding="utf-8")) == settings


def test_install_custom_command_and_marker_idempotency():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "hooks.json"
        wrapper = "/repo/scripts/arctx codex hook"
        first = run_codex_install_command(
            hooks_path=str(path), global_hooks=False, matcher="Bash", command=wrapper
        )
        assert first["changed"] is True
        settings = json.loads(path.read_text(encoding="utf-8"))
        assert settings["hooks"]["Stop"][0]["hooks"][0]["command"] == wrapper

        second = run_codex_install_command(
            hooks_path=str(path), global_hooks=False, matcher="Bash"
        )
        assert second["changed"] is False
        assert json.loads(path.read_text(encoding="utf-8")) == settings


def test_install_warns_when_hook_command_missing_from_path():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "hooks.json"
        result = run_codex_install_command(
            hooks_path=str(path),
            global_hooks=False,
            matcher="Bash",
            command="definitely-not-a-real-binary-xyz codex hook",
        )
        assert "not found on PATH" in result["warning"]


def test_install_preserves_existing_hooks():
    existing = {
        "hooks": {
            "PostToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-linter"}]}
            ]
        }
    }
    changed = merge_hooks_into_settings(existing, build_hooks_config("Edit|Write"))
    assert changed is True
    post = existing["hooks"]["PostToolUse"]
    assert post[0]["hooks"][0]["command"] == "my-linter"
    assert any("arctx codex hook" in h["command"] for e in post for h in e["hooks"])
