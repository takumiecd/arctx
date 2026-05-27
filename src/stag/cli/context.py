"""CLI current-run context persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path

from stag.cli.paths import find_repo_root, read_stag_id, resolve_stag_home


class ExtensionAwareStore:
    """Store adapter that attaches extension namespaces after loading a run."""

    def __init__(self, store):
        self._store = store

    def __getattr__(self, name: str):
        return getattr(self._store, name)

    def load_run(self, run_id: str):
        handle = self._store.load_run(run_id)
        from stag.ext import attach_enabled_extensions, attach_standard_extensions

        attach_standard_extensions(handle)
        attach_enabled_extensions(handle, self._store.run_path(run_id))
        return handle


def resolve_run_id(
    run_id: str | None,
    store_dir: str,
) -> str:
    """Resolve a run identifier using the canonical fallback chain.

    1. Explicit *run_id* if provided.
    2. ``STAG_RUN_ID`` environment variable.
    3. ``.stag-id`` file in the nearest git repo root.

    Raises
    ------
    RuntimeError
        If no run_id can be resolved.
    """
    if run_id:
        return run_id
    env = os.environ.get("STAG_RUN_ID")
    if env:
        return env
    # Walk up from cwd to find .stag-id
    try:
        repo_root = find_repo_root()
        stag_id = read_stag_id(repo_root)
        if stag_id:
            return stag_id
    except RuntimeError:
        pass
    raise RuntimeError(
        "no current run set. "
        "Run 'stag init' to create a run, or set STAG_RUN_ID, "
        "or pass --run."
    )


def resolve_run_id_from_args(args) -> str:
    """Resolve a run_id from a parsed argparse namespace.

    Reads the ``--run`` flag and falls back to the env var and
    ``.stag-id`` file.
    """
    return resolve_run_id(getattr(args, "run", None), args.store_dir)


def _config_path() -> Path:
    """Return ``<STAG_HOME>/config.json``."""
    return resolve_stag_home() / "config.json"


def resolve_user_id(user_id: str | None, store_dir: str) -> str:
    """Resolve user attribution for mutating commands."""
    if user_id:
        return user_id
    env = os.environ.get("STAG_USER_ID")
    if env:
        return env
    config_path = _config_path()
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        configured = data.get("user", {}).get("id")
        if configured:
            return str(configured)
    return "user"


def resolve_user_id_from_args(args) -> str:
    """Resolve user attribution from parsed CLI args."""
    return resolve_user_id(getattr(args, "user", None), args.store_dir)


def resolve_work_session_id(work_session_id: str | None, store_dir: str) -> str:
    """Resolve work-session attribution for mutating commands."""
    if work_session_id:
        return work_session_id
    env = os.environ.get("STAG_WORK_SESSION_ID")
    if env:
        return env
    config_path = _config_path()
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        configured = data.get("work_session", {}).get("id")
        if configured:
            return str(configured)
    return "default"


def resolve_work_session_id_from_args(args) -> str:
    """Resolve work-session attribution from parsed CLI args."""
    return resolve_work_session_id(getattr(args, "work_session", None), args.store_dir)


def resolve_store(store_dir: str | None):
    """Pick a RunStore implementation.

    Resolution chain:
    1. STAG_STORE env var ("jsonl" | "sqlite")
    2. <STAG_HOME>/config.json ``storage.backend``
    3. default: "jsonl"

    If *store_dir* is None, ``<STAG_HOME>/runs`` is used.

    Raises
    ------
    RuntimeError
        If the resolved backend name is not "jsonl" or "sqlite".
    """
    if store_dir is None:
        from stag.cli.paths import resolve_store_dir  # noqa: PLC0415
        store_dir = resolve_store_dir()

    backend: str | None = os.environ.get("STAG_STORE")
    if not backend:
        config_path = _config_path()
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            backend = data.get("storage", {}).get("backend")
    if not backend:
        backend = "jsonl"

    if backend == "jsonl":
        from stag.storage.jsonl import JsonlRunStore  # noqa: PLC0415
        return ExtensionAwareStore(JsonlRunStore(store_dir))
    if backend == "sqlite":
        from stag.storage.sqlite import SqliteRunStore  # noqa: PLC0415
        return ExtensionAwareStore(SqliteRunStore(store_dir))
    raise RuntimeError(f"unknown store backend: {backend!r}. Expected 'jsonl' or 'sqlite'.")
