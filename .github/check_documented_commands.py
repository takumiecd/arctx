#!/usr/bin/env python3
"""Fail when the docs name an `arctx` subcommand that does not exist.

This has bitten twice: #60 (the README naming a command that was never
registered) and the `claude-code` adapter, which CLAUDE.md documented in full
months after the command was deleted. Both are the same bug — prose drifting
away from the parser — and both are cheap to catch mechanically.

Every ``arctx <word>`` in the docs is checked against the real parser, with
every built-in extension enabled so extension-gated namespaces (`git`,
`trial`/`trials`) count as registered. Lines that describe something as
removed are skipped: saying "`arctx git commit` was removed" is the opposite
of drift.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DOC_GLOBS = ("*.md", "docs/**/*.md", "examples/*.sh", "skills/**/*.md")

# Prose that is explicitly *about* a command no longer existing.
REMOVAL_MARKERS = (
    "removed",
    "were all removed",
    "are gone",
    "deleted",
    "no longer",
    "do not reintroduce",
    "unregistered",
    "not implemented",
    "未登録",
    "未実装",
    "削除",
    "廃止",
    "ありません",
    "入れない",
    "実行しません",
)

# Words that follow "arctx" but are not subcommands.
NOT_COMMANDS = {
    # placeholders used in extension-authoring docs
    "myext", "experiment", "do",
}


def parser_choices() -> set[str]:
    sys.path.insert(0, str(REPO / "packages" / "arctx" / "src"))
    sys.path.insert(0, str(REPO / "packages" / "arctx-cli" / "src"))
    from arctx.ext import list_available, load_extension  # noqa: PLC0415
    from arctx_cli.main import _build_parser  # noqa: PLC0415

    choices: set[str] = set()
    root = _build_parser(run_dir=None)
    for action in root._actions:
        if getattr(action, "choices", None):
            choices.update(str(c) for c in action.choices)

    # Extension namespaces are only registered for a run that enables them.
    for name in list_available():
        try:
            ext = load_extension(name)
        except Exception:  # noqa: BLE001
            continue
        for command in ext.cli_commands():
            choices.add(command.name)
        choices.update(alias.split()[0] for alias in ext.default_aliases())
    return choices


def documented() -> dict[str, list[str]]:
    """Collect subcommands named as *commands*, not as English prose.

    A word only counts when it sits in a code span (`arctx foo`) or begins a
    line inside a fenced block — otherwise "arctx is a graph" and the Python
    `from arctx import init` both look like subcommands.
    """
    span = re.compile(r"`arctx ([a-z][a-z0-9-]*)")
    shell = re.compile(r"^\s*(?:\$ |[A-Z_]+=\S+ )*arctx ([a-z][a-z0-9-]*)")
    found: dict[str, list[str]] = {}
    for glob in DOC_GLOBS:
        for path in REPO.glob(glob):
            if "node_modules" in path.parts or "dist" in path.parts:
                continue
            in_fence = False
            recent: list[str] = []
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if line.lstrip().startswith("```"):
                    in_fence = not in_fence
                    continue
                # A removal note often wraps: "Removed commands: `arctx a`,\n
                # `arctx b`". Look back a couple of lines for the marker.
                window = " ".join(recent[-2:] + [line]).lower()
                recent.append(line)
                if any(marker in window for marker in REMOVAL_MARKERS):
                    continue
                words = set(span.findall(line))
                if in_fence or path.suffix == ".sh":
                    words.update(shell.findall(line))
                for word in words:
                    if word in NOT_COMMANDS:
                        continue
                    found.setdefault(word, []).append(
                        f"{path.relative_to(REPO)}:{lineno}"
                    )
    return found


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    choices = parser_choices()
    missing = {
        word: places for word, places in documented().items() if word not in choices
    }
    if not missing:
        print(f"ok — every documented arctx subcommand exists ({len(choices)} registered)")
        return 0
    print("documented commands that the parser does not register:\n", file=sys.stderr)
    for word, places in sorted(missing.items()):
        print(f"  arctx {word}", file=sys.stderr)
        for place in places[:5]:
            print(f"      {place}", file=sys.stderr)
        if len(places) > 5:
            print(f"      ... and {len(places) - 5} more", file=sys.stderr)
    print(
        "\nEither register the command, fix the docs, or — if the line is "
        "describing something that was removed — say so on that line.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
