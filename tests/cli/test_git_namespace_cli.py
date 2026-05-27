"""Tests for canonical ``stag git ...`` commands and git shortcut aliases."""

from __future__ import annotations

from unittest.mock import patch

import stag.cli.alias as alias_mod
import stag.cli.commands.git as git_cmd_mod
from stag.cli.main import main, parse_args


def test_canonical_git_commit_parser():
    """Parse ``stag git commit`` under the canonical git namespace."""
    args = parse_args(["git", "commit", "-m", "msg"])

    assert args.command == "git"
    assert args.git_command == "commit"
    assert args.message == "msg"


def test_git_commit_shortcut_alias_routes_to_canonical_namespace(tmp_path):
    """Route ``stag commit`` through the standard git extension alias."""
    user_toml = tmp_path / "aliases.toml"

    with (
        patch.object(alias_mod, "_user_alias_path", return_value=user_toml),
        patch.object(git_cmd_mod, "cli_git", return_value=0) as cli_git,
    ):
        rc = main(["commit", "-m", "msg"])

    assert rc == 0
    args = cli_git.call_args.args[0]
    assert args.command == "git"
    assert args.git_command == "commit"
    assert args.message == "msg"


def test_git_default_aliases_are_visible_without_run(tmp_path, capsys):
    """Expose standard git aliases even when no run directory is resolved."""
    user_toml = tmp_path / "aliases.toml"

    with patch.object(alias_mod, "_user_alias_path", return_value=user_toml):
        rc = main(["alias", "resolve", "commit"])

    assert rc == 0
    out = capsys.readouterr().out
    assert '"target": "git commit"' in out
    assert '"source": "ext:git"' in out
