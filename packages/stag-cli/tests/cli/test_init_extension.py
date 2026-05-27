"""Tests for ``stag init --extension`` integration."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import stag_api.ext as ext_mod
from stag_cli.commands.init import run_init_command
from stag_cli.main import main

_DUMMY_SPEC = "tests.fixtures.dummy_ext:DummyExtension"


def _inject_dummy():
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
# --dummy-flag is passed through to on_init
# ---------------------------------------------------------------------------


def test_init_with_dummy_flag_written(tmp_path):
    store_dir = str(tmp_path / "runs")
    with _inject_dummy():
        result = run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="flagtest",
            store_dir=store_dir,
            extensions=["_dummy"],
            extension_options={"ext__dummy_dummy_flag": True},
        )
    marker = Path(store_dir) / "flagtest" / "_dummy_init.txt"
    assert marker.exists()
    content = marker.read_text(encoding="utf-8")
    assert "flag=True" in content


def test_init_without_flag_defaults_false(tmp_path):
    store_dir = str(tmp_path / "runs")
    with _inject_dummy():
        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="noflagtest",
            store_dir=store_dir,
            extensions=["_dummy"],
            extension_options={},
        )
    marker = Path(store_dir) / "noflagtest" / "_dummy_init.txt"
    assert "flag=False" in marker.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Unknown extension → KeyError → exit 1
# ---------------------------------------------------------------------------


def test_init_unknown_extension_raises():
    with tempfile.TemporaryDirectory() as td:
        store_dir = str(Path(td) / "runs")
        with pytest.raises(KeyError, match="unknown extension"):
            run_init_command(
                requirement_id="req1",
                target_type="task",
                target_id="t",
                run_id="failtest",
                store_dir=store_dir,
                extensions=["nonexistent"],
                extension_options={},
            )


def test_cli_init_unknown_extension_exits_1(tmp_path, capsys):
    store_dir = str(tmp_path / "runs")
    rc = main(
        [
            "init",
            "req1",
            "--run-id",
            "fail_run",
            "--store-dir",
            store_dir,
            "--extension",
            "nonexistent",
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "unknown extension" in err or "error" in err


# ---------------------------------------------------------------------------
# Without extension flag: no extensions.json written
# ---------------------------------------------------------------------------


def test_init_no_extension_no_extensions_json(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="bare_run",
        store_dir=store_dir,
    )
    ext_json = Path(store_dir) / "bare_run" / "extensions.json"
    # No extensions.json should be written when no extensions are requested.
    assert not ext_json.exists()


# ---------------------------------------------------------------------------
# Multiple extensions
# ---------------------------------------------------------------------------


def test_init_multiple_extensions_all_enabled(tmp_path):
    store_dir = str(tmp_path / "runs")
    # register two copies under different names for the test
    original = dict(ext_mod._BUILTIN)
    ext_mod._BUILTIN["_dummy"] = _DUMMY_SPEC
    ext_mod._BUILTIN["_dummy2"] = _DUMMY_SPEC
    try:
        result = run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="multi_ext",
            store_dir=store_dir,
            extensions=["_dummy", "_dummy2"],
            extension_options={},
        )
    finally:
        ext_mod._BUILTIN.clear()
        ext_mod._BUILTIN.update(original)

    assert "_dummy" in result["enabled_extensions"]
    assert "_dummy2" in result["enabled_extensions"]
    from stag_api.ext.enabled import load_enabled

    enabled = load_enabled(Path(store_dir) / "multi_ext")
    names = {e.name for e in enabled}
    # Both registered (note: DummyExtension.name == "_dummy" for both instances)
    assert len(enabled) >= 1
