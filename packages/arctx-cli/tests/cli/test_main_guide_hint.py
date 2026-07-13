"""Tests for the 'arctx guide' discovery hint on parser/user errors.

New users and agents were one `--help` away from `arctx add` but two away
from discovering `arctx guide`. These tests cover the root parser's epilog,
its ``error()`` override for missing/unknown subcommands, and the hint
appended to formatted user errors (except for ``guide`` itself, to avoid
looping).
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from arctx_cli.commands.init import run_init_command
from arctx_cli.main import GUIDE_HINT, main, parse_args


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def test_no_subcommand_prints_guide_hint(capsys):
    with pytest.raises(SystemExit) as excinfo:
        parse_args([])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert GUIDE_HINT in err


def test_unknown_subcommand_prints_guide_hint(capsys):
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["nosuchcmd"])
    assert excinfo.value.code == 2
    err = capsys.readouterr().err
    assert GUIDE_HINT in err


def test_root_help_epilog_mentions_guide(capsys):
    with pytest.raises(SystemExit):
        parse_args(["--help"])
    out = capsys.readouterr().out
    assert "arctx guide" in out
    assert "First time or an agent?" in out


def test_user_error_appends_guide_hint(capsys):
    with tempfile.TemporaryDirectory() as td:
        rc = main(["show", "no_such_id", "--run", "no_such_run", "--store-dir", _store_dir(td)])
    assert rc == 1
    err = capsys.readouterr().err
    assert GUIDE_HINT in err


def test_guide_command_error_has_no_self_referential_hint(capsys, monkeypatch):
    """A failure inside 'arctx guide' itself must not loop back to 'arctx guide'."""
    from arctx_cli.commands import guide as guide_module

    def _boom(_args):
        raise RuntimeError("guide exploded")

    # core_cli_commands() re-imports `cli_guide` from this module on every
    # `_build_parser()` call, so patching the module attribute here is picked
    # up without needing to touch the command registry itself.
    monkeypatch.setattr(guide_module, "cli_guide", _boom)

    with tempfile.TemporaryDirectory() as td:
        # chdir away from the repo: run_init_command writes the active-run
        # pointer into the enclosing gitdir, which would pollute the real
        # <repo>/.git/arctx-id when tests run from a checkout.
        monkeypatch.chdir(td)
        run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="run_guide_err",
            store_dir=_store_dir(td),
        )
        rc = main(["guide", "--run", "run_guide_err", "--store-dir", _store_dir(td)])
    assert rc == 1
    err = capsys.readouterr().err
    assert "guide exploded" in err
    assert GUIDE_HINT not in err
