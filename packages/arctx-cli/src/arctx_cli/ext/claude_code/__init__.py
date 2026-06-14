"""arctx CLI claude-code command — record Claude Code sessions via hooks."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from arctx.core.append import AppendBatch
from arctx.ext.claude_code import record_hook_event

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import resolve_run_id_from_args, resolve_store, resolve_user_id_from_args

HOOK_COMMAND = "arctx claude-code hook"
# Idempotency marker: any hook command containing this substring counts as
# ours, so rewriting the command to a wrapper/absolute path (e.g.
# "/repo/scripts/arctx claude-code hook") still dedupes on re-install.
_HOOK_MARKER = "claude-code hook"
DEFAULT_TOOL_MATCHER = "Write|Edit|MultiEdit|NotebookEdit|Bash"
_HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "Stop", "SessionEnd")


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "claude-code",
        help="Record Claude Code sessions into a run via hooks",
        description=(
            "Adapter for Claude Code hooks. `install` writes hook entries into "
            ".claude/settings.json; `hook` consumes one hook event JSON from stdin "
            "and records it into the current run. Prompts and tool uses become "
            "Steps in the session's own branch; parallel sessions land as "
            "sibling branches."
        ),
    )
    sub = parser.add_subparsers(dest="claude_code_command", required=True)

    hook = sub.add_parser(
        "hook",
        help="Consume one hook event JSON from stdin (fail-safe: exits 0 on any error)",
    )
    hook.add_argument("--run", default=None)
    hook.add_argument("--store-dir", default=None)
    hook.add_argument("--user", default=None)
    hook.add_argument(
        "--tools",
        default=None,
        metavar="A,B,...",
        help=(
            "Comma-separated tool names to record for PostToolUse "
            "(default: record every tool the settings.json matcher lets through)"
        ),
    )
    hook.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero on errors instead of silently no-opping (for debugging/tests)",
    )

    install = sub.add_parser(
        "install",
        help="Add arctx hook entries to Claude Code settings (idempotent)",
    )
    install.add_argument(
        "--settings",
        default=None,
        metavar="PATH",
        help="Settings file to update (default: <repo root>/.claude/settings.json)",
    )
    install.add_argument(
        "--local",
        action="store_true",
        help="Target .claude/settings.local.json instead of settings.json",
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
            "predates the claude-code subcommand"
        ),
    )
    install.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="Print the hooks JSON snippet instead of writing a file",
    )
    return parser


def run_claude_code_hook_command(
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
        # SessionStart creates only a WorkSession — no graph records, no work
        # events — so it can't go through build_append_batch. Same path as
        # `work-session start`.
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
    """Return hook entries for every event the adapter records."""
    config: dict = {}
    for event in _HOOK_EVENTS:
        entry: dict = {"hooks": [{"type": "command", "command": command}]}
        if event == "PostToolUse":
            entry["matcher"] = matcher
        config[event] = [entry]
    return config


def merge_hooks_into_settings(settings: dict, hooks_config: dict) -> bool:
    """Merge arctx hook entries into a settings dict. Returns True if changed.

    Idempotent: an event that already has any hook running ``arctx
    claude-code hook`` is left untouched, so user edits survive re-runs.
    """
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


def run_claude_code_install_command(
    *,
    settings_path: str | None,
    local: bool,
    matcher: str,
    command: str = HOOK_COMMAND,
) -> dict:
    path = Path(settings_path) if settings_path else _default_settings_path(local=local)
    settings: dict = {}
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
    changed = merge_hooks_into_settings(settings, build_hooks_config(matcher, command))
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    result = {"settings_path": str(path), "changed": changed}
    warning = _check_hook_command(command)
    if warning:
        result["warning"] = warning
    return result


def _check_hook_command(command: str) -> str | None:
    """Best-effort check that the hook command will actually run.

    The hook itself is fail-safe (silent no-op on error), which means a
    missing or outdated `arctx` on PATH produces no symptom beyond
    "nothing gets recorded". Surface that at install time instead.
    """
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
            f"{executable!r} not found on PATH — hooks will silently no-op. "
            "Re-run with --command '/absolute/path/to/arctx claude-code hook'."
        )
    try:
        probe = subprocess.run(
            [resolved, "claude-code", "--help"],
            capture_output=True,
            timeout=10,
        )
        if probe.returncode != 0:
            return (
                f"{resolved} does not support the claude-code subcommand "
                "(older version?) — hooks will silently no-op. Upgrade it or "
                "point --command at a newer arctx."
            )
    except (OSError, subprocess.TimeoutExpired):
        return f"could not verify {resolved} (probe failed) — check that the hook command runs."
    return None


def _default_settings_path(*, local: bool) -> Path:
    try:
        from arctx.paths import find_repo_root  # noqa: PLC0415

        base = find_repo_root()
    except RuntimeError:
        base = Path.cwd()
    name = "settings.local.json" if local else "settings.json"
    return Path(base) / ".claude" / name


def _resolve_hook_user(args) -> str:
    """User attribution for hook records.

    Same chain as other mutating commands, but the final fallback is
    "claude-code" instead of "user" — the actor here is the agent.
    """
    resolved = resolve_user_id_from_args(args)
    return "claude-code" if resolved == "user" else resolved


def cli_claude_code(args) -> int:
    if args.claude_code_command == "install":
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
            result = run_claude_code_install_command(
                settings_path=args.settings,
                local=args.local,
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

    if args.claude_code_command == "hook":
        # Fail-safe by default: a broken hook must never block Claude Code.
        # stdout stays empty — on UserPromptSubmit/SessionStart, hook stdout
        # is injected into the model's context.
        try:
            raw = sys.stdin.read()
            event = json.loads(raw)
            tools = (
                [t.strip() for t in args.tools.split(",") if t.strip()]
                if args.tools
                else None
            )
            result = run_claude_code_hook_command(
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
