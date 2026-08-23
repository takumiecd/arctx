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

    if args.as_json:
        payload = diagnosis.to_dict()
        payload["repaired"] = moved
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if diagnosis.healthy else 1

    _print_report(diagnosis, moved, repaired=args.repair)
    return 0 if diagnosis.healthy else 1


def _print_report(diagnosis, moved: dict[str, int], *, repaired: bool) -> None:
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

    print()
    if repaired:
        print("run loads.")
    else:
        print("run is healthy.")
