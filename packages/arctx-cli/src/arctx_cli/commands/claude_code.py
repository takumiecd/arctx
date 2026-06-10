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
            "Transitions in the session's own branch; parallel sessions land as "
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


def _hook_entry() -> dict:
    return {"type": "command", "command": HOOK_COMMAND}


def build_hooks_config(matcher: str = DEFAULT_TOOL_MATCHER) -> dict:
    """Hook entries for every event the adapter records."""
    config: dict = {}
    for event in _HOOK_EVENTS:
        entry: dict = {"hooks": [_hook_entry()]}
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
            HOOK_COMMAND in str(h.get("command", ""))
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
) -> dict:
    path = Path(settings_path) if settings_path else _default_settings_path(local=local)
    settings: dict = {}
    if path.exists():
        settings = json.loads(path.read_text(encoding="utf-8"))
    changed = merge_hooks_into_settings(settings, build_hooks_config(matcher))
    if changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return {"settings_path": str(path), "changed": changed}


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
                        {"hooks": build_hooks_config(args.matcher)},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return 0
            result = run_claude_code_install_command(
                settings_path=args.settings,
                local=args.local,
                matcher=args.matcher,
            )
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
