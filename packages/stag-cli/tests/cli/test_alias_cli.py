"""Integration tests for ``stag alias`` CLI subcommands."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import stag_cli.alias as alias_mod
from stag_cli.main import main


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(argv, user_alias_path=None):
    """Run main() patching _user_alias_path to a temp file."""
    if user_alias_path is not None:
        with patch.object(alias_mod, "_user_alias_path", return_value=user_alias_path):
            return main(argv)
    return main(argv)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_alias_add_writes_file(tmp_path, capsys):
    user_toml = tmp_path / "aliases.toml"
    with patch.object(alias_mod, "_user_alias_path", return_value=user_toml):
        rc = main(["alias", "add", "c", "git commit"])
    assert rc == 0
    assert user_toml.exists()
    content = user_toml.read_text(encoding="utf-8")
    assert "c" in content
    assert "git commit" in content


def test_alias_list_shows_entry(tmp_path, capsys):
    user_toml = tmp_path / "aliases.toml"
    user_toml.write_text('[aliases]\nc = "git commit"\n', encoding="utf-8")
    with patch.object(alias_mod, "_user_alias_path", return_value=user_toml):
        rc = main(["alias", "list"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "c" in data
    assert data["c"]["target"] == "git commit"
    assert data["c"]["source"] == "user"


def test_alias_remove_deletes_entry(tmp_path, capsys):
    user_toml = tmp_path / "aliases.toml"
    user_toml.write_text('[aliases]\nc = "git commit"\n', encoding="utf-8")
    with patch.object(alias_mod, "_user_alias_path", return_value=user_toml):
        rc = main(["alias", "remove", "c"])
    assert rc == 0
    with patch.object(alias_mod, "_user_alias_path", return_value=user_toml):
        rc2 = main(["alias", "list"])
    assert rc2 == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "c" not in data


def test_alias_remove_missing_returns_1(tmp_path):
    user_toml = tmp_path / "aliases.toml"
    with patch.object(alias_mod, "_user_alias_path", return_value=user_toml):
        rc = main(["alias", "remove", "nonexistent"])
    assert rc == 1


def test_alias_resolve_known(tmp_path, capsys):
    user_toml = tmp_path / "aliases.toml"
    user_toml.write_text('[aliases]\nc = "git commit"\n', encoding="utf-8")
    with patch.object(alias_mod, "_user_alias_path", return_value=user_toml):
        rc = main(["alias", "resolve", "c"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["resolved"] is True
    assert data["target"] == "git commit"
    assert data["source"] == "user"


def test_alias_resolve_unknown(tmp_path, capsys):
    user_toml = tmp_path / "aliases.toml"
    with patch.object(alias_mod, "_user_alias_path", return_value=user_toml):
        rc = main(["alias", "resolve", "nope"])
    assert rc == 0
    out = capsys.readouterr().out
    data = json.loads(out)
    assert data["resolved"] is False
