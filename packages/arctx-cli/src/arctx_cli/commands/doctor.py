"""arctx CLI doctor command — check a run, and set aside what cannot be read."""

from __future__ import annotations

import argparse
import json

from arctx.storage.doctor import diagnose, repair

from arctx_cli.context import resolve_run_id_from_args, resolve_store


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "doctor",
        help="Check a run's files and report anything unreadable",
        description=(
            "Every reader parses every line of a run, so one unparsable line "
            "stops `dump`, `show`, `explore` and `topics` alike. This says "
            "exactly which lines those are. `--repair` moves them to "
            "<file>.broken and rewrites the file without them, so the rest of "
            "the run loads again; nothing is deleted."
        ),
    )
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Move unreadable lines to <file>.broken so the run loads again",
    )
    parser.add_argument("--json", dest="as_json", action="store_true")
    return parser


def cli_doctor(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)

    moved: dict[str, int] = {}
    if args.repair:
        diagnosis, moved = repair(store, run_id)
        # Re-read after the repair so the report describes the run as it now is.
        diagnosis = diagnose(store, run_id)
    else:
        diagnosis = diagnose(store, run_id)

    # Files parsing is not the same as the graph making sense. Saying "run is
    # healthy" while a node has two active producers is exactly the silent
    # answer doctor exists to prevent, so check the invariants too when the run
    # loads at all.
    consistency = _consistency_issues(store, run_id) if not diagnosis.broken else []
    ok = diagnosis.healthy and not consistency

    if args.as_json:
        payload = diagnosis.to_dict()
        payload["repaired"] = moved
        # `healthy` is the whole answer callers key on, so it has to mean the
        # same thing as the exit code. It used to describe files only, and so
        # said true while doctor exited 1 over a consistency issue.
        payload["healthy"] = ok
        payload["consistency"] = [
            {"code": issue.code, "severity": issue.severity, "message": issue.message,
             "record_id": issue.record_id}
            for issue in consistency
        ]
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    _print_report(diagnosis, moved, repaired=args.repair, consistency=consistency)
    return 0 if ok else 1


# Codes that mean a read of this run would answer untruthfully — not the wider
# lane-hygiene set, which legitimate runs violate by design.
_DOCTOR_CODES = frozenset({"multiple_active_producers"})


def _consistency_issues(store, run_id: str):
    """Graph states where the run would report something untrue.

    Deliberately narrow. Reporting every `validate_lanes` error here was wrong:
    most of those codes are lane-bookkeeping rules that legitimate runs break
    by design — a run written through the pure core API has no lane provenance
    at all, and a long-lived run accumulates lanes with several root candidates.
    Both are fine, neither can be cleared (history is append-only), and calling
    them out made `arctx doctor` exit 1 forever on the maintainer's real run.

    What belongs here is the state where the *graph itself* lies: a node with
    two active producing steps makes `trace` and `export` report a merged
    lineage that never happened. `arctx lane validate` is still the place to
    see the full bookkeeping picture.

    Read-only and never raises: doctor's job is to report, and a run that
    cannot load has already been reported as broken lines.
    """
    try:
        from arctx.core.lanes import validate_lanes  # noqa: PLC0415

        handle = store.load_run(run_id)
        return [
            issue
            for issue in validate_lanes(
                handle.run_graph, root_node_id=handle.root_node_id
            )
            if issue.code in _DOCTOR_CODES
        ]
    except Exception:  # noqa: BLE001
        return []


def _print_report(diagnosis, moved: dict[str, int], *, repaired: bool, consistency=()) -> None:
    print(f"run {diagnosis.run_id}  ({diagnosis.run_path})")

    for report in diagnosis.files:
        if not report.exists:
            continue
        mark = "!" if report.broken else " "
        rows = f"{report.rows} rows" if report.name.endswith(".jsonl") else "ok"
        print(f"  {mark} {report.name:<22} {rows}")

    if diagnosis.pending_journal:
        print("  ! an interrupted write is still journalled; the next write replays it")

    if moved:
        for name, count in sorted(moved.items()):
            print(f"  moved {count} unreadable line(s) out of {name} -> {name}.broken")

    broken = diagnosis.broken
    if broken:
        print()
        print(f"{len(broken)} unreadable line(s):")
        for line in broken:
            print(f"  {line.file} line {line.line_number}: {line.reason}")
            print(f"    {line.excerpt}")
        if not repaired:
            print()
            print("  `arctx doctor --repair` moves these to <file>.broken and")
            print("  rewrites the file without them. Nothing is deleted.")
        return

    if diagnosis.load_error:
        print()
        print(f"every line parses, but the run does not load: {diagnosis.load_error}")
        return

    if consistency:
        print()
        print(f"{len(consistency)} consistency issue(s) — every line parses, but:")
        for issue in consistency:
            print(f"  {issue.code}: {issue.message}")
        print()
        print("  `arctx lane validate` shows the same list with lane context.")
        return

    print()
    if repaired:
        print("run loads.")
    else:
        print("run is healthy.")
