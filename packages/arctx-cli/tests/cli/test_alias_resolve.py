"""Tests for arctx.cli.alias — pure unit tests for the resolution logic."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from arctx_cli.alias import (
    load_alias_table,
    list_aliases,
    resolve_alias,
    save_user_alias,
    remove_user_alias,
)


# ---------------------------------------------------------------------------
# resolve_alias
# ---------------------------------------------------------------------------


def test_resolve_expands_first_token():
    table = {"commit": "git commit"}
    assert resolve_alias(table, ["commit", "-m", "x"]) == ["git", "commit", "-m", "x"]


def test_resolve_no_match_returns_tokens():
    table = {"commit": "git commit"}
    assert resolve_alias(table, ["init", "req"]) == ["init", "req"]


def test_resolve_empty_tokens_no_crash():
    table = {"commit": "git commit"}
    assert resolve_alias(table, []) == []


def test_resolve_unknown_key():
    assert resolve_alias({}, ["something"]) == ["something"]


def test_resolve_multiword_alias_split():
    table = {"ci": "git commit --amend"}
    result = resolve_alias(table, ["ci", "--no-edit"])
    assert result == ["git", "commit", "--amend", "--no-edit"]


# ---------------------------------------------------------------------------
# load_alias_table priority: ext < user < run
# ---------------------------------------------------------------------------


def test_load_alias_table_ext_only():
    ext_defaults = [{"commit": "git commit"}]
    table = load_alias_table(extensions_default_aliases=ext_defaults)
    assert table.get("commit") == "git commit"


def test_load_alias_table_user_overrides_ext(tmp_path):
    # Write a user aliases.toml in a temp location and monkeypatch _user_alias_path
    import arctx_cli.alias as alias_mod

    user_toml = tmp_path / "aliases.toml"
    user_toml.write_text('[aliases]\ncommit = "git commit --verbose"\n', encoding="utf-8")

    original = alias_mod._user_alias_path
    alias_mod._user_alias_path = lambda: user_toml  # type: ignore[assignment]
    try:
        ext_defaults = [{"commit": "git commit"}]
        table = load_alias_table(extensions_default_aliases=ext_defaults)
        assert table["commit"] == "git commit --verbose"
    finally:
        alias_mod._user_alias_path = original


def test_load_alias_table_run_overrides_user(tmp_path):
    import arctx_cli.alias as alias_mod

    # User alias
    user_toml = tmp_path / "user_aliases.toml"
    user_toml.write_text('[aliases]\ncommit = "git commit --verbose"\n', encoding="utf-8")

    # Run alias
    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "aliases.toml").write_text(
        '[aliases]\ncommit = "git commit --all"\n', encoding="utf-8"
    )

    original = alias_mod._user_alias_path
    alias_mod._user_alias_path = lambda: user_toml  # type: ignore[assignment]
    try:
        table = load_alias_table(run_dir=run_dir)
        assert table["commit"] == "git commit --all"
    finally:
        alias_mod._user_alias_path = original


def test_load_alias_table_empty_no_crash():
    table = load_alias_table()
    assert isinstance(table, dict)


def test_load_alias_table_first_ext_wins_for_duplicates():
    """Among extension defaults, the first ext that defines an alias wins."""
    ext_defaults = [
        {"commit": "ext1 commit"},
        {"commit": "ext2 commit"},
    ]
    table = load_alias_table(extensions_default_aliases=ext_defaults)
    assert table["commit"] == "ext1 commit"


# ---------------------------------------------------------------------------
# list_aliases provenance
# ---------------------------------------------------------------------------


def test_list_aliases_provenance_run_over_user(tmp_path):
    import arctx_cli.alias as alias_mod

    user_toml = tmp_path / "user_aliases.toml"
    user_toml.write_text('[aliases]\nc = "git commit"\n', encoding="utf-8")

    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "aliases.toml").write_text(
        '[aliases]\nc = "git commit --all"\n', encoding="utf-8"
    )

    original = alias_mod._user_alias_path
    alias_mod._user_alias_path = lambda: user_toml  # type: ignore[assignment]
    try:
        result = list_aliases(run_dir=run_dir)
        target, source = result["c"]
        assert source == "run"
        assert target == "git commit --all"
    finally:
        alias_mod._user_alias_path = original


def test_list_aliases_ext_provenance():
    ext_defaults = [{"do-it": "_dummy run"}]
    ext_names = ["_dummy"]
    result = list_aliases(
        extensions_default_aliases=ext_defaults,
        extension_names=ext_names,
    )
    assert "do-it" in result
    target, source = result["do-it"]
    assert target == "_dummy run"
    assert source == "ext:_dummy"
