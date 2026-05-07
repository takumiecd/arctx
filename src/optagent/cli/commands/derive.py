"""optagent CLI derive command."""

from __future__ import annotations

import argparse
import json

from optagent.cli.context import resolve_run_id_from_args
from optagent.storage.jsonl import JsonlRunStore


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``derive`` subcommand parser."""
    parser = subparsers.add_parser(
        "derive", help="Attach a derived record to an observed transition"
    )
    parser.add_argument("transition_id", help="Observed transition identifier")
    parser.add_argument("--run", default=None, help="Run identifier (optional if current run is set)")
    parser.add_argument(
        "--type",
        dest="derived_type",
        default="finding",
        help="Derived record type (default: finding)",
    )
    parser.add_argument(
        "--id",
        dest="derived_id",
        default=None,
        help="Explicit derived record ID (default: auto-generated)",
    )
    parser.add_argument(
        "--text",
        default=None,
        help="Short text content (stored in payload as 'text')",
    )
    parser.add_argument(
        "--confidence",
        type=float,
        default=None,
        help="Confidence score in [0, 1]",
    )
    parser.add_argument(
        "--store-dir",
        default=".optagent/runs",
        help="Directory where runs are stored (default: .optagent/runs)",
    )
    return parser


def run_derive_command(
    *,
    run_id: str,
    transition_id: str,
    derived_type: str,
    payload: dict[str, str | float | int | bool | None],
    derived_id: str | None,
    generator: str,
    confidence: float | None,
    store_dir: str,
) -> dict:
    """Attach a derived record to an observed transition.

    Parameters
    ----------
    run_id:
        Identifier of the run.
    transition_id:
        Identifier of the observed transition.
    derived_type:
        Type of derived record (e.g. ``"finding"``, ``"evidence"``).
    payload:
        Key-value content for the derived record.
    derived_id:
        Optional explicit record ID.
    generator:
        Label for the source that created the record.
    confidence:
        Optional confidence score.
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    dict with ``record`` key containing the created derived record dict.

    Raises
    ------
    KeyError
        If the run_id or transition_id does not exist.
    """
    store = JsonlRunStore(store_dir)
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    record = handle.derive(
        transition_id=transition_id,
        derived_type=derived_type,
        payload=payload,
        derived_id=derived_id,
        generator=generator,
        confidence=confidence,
    )

    store.save_run(handle)
    return {"record": record.to_dict()}


def cli_derive(args) -> int:
    """Entry point for ``optagent derive`` subcommand.

    Prints the created derived record as JSON to stdout.
    """
    payload: dict[str, str | float | int | bool | None] = {}
    if args.text is not None:
        payload["text"] = args.text

    result = run_derive_command(
        run_id=resolve_run_id_from_args(args),
        transition_id=args.transition_id,
        derived_type=args.derived_type,
        payload=payload,
        derived_id=args.derived_id,
        generator="cli",
        confidence=args.confidence,
        store_dir=args.store_dir,
    )
    print(json.dumps(result["record"], ensure_ascii=False, indent=2))
    return 0
