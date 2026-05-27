"""CLI integration tests for the command extension."""

from __future__ import annotations

import json
import sys

import pytest

from stag.cli.commands.init import run_init_command
from stag.cli.context import resolve_store
from stag.cli.main import main
from stag.ext.command.payloads import CommandRunPayload


def test_command_cli_is_only_registered_for_enabled_run(tmp_path, capsys):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_plain",
        store_dir=store_dir,
    )

    with pytest.raises(SystemExit) as exc:
        main(
            [
                "command",
                "run",
                "--run",
                "run_plain",
                "--store-dir",
                store_dir,
                "--",
                sys.executable,
                "-c",
                "print('x')",
            ]
        )

    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_command_cli_runs_and_records_payload(tmp_path, capsys):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_command_cli",
        store_dir=store_dir,
        extensions=["command"],
        extension_options={},
    )

    rc = main(
        [
            "command",
            "run",
            "--run",
            "run_command_cli",
            "--store-dir",
            store_dir,
            "--cwd",
            str(tmp_path),
            "--",
            sys.executable,
            "-c",
            "print('ok')",
        ]
    )

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["payload"]["payload_type"] == "command_run"
    assert data["payload"]["stdout"] == "ok\n"

    store = resolve_store(store_dir)
    handle = store.load_run("run_command_cli")
    payload_id = data["payload"]["payload_id"]
    assert isinstance(handle.run_graph.payloads[payload_id], CommandRunPayload)


def test_command_alias_runs_when_extension_enabled(tmp_path, capsys):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_command_alias",
        store_dir=store_dir,
        extensions=["command"],
        extension_options={},
    )

    rc = main(
        [
            "cmd",
            "--run",
            "run_command_alias",
            "--store-dir",
            store_dir,
            "--",
            sys.executable,
            "-c",
            "print('alias')",
        ]
    )

    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["payload"]["stdout"] == "alias\n"
