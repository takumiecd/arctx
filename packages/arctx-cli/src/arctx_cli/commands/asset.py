"""arctx CLI ``asset`` command — attach and inspect git-object references.

    arctx asset attach n_ab12 results/plot.png            # HEAD:results/plot.png
    arctx asset attach t_cd34 bench/out --commit v0.3.1   # a directory, at a tag
    arctx asset show pl_ef56                              # does it still resolve?

An asset is a reference, not a copy: commit the file first, then attach. The
repository is always the one enclosing the run data ("absent = self"), so
there is no repo argument.
"""

from __future__ import annotations

import argparse
import json
import sys

from arctx.core.gitref import (
    GitRefError,
    guess_content_type,
    object_kind,
    repo_root_for,
    unpushed_warning,
)

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import (
    resolve_lane_id_from_args,
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
)
from arctx_cli.lane_gate import ensure_lane_open
from arctx_cli.post_write_check import warn_if_invalid


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``asset`` command."""
    parser = subparsers.add_parser(
        "asset",
        help="Attach or inspect a git-object asset ((commit, path) reference)",
        description=(
            "Assets are references to git objects, never copies: `asset attach "
            "TARGET_ID PATH` records (commit, path) on a Node or Step, where PATH "
            "is a file or a directory in the enclosing repository. Commit the file "
            "first — an uncommitted path cannot be referenced. `asset show "
            "PAYLOAD_ID` reports whether the reference still resolves in this clone."
        ),
    )
    sub = parser.add_subparsers(dest="asset_command", required=True)

    attach = sub.add_parser("attach", help="Attach a git object to a Node or Step")
    attach.add_argument("target_id")
    attach.add_argument("path", help="File or directory path (repo-root- or cwd-relative)")
    attach.add_argument("--commit", default=None, help="Commit-ish to reference (default: HEAD)")
    attach.add_argument("--title", default=None, help="Optional human label")
    attach.add_argument("--run", default=None)
    attach.add_argument("--store-dir", default=None)
    attach.add_argument("--user", default=None)
    attach.add_argument("--lane", default=None)
    attach.add_argument("--force", action="store_true",
                        help="Write even if the target lane is closed")

    show = sub.add_parser("show", help="Show an asset reference and whether it resolves")
    show.add_argument("payload_id")
    show.add_argument("--run", default=None)
    show.add_argument("--store-dir", default=None)

    return parser


def run_asset_attach_command(
    *,
    run_id: str,
    target_id: str,
    path: str,
    commit: str | None,
    title: str | None,
    store_dir: str | None,
    user_id: str | None = None,
    lane_id: str | None = None,
    force: bool = False,
) -> dict:
    """Record a ``(commit, path)`` reference on a Node or Step."""
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    ensure_lane_open(handle, lane_id, force=force)

    before = graph_counts(handle)
    result = handle.attach_asset(
        target_id,
        path,
        commit=commit,
        title=title,
        user_id=user_id,
        lane_id=lane_id,
    )
    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        lane_id=lane_id,
        before=before,
        force=force,
    )
    return {
        "payload": result.payload.to_dict(),
        "kind": result.kind,
        "warning": result.warning,
    }


def run_asset_show_command(*, run_id: str, payload_id: str, store_dir: str | None) -> dict:
    """Return an asset reference plus whether it resolves in this clone."""
    from arctx.core.schema.payloads import AssetPayload

    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    payload = handle.run_graph.payloads.get(payload_id)
    if payload is None:
        raise KeyError(f"unknown payload_id: {payload_id}")
    if not isinstance(payload, AssetPayload):
        raise ValueError(
            f"payload {payload_id} is not an asset (payload_type={payload.payload_type})"
        )

    view: dict = {
        "asset": payload.to_dict(),
        "reference": f"{payload.commit[:12]}:{payload.path or '.'}",
    }
    try:
        repo_root = repo_root_for(store.run_path(run_id))
    except GitRefError as exc:
        view["resolution"] = {"status": "no_repository", "message": str(exc)}
        return view

    try:
        kind = object_kind(repo_root, payload.commit, payload.path)
    except GitRefError as exc:
        status = type(exc).__name__
        code = {
            "MissingCommit": "missing_commit",
            "MissingPath": "missing_path",
        }.get(status, "git_error")
        view["resolution"] = {"status": code, "message": str(exc)}
        return view

    view["resolution"] = {
        "status": "found",
        "kind": kind,
        "content_type": guess_content_type(payload.path) if kind == "blob" else None,
    }
    warning = unpushed_warning(repo_root, payload.commit)
    if warning:
        view["warning"] = warning
    return view


def cli_asset(args) -> int:
    """Dispatch ``arctx asset attach`` / ``arctx asset show``."""
    try:
        run_id = resolve_run_id_from_args(args)
        if args.asset_command == "attach":
            result = run_asset_attach_command(
                run_id=run_id,
                target_id=args.target_id,
                path=args.path,
                commit=args.commit,
                title=args.title,
                store_dir=args.store_dir,
                user_id=resolve_user_id_from_args(args),
                lane_id=resolve_lane_id_from_args(args),
                force=args.force,
            )
            print(json.dumps(result["payload"], ensure_ascii=False, indent=2))
            if result["warning"]:
                print(f"warning: {result['warning']}", file=sys.stderr)
            strict_rc = warn_if_invalid(run_id, args.store_dir, command_name="asset")
            return strict_rc or 0

        result = run_asset_show_command(
            run_id=run_id,
            payload_id=args.payload_id,
            store_dir=args.store_dir,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, ValueError, GitRefError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
