"""stag git subcommand — attach / start / finish / status / diff / log."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from stag.cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)
from stag.cli.append_batch import graph_counts, maybe_append_or_save
from stag.core.git.session import (
    list_sessions,
    load_current_pointer,
    load_session,
)

# ---------------------------------------------------------------------------
# Parser registration
# ---------------------------------------------------------------------------


def add_parser(subparsers) -> argparse.ArgumentParser:
    git_parser = subparsers.add_parser("git", help="Git integration commands")
    git_sub = git_parser.add_subparsers(dest="git_command", required=True)

    # --- start ---
    sp_start = git_sub.add_parser("start", help="Start a Git session for a Transition")
    sp_start.add_argument("transition_id")
    sp_start.add_argument("--run", default=None)
    sp_start.add_argument("--store-dir", default=".stag/runs")
    sp_start.add_argument("--user", default=None)

    # --- finish ---
    sp_finish = git_sub.add_parser("finish", help="Finish a Git session")
    sp_finish.add_argument("session_id")
    sp_finish.add_argument(
        "--transition",
        default=None,
        dest="transition_id",
        help="Attach Git payload to an existing result transition",
    )
    # Form A options
    sp_finish.add_argument("--status", default=None)
    sp_finish.add_argument("--summary", default=None)
    sp_finish.add_argument("--artifact", action="append")
    sp_finish.add_argument("--raw-output", action="append")
    sp_finish.add_argument("--log", action="append")
    sp_finish.add_argument("--metric", action="append")
    sp_finish.add_argument("--error", action="append")
    sp_finish.add_argument(
        "--matched-prediction", default=None, dest="matched_prediction_transition_id"
    )
    sp_finish.add_argument("--run", default=None)
    sp_finish.add_argument("--store-dir", default=".stag/runs")
    sp_finish.add_argument("--user", default=None)
    sp_finish.add_argument("--work-session", default=None)

    # --- attach ---
    sp_attach = git_sub.add_parser(
        "attach",
        help="Attach explicit Git commits to a Transition",
    )
    sp_attach.add_argument("--transition", required=True, dest="transition_id")
    sp_attach.add_argument("--commit", action="append", required=True, dest="commits")
    sp_attach.add_argument("--run", default=None)
    sp_attach.add_argument("--store-dir", default=".stag/runs")
    sp_attach.add_argument("--user", default=None)
    sp_attach.add_argument("--work-session", default=None)

    # --- status ---
    sp_status = git_sub.add_parser("status", help="Show STAG run and Git repo status")
    sp_status.add_argument("--run", default=None)
    sp_status.add_argument("--store-dir", default=".stag/runs")

    # --- diff ---
    sp_diff = git_sub.add_parser("diff", help="Show diff for a session or Transition")
    _add_session_or_transition(sp_diff)
    sp_diff.add_argument("--run", default=None)
    sp_diff.add_argument("--store-dir", default=".stag/runs")

    # --- log ---
    sp_log = git_sub.add_parser("log", help="Show commit log for a session or Transition")
    _add_session_or_transition(sp_log)
    sp_log.add_argument("--run", default=None)
    sp_log.add_argument("--store-dir", default=".stag/runs")

    return git_parser


def _add_session_or_transition(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("session_id", nargs="?", default=None)
    group.add_argument("--transition", default=None, dest="transition_id")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_metrics(metric_list: list[str] | None) -> dict[str, float]:
    metrics: dict[str, float] = {}
    for item in metric_list or []:
        if "=" not in item:
            raise ValueError(f"--metric must be key=value format: {item}")
        key, value = item.split("=", 1)
        try:
            metrics[key] = float(value)
        except ValueError:
            raise ValueError(f"--metric value must be numeric: {item}")
    return metrics


def _run_dir(store: object, run_id: str) -> Path:
    return store.run_path(run_id)  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def cli_git(args) -> int:
    if args.git_command == "attach":
        return _cli_git_attach(args)
    if args.git_command == "start":
        return _cli_git_start(args)
    if args.git_command == "finish":
        return _cli_git_finish(args)
    if args.git_command == "status":
        return _cli_git_status(args)
    if args.git_command == "diff":
        return _cli_git_diff(args)
    if args.git_command == "log":
        return _cli_git_log(args)
    print(f"unknown git subcommand: {args.git_command}", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# attach
# ---------------------------------------------------------------------------


def _cli_git_attach(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    work_session_id = resolve_work_session_id_from_args(args)

    if not store.run_path(run_id).exists():
        print(f"error: unknown run_id: {run_id}", file=sys.stderr)
        return 1

    handle = store.load_run(run_id)
    run_dir = _run_dir(store, run_id)

    from stag.core.git.attach import attach_commits_to_transition

    try:
        before = graph_counts(handle)
        result = attach_commits_to_transition(
            handle,
            run_dir,
            args.transition_id,
            tuple(args.commits),
            user_id=user_id,
            work_session_id=work_session_id,
        )
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=work_session_id,
        before=before,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


def _cli_git_start(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)

    if not store.run_path(run_id).exists():
        print(f"error: unknown run_id: {run_id}", file=sys.stderr)
        return 1

    handle = store.load_run(run_id)
    run_dir = _run_dir(store, run_id)

    from stag.core.git.start import git_start

    try:
        result = git_start(
            handle,
            run_dir,
            args.transition_id,
            user_id=user_id,
        )
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# finish
# ---------------------------------------------------------------------------


def _cli_git_finish(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    user_id = resolve_user_id_from_args(args)
    work_session_id = resolve_work_session_id_from_args(args)

    if not store.run_path(run_id).exists():
        print(f"error: unknown run_id: {run_id}", file=sys.stderr)
        return 1

    handle = store.load_run(run_id)
    run_dir = _run_dir(store, run_id)
    session_id = args.session_id

    if args.transition_id:
        form_b_options_used = []
        for opt in ("status", "summary", "artifact", "raw_output", "log", "metric", "error"):
            val = getattr(args, opt, None)
            if val:
                form_b_options_used.append(f"--{opt.replace('_', '-')}")
        if getattr(args, "matched_prediction_transition_id", None):
            form_b_options_used.append("--matched-prediction")
        if form_b_options_used:
            print(
                f"error: attach mode (--transition) does not accept: "
                f"{', '.join(form_b_options_used)}",
                file=sys.stderr,
            )
            return 1

        from stag.core.git.finish import git_finish_form_b

        try:
            before = graph_counts(handle)
            result = git_finish_form_b(
                handle,
                run_dir,
                session_id,
                transition_id=args.transition_id,
                user_id=user_id,
                work_session_id=work_session_id,
            )
        except (KeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        # Form A
        try:
            metrics = _parse_metrics(getattr(args, "metric", None))
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        from stag.core.git.finish import git_finish_form_a

        try:
            before = graph_counts(handle)
            result = git_finish_form_a(
                handle,
                run_dir,
                session_id,
                status=args.status if args.status is not None else "completed",
                summary=args.summary,
                artifacts=tuple(getattr(args, "artifact", None) or []),
                raw_outputs=tuple(getattr(args, "raw_output", None) or []),
                logs=tuple(getattr(args, "log", None) or []),
                metrics=metrics,
                errors_list=tuple(getattr(args, "error", None) or []),
                matched_prediction_transition_id=getattr(
                    args, "matched_prediction_transition_id", None
                ),
                user_id=user_id,
                work_session_id=work_session_id,
            )
        except (KeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        work_session_id=work_session_id,
        before=before,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


def _cli_git_status(args) -> int:
    import subprocess

    store = resolve_store(args.store_dir)
    try:
        run_id = resolve_run_id_from_args(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    run_dir = _run_dir(store, run_id)
    current_ptr = load_current_pointer(run_dir)
    sessions = list_sessions(run_dir)
    open_sessions = [s for s in sessions if s.is_open]

    # Git info
    from stag.core.git import repo as git_repo

    try:
        repo_root = git_repo.find_repo_root(Path("."))
        branch = git_repo.current_branch(repo_root)
        head = git_repo.current_commit(repo_root)
        dirty = git_repo.is_dirty(repo_root)
        untracked = git_repo.untracked_count(repo_root)
        git_info: dict = {
            "repo_root": str(repo_root),
            "branch": branch,
            "head_commit": head,
            "dirty": dirty,
            "untracked_count": untracked,
        }
    except Exception as exc:
        git_info = {"error": str(exc)}

    # Latest GitChangePayload in current run
    latest_gcp = None
    if store.run_path(run_id).exists():
        handle = store.load_run(run_id)
        from stag.core.schema.payloads import GitChangePayload as GCP
        from stag.core.cuts import is_inactive_transition

        gcps = [
            p
            for p in handle.run_graph.payloads.values()
            if isinstance(p, GCP) and not is_inactive_transition(handle.run_graph, p.target_id)
        ]
        if gcps:
            latest = max(gcps, key=lambda p: p.payload_id)
            latest_gcp = {
                "payload_id": latest.payload_id,
                "transition_id": latest.target_id,
                "branch": latest.branch,
                "base_commit": latest.base_commit,
                "head_commit": latest.head_commit,
            }

    out = {
        "run_id": run_id,
        "open_sessions": [
            {
                "session_id": s.session_id,
                "transition_id": s.transition_id,
                "base_branch": s.base_branch,
                "base_commit": s.base_commit,
                "started_at": s.started_at,
            }
            for s in open_sessions
        ],
        "current_session_pointer": current_ptr,
        "git": git_info,
        "latest_git_change_payload": latest_gcp,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------


def _cli_git_diff(args) -> int:
    store = resolve_store(args.store_dir)
    try:
        run_id = resolve_run_id_from_args(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    run_dir = _run_dir(store, run_id)

    if args.transition_id:
        handle = store.load_run(run_id)
        transition_id = args.transition_id
        if transition_id not in handle.run_graph.transitions:
            print(f"error: unknown transition_id: {transition_id}", file=sys.stderr)
            return 1
        from stag.core.schema.payloads import GitChangePayload as GCP

        gcps = handle.run_graph.payloads_for_transition(transition_id, payload_type="git_change")
        if not gcps:
            print(f"error: no GitChangePayload attached to {transition_id}", file=sys.stderr)
            return 1
        if len(gcps) > 1:
            print(
                f"Multiple GitChangePayloads on {transition_id}:\n"
                + "\n".join(f"  {p.payload_id}" for p in gcps)
                + "\nSpecify --payload <pl_id> (future feature) to select one.",
                file=sys.stderr,
            )
            return 1
        gcp = gcps[0]
        if not gcp.patch_artifact:
            print("(no patch artifact — diff was empty)")
            return 0
        patch_path = run_dir / gcp.patch_artifact
        if not patch_path.exists():
            print(f"error: patch artifact not found: {patch_path}", file=sys.stderr)
            return 1
        print(patch_path.read_text(encoding="utf-8"), end="")
        return 0

    else:
        # Show live diff from session base..HEAD
        session_id = args.session_id
        if not session_id:
            print("error: provide <session_id> or --transition", file=sys.stderr)
            return 1
        try:
            session = load_session(session_id, run_dir)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        from stag.core.git import repo as git_repo

        try:
            repo_root = git_repo.find_repo_root(Path("."))
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        patch = git_repo.diff_patch(repo_root, session.base_commit)
        if not patch:
            print("(empty diff)")
            return 0
        print(patch, end="")
        return 0


# ---------------------------------------------------------------------------
# log
# ---------------------------------------------------------------------------


def _cli_git_log(args) -> int:
    store = resolve_store(args.store_dir)
    try:
        run_id = resolve_run_id_from_args(args)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    run_dir = _run_dir(store, run_id)

    if args.transition_id:
        handle = store.load_run(run_id)
        transition_id = args.transition_id
        if transition_id not in handle.run_graph.transitions:
            print(f"error: unknown transition_id: {transition_id}", file=sys.stderr)
            return 1
        gcps = handle.run_graph.payloads_for_transition(transition_id, payload_type="git_change")
        if not gcps:
            print(f"error: no GitChangePayload attached to {transition_id}", file=sys.stderr)
            return 1
        if len(gcps) > 1:
            print(
                f"Multiple GitChangePayloads on {transition_id}:\n"
                + "\n".join(f"  {p.payload_id}" for p in gcps)
                + "\nSpecify --payload <pl_id> (future feature) to select one.",
                file=sys.stderr,
            )
            return 1
        gcp = gcps[0]
        out = [c.to_dict() for c in gcp.commit_log]
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    else:
        session_id = args.session_id
        if not session_id:
            print("error: provide <session_id> or --transition", file=sys.stderr)
            return 1
        try:
            session = load_session(session_id, run_dir)
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        from stag.core.git import repo as git_repo

        try:
            repo_root = git_repo.find_repo_root(Path("."))
        except Exception as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1

        entries = git_repo.commit_log(repo_root, session.base_commit)
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0
