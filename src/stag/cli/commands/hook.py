"""stag CLI hook commands.

Subcommands:
  stag hook install [--force]  — Install .git/hooks/post-rewrite
  stag hook post-rewrite <mode> — Process stdin sha_map and call adopt_rewrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Hook script content
# ---------------------------------------------------------------------------

_POST_REWRITE_HOOK = """\
#!/usr/bin/env bash
# .git/hooks/post-rewrite — stag amend/rebase tracking
# argv: $1 = "amend" | "rebase"
# stdin: one line per rewrite: "<old_sha> <new_sha>"
exec stag hook post-rewrite "$1"
"""


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``hook`` subcommand parser."""
    parser = subparsers.add_parser("hook", help="Manage git hooks for stag integration")
    hook_sub = parser.add_subparsers(dest="hook_command", required=True)

    # install subcommand
    install_parser = hook_sub.add_parser(
        "install", help="Install .git/hooks/post-rewrite"
    )
    install_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing hook without prompting",
    )
    install_parser.add_argument(
        "--repo-path",
        default=None,
        help="Path to git repo root (default: cwd)",
    )

    # post-rewrite subcommand (called by the hook script)
    post_rewrite_parser = hook_sub.add_parser(
        "post-rewrite",
        help="Process a post-rewrite hook invocation (reads stdin)",
    )
    post_rewrite_parser.add_argument(
        "mode",
        choices=["amend", "rebase"],
        help="The rewrite mode passed by git",
    )
    post_rewrite_parser.add_argument("--run", default=None)
    post_rewrite_parser.add_argument("--store-dir", default=None)

    return parser


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def run_hook_install(
    *,
    repo_path: Path | None = None,
    force: bool = False,
) -> dict:
    """Install .git/hooks/post-rewrite in the git repo.

    Parameters
    ----------
    repo_path:
        Path to the git repository root. Defaults to cwd.
    force:
        If True, overwrite an existing hook. If False and the hook already
        exists, skip and return status="skipped".

    Returns
    -------
    dict with keys:
        - status: "installed", "skipped", or "error"
        - hook_path: absolute path to the hook file
        - message: human-readable description
    """
    from stag.cli.paths import find_repo_root  # noqa: PLC0415

    resolved_root: Path
    if repo_path is not None:
        resolved_root = Path(repo_path)
    else:
        try:
            resolved_root = find_repo_root()
        except RuntimeError as exc:
            return {
                "status": "error",
                "hook_path": None,
                "message": str(exc),
            }

    hooks_dir = resolved_root / ".git" / "hooks"
    if not hooks_dir.exists():
        return {
            "status": "error",
            "hook_path": None,
            "message": f".git/hooks directory not found at {hooks_dir}",
        }

    hook_path = hooks_dir / "post-rewrite"

    if hook_path.exists() and not force:
        return {
            "status": "skipped",
            "hook_path": str(hook_path),
            "message": (
                f"hook already exists at {hook_path}; "
                "use --force to overwrite"
            ),
        }

    hook_path.write_text(_POST_REWRITE_HOOK, encoding="utf-8")
    hook_path.chmod(0o755)

    return {
        "status": "installed",
        "hook_path": str(hook_path),
        "message": f"installed post-rewrite hook at {hook_path}",
    }


# ---------------------------------------------------------------------------
# post-rewrite
# ---------------------------------------------------------------------------


def run_hook_post_rewrite(
    *,
    mode: str,
    run_id: str,
    store_dir: str | None,
    stdin_lines: list[str] | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> dict:
    """Process a post-rewrite hook invocation.

    Reads sha_map from stdin (or ``stdin_lines`` for testing), calls
    ``RunHandle.adopt_rewrite``, and persists the run.

    Parameters
    ----------
    mode:
        "amend" or "rebase" (the first argument git passes to post-rewrite).
    run_id:
        The stag run to update.
    store_dir:
        Run store directory. If None, uses default.
    stdin_lines:
        Override stdin lines (for testing). Each line: "<old_sha> <new_sha>".
    user_id:
        User ID for work events.
    work_session_id:
        Work session ID for work events.

    Returns
    -------
    dict with keys from ``adopt_rewrite``:
        - affected_transitions, skipped_shas, event_id
    """
    from stag.cli.context import resolve_store  # noqa: PLC0415
    import os  # noqa: PLC0415

    # Parse sha_map from stdin.
    if stdin_lines is None:
        stdin_lines = sys.stdin.read().splitlines()

    sha_map: dict[str, str] = {}
    for line in stdin_lines:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 2:
            sha_map[parts[0]] = parts[1]

    if not sha_map:
        return {
            "affected_transitions": [],
            "skipped_shas": [],
            "event_id": None,
        }

    # Resolve onto = last new_sha.
    onto = list(sha_map.values())[-1]

    # Resolve user / session from env if not provided.
    if user_id is None:
        user_id = os.environ.get("STAG_USER_ID", "user")
    if work_session_id is None:
        work_session_id = os.environ.get("STAG_WORK_SESSION_ID", "session_hook")

    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    result = handle.adopt_rewrite(
        sha_map=sha_map,
        onto=onto,
        mode=mode,
        user_id=user_id,
        work_session_id=work_session_id,
    )

    store.save_run(handle)
    return result


# ---------------------------------------------------------------------------
# CLI dispatcher
# ---------------------------------------------------------------------------


def cli_hook(args) -> int:
    """Entry point for ``stag hook`` subcommands."""
    if args.hook_command == "install":
        repo_path = Path(args.repo_path) if args.repo_path else None
        result = run_hook_install(repo_path=repo_path, force=args.force)
        if result["status"] == "error":
            print(f"error: {result['message']}", file=sys.stderr)
            return 1
        if result["status"] == "skipped":
            print(f"warning: {result['message']}", file=sys.stderr)
            return 0
        print(result["message"])
        return 0

    if args.hook_command == "post-rewrite":
        from stag.cli.context import resolve_run_id_from_args  # noqa: PLC0415
        import os  # noqa: PLC0415

        try:
            run_id = resolve_run_id_from_args(args)
        except Exception as exc:
            print(f"stag hook post-rewrite: could not resolve run: {exc}", file=sys.stderr)
            # Exit 0 so git continues even if stag can't find the run.
            return 0

        result = run_hook_post_rewrite(
            mode=args.mode,
            run_id=run_id,
            store_dir=args.store_dir,
            user_id=os.environ.get("STAG_USER_ID"),
            work_session_id=os.environ.get("STAG_WORK_SESSION_ID"),
        )
        n_affected = len(result.get("affected_transitions", []))
        n_skipped = len(result.get("skipped_shas", []))
        print(
            f"stag: post-rewrite ({args.mode}): "
            f"{n_affected} transition(s) updated, {n_skipped} sha(s) skipped",
            file=sys.stderr,
        )
        return 0

    return 1
