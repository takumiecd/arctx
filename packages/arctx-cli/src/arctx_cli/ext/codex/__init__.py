"""arctx CLI codex command -- record Codex sessions via hooks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from arctx.core.append import AppendBatch
from arctx.ext.codex import record_hook_event

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import resolve_run_id_from_args, resolve_store, resolve_user_id_from_args

HOOK_COMMAND = "arctx codex hook"
_HOOK_MARKER = "codex hook"
DEFAULT_TOOL_MATCHER = "Bash|apply_patch|Edit|Write|MultiEdit"
_HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop")


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "codex",
        help="Record Codex sessions into a run via hooks",
        description=(
            "Adapter for Codex hooks. `install` writes hook entries into "
            ".codex/hooks.json by default; `hook` consumes one hook event JSON "
            "from argv or stdin and records it into the current run."
        ),
    )
    sub = parser.add_subparsers(dest="codex_command", required=True)

    hook = sub.add_parser(
        "hook",
        help="Consume one hook event JSON from argv or stdin (fail-safe: exits 0 on any error)",
    )
    hook.add_argument("event_json", nargs="?", default=None)
    hook.add_argument("--run", default=None)
    hook.add_argument("--store-dir", default=None)
    hook.add_argument("--user", default=None)
    hook.add_argument(
        "--tools",
        default=None,
        metavar="A,B,...",
        help=(
            "Comma-separated tool names to record for PostToolUse "
            "(default: record every tool the hooks.json matcher lets through)"
        ),
    )
    hook.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on errors instead of silently no-opping (for debugging/tests)",
    )

    install = sub.add_parser(
        "install",
        help="Add arctx hook entries to Codex hooks.json (idempotent)",
    )
    install.add_argument(
        "--hooks",
        default=None,
        metavar="PATH",
        help="Hooks file to update (default: <repo root>/.codex/hooks.json)",
    )
    install.add_argument(
        "--global",
        action="store_true",
        dest="global_hooks",
        help="Target $CODEX_HOME/hooks.json or ~/.codex/hooks.json instead of project hooks",
    )
    install.add_argument(
        "--matcher",
        default=DEFAULT_TOOL_MATCHER,
        help=f"PostToolUse tool matcher (default: {DEFAULT_TOOL_MATCHER})",
    )
    install.add_argument(
        "--command",
        default=HOOK_COMMAND,
        dest="hook_command",
        metavar="CMD",
        help=(
            f"Hook command to write (default: {HOOK_COMMAND!r}). Pass an "
            "absolute path when arctx is not on PATH or the PATH version "
            "predates the codex subcommand"
        ),
    )
    install.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="Print the hooks JSON snippet instead of writing a file",
    )
    return parser


def run_codex_hook_command(
    *,
    event: dict,
    run_id: str,
    store_dir: str | None,
    user_id: str,
    tools: list[str] | None = None,
) -> dict | None:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    before = graph_counts(handle)
    result = record_hook_event(handle, event, user_id=user_id, tools=tools)
    if result is None:
        return None
    ws_id = result["work_session_id"]
    if result["event"] == "SessionStart":
        if hasattr(store, "append_batch"):
            store.append_batch(
                AppendBatch(
                    run_id=run_id,
                    user_id=user_id,
                    work_session_id=ws_id,
                    work_session=handle.run_graph.work_sessions[ws_id],
                    records=(),
                    events=(),
                )
            )
        else:
            store.save_run(handle)
        return result
    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=ws_id,
        before=before,
    )
    return result


def build_hooks_config(
    matcher: str = DEFAULT_TOOL_MATCHER, command: str = HOOK_COMMAND
) -> dict:
    """Return hook entries for every Codex event the adapter records."""
    config: dict = {}
    for event in _HOOK_EVENTS:
        entry: dict = {"hooks": [{"type": "command", "command": command}]}
        if event == "PostToolUse":
            entry["matcher"] = matcher
        config[event] = [entry]
    return config


def merge_hooks_into_settings(settings: dict, hooks_config: dict) -> bool:
    """Merge arctx hook entries into a hooks.json-style settings dict."""
    hooks = settings.setdefault("hooks", {})
    changed = False
    for event, entries in hooks_config.items():
        existing = hooks.setdefault(event, [])
        already = any(
            _HOOK_MARKER in str(h.get("command", ""))
            for e in existing
            if isinstance(e, dict)
            for h in e.get("hooks", [])
            if isinstance(h, dict)
        )
        if already:
            continue
        existing.extend(entries)
        changed = True
    return changed


def run_codex_install_command(
    *,
    hooks_path: str | None,
    global_hooks: bool,
    matcher: str,
    command: str = HOOK_COMMAND,
) -> dict:
    path = Path(hooks_path) if hooks_path else _default_hooks_path(global_hooks=global_hooks)
    settings: dict = {}
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
    changed = merge_hooks_into_settings(settings, build_hooks_config(matcher, command))
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    result = {"hooks_path": str(path), "changed": changed}
    warning = _check_hook_command(command)
    if warning:
        result["warning"] = warning
    return result


def _check_hook_command(command: str) -> str | None:
    import shlex  # noqa: PLC0415
    import shutil  # noqa: PLC0415
    import subprocess  # noqa: PLC0415

    try:
        executable = shlex.split(command)[0]
    except (ValueError, IndexError):
        return f"could not parse hook command: {command!r}"
    resolved = shutil.which(executable)
    if resolved is None:
        return (
            f"{executable!r} not found on PATH -- hooks will silently no-op. "
            "Re-run with --command '/absolute/path/to/arctx codex hook'."
        )
    try:
        probe = subprocess.run(
            [resolved, "codex", "--help"],
            capture_output=True,
            timeout=10,
        )
        if probe.returncode != 0:
            return (
                f"{resolved} does not support the codex subcommand "
                "(older version?) -- hooks will silently no-op. Upgrade it or "
                "point --command at a newer arctx."
            )
    except (OSError, subprocess.TimeoutExpired):
        return f"could not verify {resolved} (probe failed) -- check that the hook command runs."
    return None


def _default_hooks_path(*, global_hooks: bool) -> Path:
    if global_hooks:
        return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "hooks.json"
    try:
        from arctx.paths import find_repo_root  # noqa: PLC0415

        base = find_repo_root()
    except RuntimeError:
        base = Path.cwd()
    return Path(base) / ".codex" / "hooks.json"


def _resolve_hook_user(args) -> str:
    resolved = resolve_user_id_from_args(args)
    return "codex" if resolved == "user" else resolved


def _read_event_json(args) -> dict:
    raw = args.event_json if args.event_json is not None else sys.stdin.read()
    return json.loads(raw)


def cli_codex(args) -> int:
    if args.codex_command == "install":
        try:
            if args.print_only:
                print(
                    json.dumps(
                        {"hooks": build_hooks_config(args.matcher, args.hook_command)},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 0
            result = run_codex_install_command(
                hooks_path=args.hooks,
                global_hooks=args.global_hooks,
                matcher=args.matcher,
                command=args.hook_command,
            )
            if "warning" in result:
                print(f"warning: {result['warning']}", file=sys.stderr)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    if args.codex_command == "hook":
        try:
            event = _read_event_json(args)
            tools = (
                [t.strip() for t in args.tools.split(",") if t.strip()]
                if args.tools
                else None
            )
            result = run_codex_hook_command(
                event=event,
                run_id=resolve_run_id_from_args(args),
                store_dir=args.store_dir,
                user_id=_resolve_hook_user(args),
                tools=tools,
            )
            if args.strict and result is not None:
                print(json.dumps(result, ensure_ascii=False), file=sys.stderr)
            return 0
        except Exception as exc:  # noqa: BLE001
            if args.strict:
                print(f"error: {exc}", file=sys.stderr)
                return 1
            return 0

    return 1
