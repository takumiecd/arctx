"""Integration tests for ``stag ext`` CLI subcommands using the dummy extension."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import stag_api.ext as ext_mod
from stag_cli.main import main
from stag_cli.commands.init import run_init_command


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_SPEC = "tests.fixtures.dummy_ext:DummyExtension"


def _inject_dummy():
    """Context manager that temporarily registers the dummy extension."""
    original = dict(ext_mod._BUILTIN)

    class _CM:
        def __enter__(self):
            ext_mod._BUILTIN["_dummy"] = _DUMMY_SPEC
            return self

        def __exit__(self, *_):
            ext_mod._BUILTIN.clear()
            ext_mod._BUILTIN.update(original)

    return _CM()


# ---------------------------------------------------------------------------
# stag ext list
# ---------------------------------------------------------------------------


def test_ext_list_contains_dummy(capsys):
    with _inject_dummy():
        rc = main(["ext", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    names = [e["name"] for e in data["extensions"]]
    assert "_dummy" in names


def test_ext_list_enabled_flag(tmp_path, capsys):
    store_dir = str(tmp_path / "runs")
    with _inject_dummy():
        # init without extension
        result = run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_ext_list",
            store_dir=store_dir,
        )
        run_dir = str(Path(store_dir) / "run_ext_list")
        rc = main(["ext", "list", "--run", "run_ext_list", "--store-dir", store_dir])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    entry = next(e for e in data["extensions"] if e["name"] == "_dummy")
    assert entry["enabled"] is False


# ---------------------------------------------------------------------------
# stag ext show
# ---------------------------------------------------------------------------


def test_ext_show_dummy(capsys):
    with _inject_dummy():
        rc = main(["ext", "show", "_dummy"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["name"] == "_dummy"
    assert data["version"] == "0.1"
    assert "do-it" in data["default_aliases"]


def test_ext_show_unknown_returns_1(capsys):
    rc = main(["ext", "show", "does_not_exist"])
    assert rc == 1


# ---------------------------------------------------------------------------
# stag init --extension _dummy
# ---------------------------------------------------------------------------


def test_init_with_dummy_extension(tmp_path):
    store_dir = str(tmp_path / "runs")
    with _inject_dummy():
        result = run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_with_dummy",
            store_dir=store_dir,
            extensions=["_dummy"],
            extension_options={},
        )
    assert "_dummy" in result["enabled_extensions"]
    run_dir = Path(store_dir) / "run_with_dummy"
    marker = run_dir / "_dummy_init.txt"
    assert marker.exists()
    assert "dummy init" in marker.read_text(encoding="utf-8")


def test_init_extension_enabled_in_list(tmp_path, capsys):
    store_dir = str(tmp_path / "runs")
    with _inject_dummy():
        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_enabled",
            store_dir=store_dir,
            extensions=["_dummy"],
            extension_options={},
        )
        rc = main(["ext", "list", "--run", "run_enabled", "--store-dir", store_dir])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    entry = next(e for e in data["extensions"] if e["name"] == "_dummy")
    assert entry["enabled"] is True


# ---------------------------------------------------------------------------
# stag ext enable (post-init)
# ---------------------------------------------------------------------------


def test_ext_enable_on_existing_run(tmp_path, capsys):
    store_dir = str(tmp_path / "runs")
    with _inject_dummy():
        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_enable_test",
            store_dir=store_dir,
        )
        rc = main(
            ["ext", "enable", "_dummy", "--run", "run_enable_test", "--store-dir", store_dir]
        )
    assert rc == 0
    # Verify marker written
    marker = Path(store_dir) / "run_enable_test" / "_dummy_init.txt"
    assert marker.exists()


def test_ext_enable_unknown_returns_1(tmp_path, capsys):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="run_enable_unk",
        store_dir=store_dir,
    )
    rc = main(
        ["ext", "enable", "does_not_exist", "--run", "run_enable_unk", "--store-dir", store_dir]
    )
    assert rc == 1


# ---------------------------------------------------------------------------
# stag ext disable
# ---------------------------------------------------------------------------


def test_ext_disable_removes_from_enabled(tmp_path, capsys):
    store_dir = str(tmp_path / "runs")
    with _inject_dummy():
        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_disable",
            store_dir=store_dir,
            extensions=["_dummy"],
            extension_options={},
        )
        rc = main(
            ["ext", "disable", "_dummy", "--run", "run_disable", "--store-dir", store_dir]
        )
    assert rc == 0
    # Check it's gone from enabled list
    from stag_api.ext.enabled import load_enabled

    enabled = load_enabled(Path(store_dir) / "run_disable")
    assert not any(e.name == "_dummy" for e in enabled)


def test_ext_disable_not_enabled_returns_1(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="run_dis_unk",
        store_dir=store_dir,
    )
    rc = main(
        ["ext", "disable", "_dummy", "--run", "run_dis_unk", "--store-dir", store_dir]
    )
    assert rc == 1
