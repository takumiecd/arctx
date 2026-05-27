"""arctx CLI verify command.

Validates the Descendant constraint (REDESIGN §10.9 invariant 7) over all
non-cut transitions in the current run.

Exit codes:
  0 — no violations
  1 — one or more violations (or command error)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from arctx_cli.context import resolve_run_id_from_args, resolve_store


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``verify`` subcommand parser."""
    p = subparsers.add_parser(
        "verify",
        help="Verify the descendant constraint over all transitions",
    )
    p.add_argument(
        "--repo",
        default=None,
        help="Repo path (default: cwd)",
    )
    p.add_argument("--run", default=None, help="Explicit run id")
    p.add_argument("--store-dir", default=None, help="Store directory")
    p.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON",
    )
    return p


def run_verify_command(
    *,
    run_id: str | None,
    store_dir: str | None,
    repo_path: Path | None = None,
    skip_dead_sha_check: bool = False,
) -> dict:
    """Execute verify and return a result dict.

    Parameters
    ----------
    run_id:
        Explicit run id (or None to auto-resolve).
    store_dir:
        Store directory (or None to use ARCTX_HOME default).
    repo_path:
        Path to git repo root. Defaults to cwd.
    skip_dead_sha_check:
        If True, skip ``git cat-file -e`` pre-checks. For testing.

    Returns
    -------
    dict with keys:
      violations: list of violation dicts
      summary: {"checked": int, "violations": int, "by_kind": {kind: int}}
    """
    store = resolve_store(store_dir)
    handle = store.load_run(run_id)

    violations = handle.git.verify(
        repo_path=repo_path,
        skip_dead_sha_check=skip_dead_sha_check,
    )

    # Count non-cut transitions that were checked.
    from arctx.core.cuts import inactive_transition_ids  # noqa: PLC0415
    graph = handle.run_graph
    inactive = inactive_transition_ids(graph)
    checked = sum(1 for t_id in graph.transitions if t_id not in inactive)

    by_kind: dict[str, int] = {}
    for v in violations:
        by_kind[v.kind] = by_kind.get(v.kind, 0) + 1

    violation_dicts = [
        {
            "transition_id": v.transition_id,
            "kind": v.kind,
            "message": v.message,
            "details": v.details,
        }
        for v in violations
    ]

    return {
        "violations": violation_dicts,
        "summary": {
            "checked": checked,
            "violations": len(violations),
            "by_kind": by_kind,
        },
    }


def cli_verify(args) -> int:
    """Entry point for ``arctx verify`` subcommand."""
    run_id = resolve_run_id_from_args(args)
    repo_path = Path(args.repo) if args.repo else None

    try:
        result = run_verify_command(
            run_id=run_id,
            store_dir=args.store_dir,
            repo_path=repo_path,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json_output:
        print(json.dumps(result, indent=2))
    else:
        summary = result["summary"]
        violations = result["violations"]
        if not violations:
            print(
                f"ok: {summary['checked']} transition(s) checked, "
                "no violations found"
            )
        else:
            print(
                f"FAIL: {summary['violations']} violation(s) in "
                f"{summary['checked']} transition(s) checked"
            )
            for v in violations:
                print(f"  [{v['kind']}] {v['transition_id']}: {v['message']}")

    return 0 if not result["violations"] else 1
