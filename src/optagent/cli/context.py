"""CLI current-run context persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path


_CURRENT_FILENAME = "current.json"


def current_path(store_dir: str) -> Path:
    """Return the path to the current-run marker file."""
    return Path(store_dir).parent / _CURRENT_FILENAME


def save_current_run(run_id: str, store_dir: str) -> Path:
    """Persist *run_id* as the current run for the store directory."""
    path = current_path(store_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"run_id": run_id, "store_dir": store_dir}, indent=2),
        encoding="utf-8",
    )
    return path


def load_current_run(store_dir: str) -> str:
    """Load the current run_id from the marker file.

    Raises
    ------
    RuntimeError
        If no current run is set.
    """
    path = current_path(store_dir)
    if not path.exists():
        raise RuntimeError("no current run set. Use 'optagent use <run_id>'")
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["run_id"]


def resolve_run_id(
    run_id: str | None,
    store_dir: str,
) -> str:
    """Resolve a run identifier using the canonical fallback chain.

    1. Explicit *run_id* if provided.
    2. ``OPTAGENT_RUN_ID`` environment variable.
    3. ``.optagent/current.json`` marker file.

    Raises
    ------
    RuntimeError
        If no run_id can be resolved.
    """
    if run_id:
        return run_id
    env = os.environ.get("OPTAGENT_RUN_ID")
    if env:
        return env
    return load_current_run(store_dir)


def resolve_run_id_from_args(args) -> str:
    """Resolve a run_id from a parsed argparse namespace.

    Reads the ``--run`` flag and falls back to the env var and
    current.json marker.
    """
    return resolve_run_id(getattr(args, "run", None), args.store_dir)
