"""arctx CLI hook commands.

Subcommands:
  arctx git hook install [--force]  — Install .git/hooks/post-rewrite
  arctx git hook post-rewrite <mode> — Process stdin sha_map and call adopt_rewrite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from arctx.ext.git.helpers.repo import resolve_worktree_path
from arctx.ext.git.queries import transition_by_sha

# ---------------------------------------------------------------------------
# Hook script content
# ---------------------------------------------------------------------------

_POST_REWRITE_HOOK = """\
#!/usr/bin/env bash
# .git/hooks/post-rewrite — arctx amend/rebase tracking
# argv: $1 = "amend" | "rebase"
# stdin: one line per rewrite: "<old_sha> <new_sha>"
exec arctx git hook post-rewrite "$1"
"""

_POST_COMMIT_HOOK = """\
#!/usr/bin/env bash
# .git/hooks/post-commit — arctx revert/cherry-pick fallback tracking
# Detects bare git revert / cherry-pick and records a arctx transition.
exec arctx git hook post-commit
"""

_POST_MERGE_HOOK = """\
#!/usr/bin/env bash
# .git/hooks/post-merge — arctx merge tracking
# Detects a bare `git merge` (not driven by arctx merge) and attempts to
# adopt the merge commit into the arctx graph.
# argv: $1 = 1 if squash merge, 0 otherwise
exec arctx git hook post-merge "$1"
"""


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``hook`` subcommand parser."""
    parser = subparsers.add_parser("hook", help="Manage git hooks for arctx integration")
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

    # post-commit subcommand (called by the hook script)
    post_commit_parser = hook_sub.add_parser(
        "post-commit",
        help="Process a post-commit hook invocation (revert/cherry-pick fallback)",
    )
    post_commit_parser.add_argument("--run", default=None)
    post_commit_parser.add_argument("--store-dir", default=None)
    post_commit_parser.add_argument(
        "--repo-path",
        default=None,
        help="Path to git repo root (default: cwd)",
    )

    # post-merge subcommand (called by the hook script)
    post_merge_parser = hook_sub.add_parser(
        "post-merge",
        help="Process a post-merge hook invocation (adopt bare git merge)",
    )
    post_merge_parser.add_argument(
        "squash",
        nargs="?",
        default="0",
        help="1 if squash merge, 0 otherwise (passed by git)",
    )
    post_merge_parser.add_argument("--run", default=None)
    post_merge_parser.add_argument("--store-dir", default=None)
    post_merge_parser.add_argument(
        "--repo-path",
        default=None,
        help="Path to git repo root (default: cwd)",
    )

    return parser


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------


def run_hook_install(
    *,
    repo_path: Path | None = None,
    force: bool = False,
) -> dict:
    """Install .git/hooks/post-rewrite and .git/hooks/post-commit in the git repo.

    Parameters
    ----------
    repo_path:
        Path to the git repository root. Defaults to cwd.
    force:
        If True, overwrite existing hooks. If False and hooks already exist,
        skip them and return status="skipped".

    Returns
    -------
    dict with keys:
        - status: "installed", "skipped", or "error"
        - hook_path: absolute path to the post-rewrite hook file
        - message: human-readable description
    """
    from arctx_cli.paths import find_repo_root  # noqa: PLC0415

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

    post_rewrite_path = hooks_dir / "post-rewrite"
    post_commit_path = hooks_dir / "post-commit"
    post_merge_path = hooks_dir / "post-merge"

    # Backward-compatible: if post-rewrite already exists and force=False, skip all.
    if post_rewrite_path.exists() and not force:
        return {
            "status": "skipped",
            "hook_path": str(post_rewrite_path),
            "message": (
                f"hook already exists at {post_rewrite_path}; "
                "use --force to overwrite"
            ),
        }

    # Install post-rewrite.
    post_rewrite_path.write_text(_POST_REWRITE_HOOK, encoding="utf-8")
    post_rewrite_path.chmod(0o755)

    # Install post-commit (best-effort; skip silently if it already exists and not force).
    if not post_commit_path.exists() or force:
        post_commit_path.write_text(_POST_COMMIT_HOOK, encoding="utf-8")
        post_commit_path.chmod(0o755)

    # Install post-merge (best-effort; skip silently if it already exists and not force).
    if not post_merge_path.exists() or force:
        post_merge_path.write_text(_POST_MERGE_HOOK, encoding="utf-8")
        post_merge_path.chmod(0o755)

    return {
        "status": "installed",
        "hook_path": str(post_rewrite_path),
        "message": f"installed post-rewrite, post-commit, and post-merge hooks under {hooks_dir}",
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
    ``RunHandle.git.adopt_rewrite``, and persists the run.

    Parameters
    ----------
    mode:
        "amend" or "rebase" (the first argument git passes to post-rewrite).
    run_id:
        The arctx run to update.
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
    import os  # noqa: PLC0415

    from arctx_cli.context import resolve_store  # noqa: PLC0415

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
        user_id = os.environ.get("ARCTX_USER_ID", "user")
    if work_session_id is None:
        work_session_id = os.environ.get("ARCTX_WORK_SESSION_ID", "session_hook")

    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    result = handle.git.adopt_rewrite(
        sha_map=sha_map,
        onto=onto,
        mode=mode,
        user_id=user_id,
        work_session_id=work_session_id,
    )

    store.save_run(handle)
    return result


# ---------------------------------------------------------------------------
# post-commit
# ---------------------------------------------------------------------------

# Regex patterns for detecting revert / cherry-pick from commit subject/body.
import re as _re

_REVERT_SUBJECT_RE = _re.compile(r'^Revert "(.+)"$')
_REVERT_SHA_RE = _re.compile(r"This reverts commit ([0-9a-f]{7,40})")
_CHERRY_PICK_RE = _re.compile(r"cherry picked from commit ([0-9a-f]{7,40})", _re.IGNORECASE)


def run_hook_post_commit(
    *,
    run_id: str,
    store_dir: str | None,
    repo_path: Path | None = None,
    user_id: str | None = None,
    work_session_id: str | None = None,
    # Test injection: override HEAD info instead of running git.
    head_sha: str | None = None,
    head_subject: str | None = None,
    head_body: str | None = None,
) -> dict:
    """Process a post-commit hook invocation.

    Detects whether the newest commit is a bare ``git revert`` or
    ``git cherry-pick`` (i.e. not driven by ``arctx revert`` / ``arctx
    cherry-pick``) and records the appropriate arctx transition if so.

    Detection logic
    ---------------
    1. Read HEAD: sha, subject, full body via ``git log -1``.
    2. Check whether HEAD sha is already known to arctx
       (``transition_by_sha``).  If it is, arctx already recorded it —
       return early.
    3. Match subject/body against revert / cherry-pick patterns.
    4. If matched, call ``handle.revert`` / ``handle.cherry_pick`` with
       ``head_commit`` injected so git is not called a second time.

    For revert, the reverted sha is extracted from the body line
    ``This reverts commit <sha>.``

    For cherry-pick, the source sha is extracted from the trailer
    ``cherry picked from commit <sha>`` (added by ``git cherry-pick -x``).
    If the trailer is absent, detection is skipped (best-effort only).

    Returns
    -------
    dict with keys:
        - action: "revert", "cherry_pick", "skip", or "warn"
        - transition_id: the new arctx transition ID (or None)
        - message: human-readable description
    """
    import os  # noqa: PLC0415
    import subprocess as _sp  # noqa: PLC0415

    from arctx_cli.context import resolve_store  # noqa: PLC0415

    resolved_repo_path: Path = resolve_worktree_path(repo_path)

    # Resolve user / session from env if not provided.
    if user_id is None:
        user_id = os.environ.get("ARCTX_USER_ID", "user")
    if work_session_id is None:
        work_session_id = os.environ.get("ARCTX_WORK_SESSION_ID", "session_hook")

    # ------------------------------------------------------------------
    # 1. Read HEAD info (or use injected values for testing).
    # ------------------------------------------------------------------
    if head_sha is None or head_subject is None or head_body is None:
        try:
            log_result = _sp.run(
                ["git", "log", "-1", "--format=%H%n%s%n%B"],
                cwd=str(resolved_repo_path),
                capture_output=True,
                text=True,
                check=True,
            )
            lines = log_result.stdout.splitlines()
            head_sha = lines[0].strip() if lines else ""
            head_subject = lines[1].strip() if len(lines) > 1 else ""
            head_body = "\n".join(lines[2:]) if len(lines) > 2 else ""
        except Exception as exc:  # noqa: BLE001
            return {
                "action": "warn",
                "transition_id": None,
                "message": f"could not read git HEAD: {exc}",
            }

    if not head_sha:
        return {
            "action": "skip",
            "transition_id": None,
            "message": "no HEAD sha found",
        }

    # ------------------------------------------------------------------
    # 2. Check if arctx already knows this sha.
    # ------------------------------------------------------------------
    store = resolve_store(store_dir)
    try:
        handle = store.load_run(run_id)
    except Exception as exc:  # noqa: BLE001
        return {
            "action": "warn",
            "transition_id": None,
            "message": f"could not load run: {exc}",
        }

    if transition_by_sha(handle.run_graph, head_sha) is not None:
        # Already recorded by arctx revert/cherry-pick/commit — skip.
        return {
            "action": "skip",
            "transition_id": None,
            "message": "HEAD sha already recorded by arctx",
        }

    # ------------------------------------------------------------------
    # 3. Detect revert.
    # ------------------------------------------------------------------
    revert_match = _REVERT_SUBJECT_RE.match(head_subject)
    if revert_match:
        sha_match = _REVERT_SHA_RE.search(head_body)
        if sha_match:
            reverted_sha = sha_match.group(1)
            # Look up the reverted transition.
            reverted_t = transition_by_sha(handle.run_graph, reverted_sha)
            if reverted_t is None:
                # We don't know the original commit — skip; can't link properly.
                return {
                    "action": "warn",
                    "transition_id": None,
                    "message": (
                        f"post-commit: revert of {reverted_sha[:12]} detected but "
                        "original commit not in arctx graph; skipping"
                    ),
                }
            try:
                transition = handle.git.revert(
                    target_transition=reverted_t,
                    user_id=user_id,
                    work_session_id=work_session_id,
                    head_commit=head_sha,
                    dry_run=True,  # git already ran; just record
                )
                store.save_run(handle)
                return {
                    "action": "revert",
                    "transition_id": transition.transition_id,
                    "message": (
                        f"post-commit: recorded revert of {reverted_sha[:12]} "
                        f"as {transition.transition_id}"
                    ),
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "action": "warn",
                    "transition_id": None,
                    "message": f"post-commit: failed to record revert: {exc}",
                }

    # ------------------------------------------------------------------
    # 4. Detect cherry-pick (best-effort; requires -x trailer).
    # ------------------------------------------------------------------
    cp_match = _CHERRY_PICK_RE.search(head_body)
    if cp_match:
        source_sha = cp_match.group(1)
        try:
            transition = handle.git.cherry_pick(
                source_sha=source_sha,
                user_id=user_id,
                work_session_id=work_session_id,
                head_commit=head_sha,
                dry_run=True,  # git already ran; just record
            )
            store.save_run(handle)
            return {
                "action": "cherry_pick",
                "transition_id": transition.transition_id,
                "message": (
                    f"post-commit: recorded cherry-pick of {source_sha[:12]} "
                    f"as {transition.transition_id}"
                ),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "action": "warn",
                "transition_id": None,
                "message": f"post-commit: failed to record cherry-pick: {exc}",
            }

    # Not a revert or detectable cherry-pick — nothing to do.
    return {
        "action": "skip",
        "transition_id": None,
        "message": "post-commit: not a revert or cherry-pick (no pattern matched)",
    }


# ---------------------------------------------------------------------------
# post-merge
# ---------------------------------------------------------------------------


def run_hook_post_merge(
    *,
    run_id: str,
    store_dir: str | None,
    repo_path: Path | None = None,
    squash: bool = False,
    user_id: str | None = None,
    work_session_id: str | None = None,
    # Test injection: override HEAD info.
    head_sha: str | None = None,
) -> dict:
    """Process a post-merge hook invocation.

    Detects whether the newest commit is a merge commit that arctx has not
    yet recorded, and adopts it by calling ``handle.git.merge(dry_run=True)``.

    Detection logic
    ---------------
    1. Read HEAD sha via ``git rev-parse HEAD``.
    2. Check if HEAD sha is already known to arctx.  If yes, skip (arctx merge
       already ran via ``arctx merge`` or ``arctx commit --merge``).
    3. Check if HEAD has two parents (``git rev-parse HEAD^2`` succeeds).
       If squash merge (squash=True), HEAD has only one parent but this hook
       still fires — log a warning and skip.
    4. If a real merge commit: call ``handle.git.merge(dry_run=True, ...)`` to
       adopt it into the arctx graph.

    Returns
    -------
    dict with keys:
        - action: "adopted", "skip", or "warn"
        - transition_id: new arctx transition ID (or None)
        - message: human-readable description
    """
    import os  # noqa: PLC0415
    import subprocess as _sp  # noqa: PLC0415

    from arctx_cli.context import resolve_store  # noqa: PLC0415

    resolved_repo_path: Path = resolve_worktree_path(repo_path)

    if user_id is None:
        user_id = os.environ.get("ARCTX_USER_ID", "user")
    if work_session_id is None:
        work_session_id = os.environ.get("ARCTX_WORK_SESSION_ID", "session_hook")

    # ------------------------------------------------------------------
    # 1. Squash merge: cannot adopt automatically (no merge commit).
    # ------------------------------------------------------------------
    if squash:
        return {
            "action": "skip",
            "transition_id": None,
            "message": "post-merge: squash merge — skipping automatic adoption",
        }

    # ------------------------------------------------------------------
    # 2. Read HEAD sha.
    # ------------------------------------------------------------------
    if head_sha is None:
        try:
            result = _sp.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(resolved_repo_path),
                capture_output=True,
                text=True,
                check=True,
            )
            head_sha = result.stdout.strip()
        except Exception as exc:  # noqa: BLE001
            return {
                "action": "warn",
                "transition_id": None,
                "message": f"post-merge: could not read HEAD sha: {exc}",
            }

    if not head_sha:
        return {
            "action": "skip",
            "transition_id": None,
            "message": "post-merge: no HEAD sha found",
        }

    # ------------------------------------------------------------------
    # 3. Load run and check if already known.
    # ------------------------------------------------------------------
    store = resolve_store(store_dir)
    try:
        handle = store.load_run(run_id)
    except Exception as exc:  # noqa: BLE001
        return {
            "action": "warn",
            "transition_id": None,
            "message": f"post-merge: could not load run: {exc}",
        }

    if transition_by_sha(handle.run_graph, head_sha) is not None:
        return {
            "action": "skip",
            "transition_id": None,
            "message": "post-merge: HEAD sha already recorded by arctx",
        }

    # ------------------------------------------------------------------
    # 4. Verify HEAD is actually a merge commit (has ^2 parent).
    # ------------------------------------------------------------------
    try:
        p2_result = _sp.run(
            ["git", "rev-parse", "--verify", "HEAD^2"],
            cwd=str(resolved_repo_path),
            capture_output=True,
            text=True,
        )
        if p2_result.returncode != 0:
            return {
                "action": "skip",
                "transition_id": None,
                "message": "post-merge: HEAD is not a merge commit (no second parent)",
            }
        other_sha = p2_result.stdout.strip()
    except Exception as exc:  # noqa: BLE001
        return {
            "action": "warn",
            "transition_id": None,
            "message": f"post-merge: could not verify merge parents: {exc}",
        }

    # ------------------------------------------------------------------
    # 5. Adopt: call merge with dry_run=True (git already ran).
    # ------------------------------------------------------------------
    # Look up the other node by its sha, if known.
    other_node_id: str | None = None
    other_transition_id = transition_by_sha(handle.run_graph, other_sha)
    if other_transition_id is not None:
        other_t = handle.run_graph.transitions.get(other_transition_id)
        if other_t is not None:
            other_node_id = other_t.output_node_id

    try:
        transition = handle.git.merge(
            other_node_id=other_node_id,
            other_branch=None,  # branch unknown from hook context
            head_commit=head_sha,
            user_id=user_id,
            work_session_id=work_session_id,
            dry_run=True,  # git already merged
        )
        store.save_run(handle)
        return {
            "action": "adopted",
            "transition_id": transition.transition_id,
            "message": (
                f"post-merge: adopted merge commit {head_sha[:12]} "
                f"as {transition.transition_id}"
            ),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "action": "warn",
            "transition_id": None,
            "message": f"post-merge: could not adopt merge: {exc}",
        }


# ---------------------------------------------------------------------------
# CLI dispatcher
# ---------------------------------------------------------------------------


def cli_hook(args) -> int:
    """Entry point for ``arctx hook`` subcommands."""
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
        import os  # noqa: PLC0415

        from arctx_cli.context import resolve_run_id_from_args  # noqa: PLC0415

        try:
            run_id = resolve_run_id_from_args(args)
        except Exception as exc:
            print(f"arctx hook post-rewrite: could not resolve run: {exc}", file=sys.stderr)
            # Exit 0 so git continues even if arctx can't find the run.
            return 0

        result = run_hook_post_rewrite(
            mode=args.mode,
            run_id=run_id,
            store_dir=args.store_dir,
            user_id=os.environ.get("ARCTX_USER_ID"),
            work_session_id=os.environ.get("ARCTX_WORK_SESSION_ID"),
        )
        n_affected = len(result.get("affected_transitions", []))
        n_skipped = len(result.get("skipped_shas", []))
        print(
            f"arctx: post-rewrite ({args.mode}): "
            f"{n_affected} transition(s) updated, {n_skipped} sha(s) skipped",
            file=sys.stderr,
        )
        return 0

    if args.hook_command == "post-commit":
        import os  # noqa: PLC0415

        from arctx_cli.context import resolve_run_id_from_args  # noqa: PLC0415

        try:
            run_id = resolve_run_id_from_args(args)
        except Exception as exc:
            print(f"arctx hook post-commit: could not resolve run: {exc}", file=sys.stderr)
            return 0

        repo_path = Path(args.repo_path) if getattr(args, "repo_path", None) else None
        result = run_hook_post_commit(
            run_id=run_id,
            store_dir=args.store_dir,
            repo_path=repo_path,
            user_id=os.environ.get("ARCTX_USER_ID"),
            work_session_id=os.environ.get("ARCTX_WORK_SESSION_ID"),
        )
        print(
            f"arctx: post-commit: {result['action']}: {result['message']}",
            file=sys.stderr,
        )
        return 0

    if args.hook_command == "post-merge":
        import os  # noqa: PLC0415

        from arctx_cli.context import resolve_run_id_from_args  # noqa: PLC0415

        try:
            run_id = resolve_run_id_from_args(args)
        except Exception as exc:
            print(f"arctx hook post-merge: could not resolve run: {exc}", file=sys.stderr)
            # Exit 0 so git continues even if arctx can't find the run.
            return 0

        repo_path = Path(args.repo_path) if getattr(args, "repo_path", None) else None
        squash_arg = getattr(args, "squash", "0")
        squash = squash_arg == "1"

        result = run_hook_post_merge(
            run_id=run_id,
            store_dir=args.store_dir,
            repo_path=repo_path,
            squash=squash,
            user_id=os.environ.get("ARCTX_USER_ID"),
            work_session_id=os.environ.get("ARCTX_WORK_SESSION_ID"),
        )
        print(
            f"arctx: post-merge: {result['action']}: {result['message']}",
            file=sys.stderr,
        )
        return 0

    return 1
