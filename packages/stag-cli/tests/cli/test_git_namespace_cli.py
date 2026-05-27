"""Tests for canonical ``stag git ...`` commands and git shortcut aliases."""

from __future__ import annotations

from unittest.mock import patch

import stag_cli.alias as alias_mod
import stag_cli.commands.git as git_cmd_mod
from stag_cli.commands.init import run_init_command
from stag_cli.main import main, parse_args


def _store_dir(tmp_path):
    return str(tmp_path / "stag_home" / "runs")


def _init_git_enabled_run(tmp_path, run_id: str = "run_git_cli") -> str:
    store_dir = _store_dir(tmp_path)
    run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=store_dir,
        extensions=["git"],
        no_hooks=True,
    )
    return store_dir


def test_canonical_git_commit_parser(tmp_path):
    """Parse ``stag git commit`` under the canonical git namespace."""
    store_dir = _init_git_enabled_run(tmp_path)
    args = parse_args([
        "git", "commit", "-m", "msg", "--run", "run_git_cli", "--store-dir", store_dir
    ])

    assert args.command == "git"
    assert args.git_command == "commit"
    assert args.message == "msg"


def test_git_commit_shortcut_alias_routes_to_canonical_namespace(tmp_path):
    """Route ``stag commit`` through the enabled git extension alias."""
    user_toml = tmp_path / "aliases.toml"
    store_dir = _init_git_enabled_run(tmp_path)

    with (
        patch.object(alias_mod, "_user_alias_path", return_value=user_toml),
        patch.object(git_cmd_mod, "cli_git", return_value=0) as cli_git,
    ):
        rc = main(["commit", "-m", "msg", "--run", "run_git_cli", "--store-dir", store_dir])

    assert rc == 0
    args = cli_git.call_args.args[0]
    assert args.command == "git"
    assert args.git_command == "commit"
    assert args.message == "msg"


def test_git_default_aliases_are_visible_for_enabled_run(tmp_path, capsys):
    """Expose git aliases when the current run enables the git extension."""
    user_toml = tmp_path / "aliases.toml"
    store_dir = _init_git_enabled_run(tmp_path)

    with patch.object(alias_mod, "_user_alias_path", return_value=user_toml):
        rc = main(["alias", "resolve", "commit", "--run", "run_git_cli", "--store-dir", store_dir])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"target": "git commit"' in out
    assert '"source": "ext:git"' in out
