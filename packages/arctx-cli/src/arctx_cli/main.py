"""arctx CLI entry point."""

from __future__ import annotations

import argparse
import errno
import os
import platform
import sys
from importlib import metadata

from arctx_cli.commands import core_cli_commands, register_cli_commands

GUIDE_HINT = "hint: run 'arctx guide' to see the usage model and current context"


class _RootArgumentParser(argparse.ArgumentParser):
    """Root parser that points users at ``arctx guide`` on a parse error.

    Base ``argparse`` prints usage + message on ``error()`` and exits, without
    ever showing the epilog — so a missing/typo'd subcommand gives no signal
    toward ``arctx guide``. This appends the same hint used elsewhere
    (:data:`GUIDE_HINT`) after the standard usage/message, then exits with the
    usual code 2. Subparsers created via ``subparsers.add_parser`` inherit
    this class (``add_subparsers`` defaults ``parser_class`` to the parent's
    type), so subcommand parse errors funnel to the guide as well.
    """

    def error(self, message: str) -> None:  # noqa: D102 — argparse override
        self.print_usage(sys.stderr)
        print(f"{self.prog}: error: {message}", file=sys.stderr)
        print(GUIDE_HINT, file=sys.stderr)
        self.exit(2)


def version_line() -> str:
    """One line identifying this install, for bug reports (see CONTRIBUTING).

    Core and CLI are released in lockstep and pinned exactly (``arctx==<v>``),
    so they normally match — printing both is what makes a mismatched install
    visible, which is the failure this line exists to expose.
    """
    from arctx import __version__ as core_version  # noqa: PLC0415

    try:
        cli_version = metadata.version("arctx-cli")
    except metadata.PackageNotFoundError:
        # Running from a source checkout via PYTHONPATH: nothing is installed,
        # so there is no distribution metadata to read.
        cli_version = "source"

    return (
        f"arctx {core_version} (arctx-cli {cli_version}, "
        f"python {platform.python_version()}, {sys.platform})"
    )


class _VersionAction(argparse.Action):
    """``--version``, computed when asked for rather than on every startup."""

    def __init__(self, option_strings, dest, default=argparse.SUPPRESS, help=None):
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            default=default,
            nargs=0,
            help=help,
        )

    def __call__(self, parser, namespace, values, option_string=None):  # noqa: D102
        print(version_line())
        parser.exit()


def _user_error(message: str, *, command: str | None = None) -> int:
    """Print a clean ``arctx: <message>`` to stderr and return exit code 1.

    Appends the ``arctx guide`` hint unless the failing command is ``guide``
    itself (that would just loop the user back to the thing that failed).
    """
    print(f"arctx: {message}", file=sys.stderr)
    if command != "guide":
        print(GUIDE_HINT, file=sys.stderr)
    return 1


def _format_user_error(exc: BaseException, args) -> str | None:
    """Turn an expected, user-facing exception into a friendly message.

    Returns ``None`` for exceptions that should keep their traceback (genuine
    bugs), so they propagate unchanged.
    """
    if isinstance(exc, OSError) and exc.errno == errno.EADDRINUSE:
        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", None)
        where = f"{host}:{port}" if port is not None else "the requested address"
        return (
            f"address already in use ({where}). "
            "Another server is probably already running there — "
            "stop it, or pick a different port with --port <N>."
        )
    if isinstance(exc, KeyError):
        # KeyError stringifies with quotes; unwrap to the bare message.
        return str(exc.args[0]) if exc.args else str(exc)
    if isinstance(exc, (RuntimeError, FileNotFoundError, ValueError)):
        return str(exc) or exc.__class__.__name__
    return None


def _build_parser(*, run_dir: str | None = None) -> argparse.ArgumentParser:
    parser = _RootArgumentParser(
        prog="arctx",
        description="Record optimization and problem-solving processes",
        epilog=(
            "First time or an agent? Run 'arctx guide' first — it explains "
            "the data model (Node/Step/Lane), the recommended workflow, and "
            "shows the current context in one shot."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Before the subparsers: the version action exits during parsing, so it
    # answers even though a subcommand is otherwise required.
    parser.add_argument(
        "--version",
        action=_VersionAction,
        help="Show the installed arctx / arctx-cli versions and exit",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    register_cli_commands(subparsers, core_cli_commands())

    from arctx_cli.ext_registry import (  # noqa: PLC0415
        ALWAYS_ON_EXTENSIONS,
        register_enabled_cli,
        register_extension_cli,
    )

    register_extension_cli(subparsers, ALWAYS_ON_EXTENSIONS)
    register_enabled_cli(subparsers, run_dir)

    return parser


def _resolve_run_dir_for_alias(tokens: list[str]) -> str | None:
    """Delegate to the one resolver in arctx_cli.alias."""
    from arctx_cli.alias import resolve_run_dir_for_alias  # noqa: PLC0415

    return resolve_run_dir_for_alias(tokens)


def _collect_ext_default_aliases(run_dir: str | None) -> list[dict[str, str]]:
    """Load default_aliases from extensions enabled in the current run."""
    from arctx.ext import load_extension  # noqa: PLC0415
    from arctx.ext.enabled import load_enabled  # noqa: PLC0415

    ext_aliases: list[dict[str, str]] = []
    seen: set[str] = set()
    if run_dir is None:
        return ext_aliases

    for ee in load_enabled(run_dir):
        if ee.name in seen:
            continue
        try:
            ext = load_extension(ee.name)
            ext_aliases.append(ext.default_aliases())
            seen.add(ext.name)
        except (KeyError, ImportError):
            continue
    return ext_aliases


def parse_args(argv: list[str] | None = None):
    """Parse CLI arguments."""
    tokens: list[str] | None = None if argv is None else list(argv)
    run_dir = _resolve_run_dir_for_alias(tokens or sys.argv[1:])
    parser = _build_parser(run_dir=run_dir)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the CLI entry point."""
    tokens: list[str] = list(argv if argv is not None else sys.argv[1:])

    # --- Alias resolution (one level only) ---
    run_dir = _resolve_run_dir_for_alias(tokens)
    ext_aliases = _collect_ext_default_aliases(run_dir)
    from arctx_cli.alias import load_alias_table, resolve_alias  # noqa: PLC0415

    alias_table = load_alias_table(
        run_dir=run_dir,
        extensions_default_aliases=ext_aliases,
    )
    tokens = resolve_alias(alias_table, tokens)
    # ---

    parser = _build_parser(run_dir=run_dir)
    args = parser.parse_args(tokens)
    handler = getattr(args, "_arctx_handler", None)
    if handler is None:
        return 1

    if os.environ.get("ARCTX_DEBUG"):
        # Opt back into full tracebacks for debugging.
        return handler(args)
    try:
        return handler(args)
    except KeyboardInterrupt:
        return 130
    except BaseException as exc:  # noqa: BLE001 — re-raise anything unexpected
        message = _format_user_error(exc, args)
        if message is None:
            raise
        return _user_error(message, command=getattr(args, "command", None))


if __name__ == "__main__":
    sys.exit(main())
