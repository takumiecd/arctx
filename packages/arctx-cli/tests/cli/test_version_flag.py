"""Tests for ``arctx --version``.

CONTRIBUTING asks bug reporters to include ``arctx --version`` output, but the
flag did not exist: the command errored out with a usage message instead. The
subcommand is `required=True`, so the interesting part is that the version
action still answers without one.
"""

from __future__ import annotations

import pytest

from arctx_cli.main import parse_args, version_line


def test_version_flag_answers_without_a_subcommand(capsys):
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--version"])

    assert excinfo.value.code == 0
    out = capsys.readouterr().out.strip()
    assert out == version_line()


def test_version_line_names_both_packages():
    """A mismatched core/CLI pair is exactly what a bug report needs to show."""
    from arctx import __version__ as core_version

    line = version_line()
    assert line.startswith(f"arctx {core_version} ")
    assert "arctx-cli " in line


def test_version_line_records_the_interpreter():
    import platform
    import sys

    line = version_line()
    assert f"python {platform.python_version()}" in line
    assert sys.platform in line


def test_version_flag_is_listed_in_help(capsys):
    with pytest.raises(SystemExit):
        parse_args(["--help"])

    assert "--version" in capsys.readouterr().out
