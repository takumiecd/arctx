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


def test_a_run_local_alias_file_is_ignored(tmp_path):
    """A run travels with its repository, so its contents are untrusted.

    `<run_dir>/aliases.toml` used to be read at the highest priority, so a
    received run could rebind any command -- `show = "cut node"` turned a read
    into an append-only write, overriding the victim's own aliases. Nothing in
    the product ever wrote that file; the tier is gone.
    """
    import arctx_cli.alias as alias_mod

    user_toml = tmp_path / "user_aliases.toml"
    user_toml.write_text('[aliases]\ncommit = "git commit --verbose"\n', encoding="utf-8")

    run_dir = tmp_path / "run1"
    run_dir.mkdir()
    (run_dir / "aliases.toml").write_text(
        '[aliases]\ncommit = "git commit --all"\nshow = "cut node"\n', encoding="utf-8"
    )

    original = alias_mod._user_alias_path
    alias_mod._user_alias_path = lambda: user_toml  # type: ignore[assignment]
    try:
        table = load_alias_table(run_dir=run_dir)
        assert table["commit"] == "git commit --verbose"  # the user's own wins
        assert "show" not in table  # the hijack never lands
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


def test_list_aliases_never_reports_a_run_source(tmp_path):
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
        assert source == "user"
        assert target == "git commit"
        assert all(src != "run" for _, src in result.values())
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


# ---------------------------------------------------------------------------
# alias introspection must answer for the run dispatch would actually use
# ---------------------------------------------------------------------------


def test_alias_introspection_resolves_the_run_the_same_way_dispatch_does(
    tmp_path, monkeypatch
):
    """`alias list` used to have its own resolver that skipped <gitdir>/arctx-id.

    Inside a repo with a run pointer and no ARCTX_RUN_ID, that made the
    introspection commands report a different resolution than the CLI
    dispatched against.
    """
    import subprocess

    from arctx_cli.alias import resolve_run_dir_for_alias
    from arctx_cli.commands.alias_cmd import _resolve_run_dir_from_args
    from arctx_cli.commands.init import run_init_command

    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (
        ["git", "init", "-q", "."],
        ["git", "config", "user.email", "a@b"],
        ["git", "config", "user.name", "a"],
        ["git", "commit", "-q", "--allow-empty", "-m", "i"],
    ):
        subprocess.run(cmd, cwd=str(repo), capture_output=True, check=True)

    monkeypatch.chdir(repo)
    monkeypatch.delenv("ARCTX_RUN_ID", raising=False)
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "home"))
    run_init_command(
        requirement_id="r",
        target_type="task",
        target_id="t",
        run_id="drift",
        store_dir=str(tmp_path / "home" / "runs"),
        extensions=["git"],
    )

    class _Args:
        run = None
        store_dir = str(tmp_path / "home" / "runs")

    dispatch = resolve_run_dir_for_alias(["--store-dir", _Args.store_dir])
    introspection = _resolve_run_dir_from_args(_Args())
    assert introspection == dispatch
    assert dispatch is not None and dispatch.endswith("drift")


def test_introspection_does_not_advertise_a_disabled_extension(tmp_path, monkeypatch):
    """`alias resolve verify` used to say yes on every freshly-init'd run.

    The introspection path seeded git's aliases unconditionally while dispatch
    iterated enabled extensions only — so the commands whose job is to say what
    an alias resolves to stated a false fact, and `arctx verify` then answered
    "invalid choice".
    """
    from arctx_cli.alias import collect_ext_default_aliases
    from arctx_cli.commands.init import run_init_command

    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="r", target_type="task", target_id="t",
        run_id="noext", store_dir=store_dir,
    )
    run_dir = str(tmp_path / "runs" / "noext")

    tables, names = collect_ext_default_aliases(run_dir)
    assert tables == [] and names == []

    run_init_command(
        requirement_id="r", target_type="task", target_id="t",
        run_id="withgit", store_dir=store_dir, extensions=["git"],
    )
    tables, names = collect_ext_default_aliases(str(tmp_path / "runs" / "withgit"))
    assert "git" in names
    assert any("verify" in table for table in tables)


def test_both_alias_paths_use_the_one_collector():
    """Two collectors is how the last drift happened; assert there is one."""
    from arctx_cli.alias import collect_ext_default_aliases
    from arctx_cli.commands.alias_cmd import _collect_ext_aliases
    from arctx_cli.main import _collect_ext_default_aliases

    assert _collect_ext_aliases(None) == collect_ext_default_aliases(None)
    assert _collect_ext_default_aliases(None) == collect_ext_default_aliases(None)[0]
