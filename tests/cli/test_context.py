"""CLI context resolution tests."""

from __future__ import annotations

import json

import pytest

from optagent.cli.context import (
    current_path,
    resolve_run_id,
    resolve_user_id,
    save_current_run,
)
from optagent.cli.commands.current import run_current_command
from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.use import run_use_command


def test_init_sets_current_run(tmp_path):
    store_dir = str(tmp_path / "runs")

    result = run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_a",
        store_dir=store_dir,
    )

    assert result == {"run_id": "run_a"}
    assert run_current_command(store_dir=store_dir)["run_id"] == "run_a"
    marker = json.loads(current_path(store_dir).read_text(encoding="utf-8"))
    assert marker == {"run_id": "run_a", "store_dir": store_dir}


def test_use_requires_existing_run_and_updates_current(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_a",
        store_dir=store_dir,
    )

    with pytest.raises(KeyError):
        run_use_command(run_id="missing", store_dir=store_dir)

    assert run_use_command(run_id="run_a", store_dir=store_dir) == {"run_id": "run_a"}
    assert run_current_command(store_dir=store_dir)["run_id"] == "run_a"


def test_resolve_run_id_precedence(tmp_path, monkeypatch):
    store_dir = str(tmp_path / "runs")
    save_current_run("from_marker", store_dir)

    monkeypatch.setenv("OPTAGENT_RUN_ID", "from_env")

    assert resolve_run_id("explicit", store_dir) == "explicit"
    assert resolve_run_id(None, store_dir) == "from_env"

    monkeypatch.delenv("OPTAGENT_RUN_ID")
    assert resolve_run_id(None, store_dir) == "from_marker"


def test_resolve_run_id_errors_without_marker(tmp_path, monkeypatch):
    monkeypatch.delenv("OPTAGENT_RUN_ID", raising=False)

    with pytest.raises(RuntimeError):
        resolve_run_id(None, str(tmp_path / "runs"))


def test_resolve_user_id_precedence(tmp_path, monkeypatch):
    store_dir = str(tmp_path / "runs")
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"user": {"id": "from_config"}}), encoding="utf-8")

    monkeypatch.setenv("OPTAGENT_USER_ID", "from_env")

    assert resolve_user_id("explicit", store_dir) == "explicit"
    assert resolve_user_id(None, store_dir) == "from_env"

    monkeypatch.delenv("OPTAGENT_USER_ID")
    assert resolve_user_id(None, store_dir) == "from_config"

    config_path.unlink()
    assert resolve_user_id(None, store_dir) == "user"
