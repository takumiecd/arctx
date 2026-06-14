"""arctx CLI migrate command — convert a jsonl run directory to sqlite."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from arctx.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``migrate`` subcommand parser."""
    parser = subparsers.add_parser(
        "migrate",
        help="Migrate run storage format (currently: jsonl -> sqlite)",
    )
    parser.add_argument(
        "--to",
        required=True,
        choices=["sqlite"],
        help="Target storage format",
    )
    parser.add_argument(
        "--store-dir",
        default=None,
        help="Directory where runs are stored (default: <ARCTX_HOME>/runs)",
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--run", metavar="RUN_ID", help="Single run ID to migrate")
    target.add_argument("--all", action="store_true", help="Migrate all runs in store-dir")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing run.db if present",
    )
    return parser


def run_migrate_command(
    *,
    to: str,
    store_dir: str | None,
    run_id: str | None,
    all_runs: bool,
    force: bool,
) -> dict:
    """Migrate one or all jsonl runs to sqlite.

    Parameters
    ----------
    to:
        Target format, currently only ``"sqlite"`` is supported.
    store_dir:
        Root directory of the run store.
    run_id:
        Single run to migrate. Mutually exclusive with *all_runs*.
    all_runs:
        When True, migrate all runs found via ``JsonlRunStore.list_runs()``.
    force:
        When True, overwrite an existing ``run.db`` instead of skipping.

    Returns
    -------
    dict with ``migrated``, ``skipped``, and ``failed`` lists of run IDs.
    """
    if to != "sqlite":
        raise ValueError(f"unsupported target format: {to!r}")

    if store_dir is None:
        from arctx_cli.paths import resolve_store_dir  # noqa: PLC0415

        store_dir = resolve_store_dir()

    src_store = JsonlRunStore(store_dir)
    from arctx.storage.sqlite import SqliteRunStore

    dst_store = SqliteRunStore(store_dir)

    if all_runs:
        run_ids = [r["run_id"] for r in src_store.list_runs()]
    else:
        if run_id is None:
            raise ValueError("either --run or --all must be specified")
        run_ids = [run_id]

    migrated: list[str] = []
    skipped: list[str] = []
    failed: list[str] = []

    for rid in run_ids:
        run_path = Path(store_dir) / rid
        nodes_jsonl = run_path / "nodes.jsonl"
        db_path = run_path / "run.db"

        # Must look like a jsonl run dir
        if not nodes_jsonl.exists():
            print(
                f"warning: {rid}: nodes.jsonl not found — not a jsonl run, skipping",
                file=sys.stderr,
            )
            skipped.append(rid)
            continue

        # Already migrated?
        if db_path.exists() and not force:
            print(
                f"warning: {rid}: run.db already exists — skipping (use --force to overwrite)",
                file=sys.stderr,
            )
            skipped.append(rid)
            continue

        # Remove stale db so SqliteRunStore starts fresh
        if db_path.exists() and force:
            db_path.unlink()

        try:
            handle = src_store.load_run(rid)
            dst_store.save_run(handle)
            migrated.append(rid)
        except Exception as exc:  # noqa: BLE001
            print(f"error: {rid}: migration failed — {exc}", file=sys.stderr)
            failed.append(rid)

    return {"migrated": migrated, "skipped": skipped, "failed": failed}


def cli_migrate(args) -> int:
    """Entry point for ``arctx migrate`` subcommand."""
    result = run_migrate_command(
        to=args.to,
        store_dir=args.store_dir,
        run_id=getattr(args, "run", None),
        all_runs=args.all,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["failed"] else 1
