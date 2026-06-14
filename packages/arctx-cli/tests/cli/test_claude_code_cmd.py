"""Tests for the claude-code CLI command (hook recording + install)."""

from __future__ import annotations

import io
import json
import tempfile
from pathlib import Path

import pytest

from arctx_cli.ext.claude_code import (
    build_hooks_config,
    merge_hooks_into_settings,
    run_claude_code_hook_command,
    run_claude_code_install_command,
)
from arctx_cli.commands.init import run_init_command
from arctx_cli.context import resolve_store
from arctx_cli.main import main


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init(td: str) -> dict:
    return run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_cc",
        store_dir=_store_dir(td),
    )


def _event(name: str, session_id: str = "s1", **extra) -> dict:
    return {"hook_event_name": name, "session_id": session_id, **extra}


def test_hook_command_records_prompt_and_tool_use():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        prompt = run_claude_code_hook_command(
            event=_event("UserPromptSubmit", prompt="optimize the kernel"),
            run_id="run_cc",
            store_dir=_store_dir(td),
            user_id="claude-code",
        )
        tool = run_claude_code_hook_command(
            event=_event(
                "PostToolUse",
                tool_name="Bash",
                tool_input={"command": "pytest -q"},
                tool_output="ok",
            ),
            run_id="run_cc",
            store_dir=_store_dir(td),
            user_id="claude-code",
        )

        handle = resolve_store(_store_dir(td)).load_run("run_cc")
        assert prompt["step_id"] in handle.run_graph.steps
        tool_step = handle.run_graph.steps[tool["step_id"]]
        assert tool_step.input_node_ids == (prompt["output_node_id"],)
        types = [
            p.type
            for p in handle.run_graph.payloads_for_step(tool["step_id"])
        ]
        assert types == ["agent.tool_use"]
        assert "ws_cc_s1" in handle.run_graph.work_sessions


def test_hook_command_persists_session_start_metadata():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        result = run_claude_code_hook_command(
            event=_event(
                "SessionStart",
                transcript_path="/t/a.jsonl",
                source="startup",
                model="claude-fable-5",
            ),
            run_id="run_cc",
            store_dir=_store_dir(td),
            user_id="claude-code",
        )
        assert result == {"event": "SessionStart", "work_session_id": "ws_cc_s1"}

        handle = resolve_store(_store_dir(td)).load_run("run_cc")
        session = handle.run_graph.work_sessions["ws_cc_s1"]
        assert session.metadata["agent"]["harness"] == "claude-code"
        assert session.metadata["agent"]["model"] == "claude-fable-5"
        assert session.metadata["agent"]["source"] == "startup"


def test_hook_command_unknown_run_raises():
    with tempfile.TemporaryDirectory() as td, pytest.raises(KeyError, match="unknown run_id"):
        run_claude_code_hook_command(
            event=_event("UserPromptSubmit", prompt="x"),
            run_id="missing",
            store_dir=_store_dir(td),
            user_id="u",
        )


def test_hook_cli_is_fail_safe(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        monkeypatch.delenv("ARCTX_RUN_ID", raising=False)
        # Broken stdin JSON -> still exit 0.
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        assert main(["claude-code", "hook", "--run", "missing", "--store-dir", _store_dir(td)]) == 0
        # Unknown run -> still exit 0.
        monkeypatch.setattr(
            "sys.stdin", io.StringIO(json.dumps(_event("UserPromptSubmit", prompt="x")))
        )
        assert main(["claude-code", "hook", "--run", "missing", "--store-dir", _store_dir(td)]) == 0
        # --strict surfaces the error.
        monkeypatch.setattr(
            "sys.stdin", io.StringIO(json.dumps(_event("UserPromptSubmit", prompt="x")))
        )
        assert (
            main(
                [
                    "claude-code",
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


def test_hook_cli_records_via_stdin(monkeypatch, capsys):
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        monkeypatch.delenv("ARCTX_RUN_ID", raising=False)
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(json.dumps(_event("UserPromptSubmit", prompt="hello"))),
        )
        rc = main(["claude-code", "hook", "--run", "run_cc", "--store-dir", _store_dir(td)])
        assert rc == 0
        # stdout must stay empty: on UserPromptSubmit it would be injected
        # into the model context.
        assert capsys.readouterr().out == ""

        handle = resolve_store(_store_dir(td)).load_run("run_cc")
        assert len(handle.run_graph.steps) == 1


def test_hook_cli_tools_filter(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        monkeypatch.delenv("ARCTX_RUN_ID", raising=False)
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(
                json.dumps(_event("PostToolUse", tool_name="Read", tool_input={}))
            ),
        )
        rc = main(
            [
                "claude-code",
                "hook",
                "--run",
                "run_cc",
                "--store-dir",
                _store_dir(td),
                "--tools",
                "Bash,Edit",
            ]
        )
        assert rc == 0
        handle = resolve_store(_store_dir(td)).load_run("run_cc")
        assert len(handle.run_graph.steps) == 0


def test_install_writes_settings_and_is_idempotent():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / ".claude" / "settings.json"
        first = run_claude_code_install_command(
            settings_path=str(path), local=False, matcher="Bash"
        )
        assert first["changed"] is True
        settings = json.loads(path.read_text(encoding="utf-8"))
        for event in ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd"):
            assert event in settings["hooks"]
        assert settings["hooks"]["PostToolUse"][0]["matcher"] == "Bash"

        second = run_claude_code_install_command(
            settings_path=str(path), local=False, matcher="Bash"
        )
        assert second["changed"] is False
        assert json.loads(path.read_text(encoding="utf-8")) == settings


def test_hook_cli_strict_keeps_stdout_empty(monkeypatch, capsys):
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        monkeypatch.delenv("ARCTX_RUN_ID", raising=False)
        monkeypatch.setattr(
            "sys.stdin",
            io.StringIO(json.dumps(_event("UserPromptSubmit", prompt="hello"))),
        )
        rc = main(
            ["claude-code", "hook", "--strict", "--run", "run_cc", "--store-dir", _store_dir(td)]
        )
        captured = capsys.readouterr()
        assert rc == 0
        assert captured.out == ""
        assert "UserPromptSubmit" in captured.err


def test_install_custom_command_and_marker_idempotency():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "settings.json"
        wrapper = "/repo/scripts/arctx claude-code hook"
        first = run_claude_code_install_command(
            settings_path=str(path), local=False, matcher="Bash", command=wrapper
        )
        assert first["changed"] is True
        settings = json.loads(path.read_text(encoding="utf-8"))
        assert settings["hooks"]["Stop"][0]["hooks"][0]["command"] == wrapper

        # Re-install with the default command: the marker ("claude-code
        # hook") must dedupe against the wrapper-style command.
        second = run_claude_code_install_command(
            settings_path=str(path), local=False, matcher="Bash"
        )
        assert second["changed"] is False
        assert json.loads(path.read_text(encoding="utf-8")) == settings


def test_install_warns_when_hook_command_missing_from_path():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "settings.json"
        result = run_claude_code_install_command(
            settings_path=str(path),
            local=False,
            matcher="Bash",
            command="definitely-not-a-real-binary-xyz claude-code hook",
        )
        assert "not found on PATH" in result["warning"]


def test_install_preserves_existing_hooks():
    existing = {
        "hooks": {
            "PostToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-linter"}]}
            ]
        },
        "permissions": {"allow": ["Bash(ls:*)"]},
    }
    changed = merge_hooks_into_settings(existing, build_hooks_config("Edit|Write"))
    assert changed is True
    post = existing["hooks"]["PostToolUse"]
    assert post[0]["hooks"][0]["command"] == "my-linter"
    assert any(
        "arctx claude-code hook" in h["command"] for e in post for h in e["hooks"]
    )
    assert existing["permissions"] == {"allow": ["Bash(ls:*)"]}
