"""Environment/config-level session resolution for STAG.

These helpers resolve store backends, run IDs, user IDs, and work-session IDs
from environment variables and the STAG config file.  They carry no CLI /
argparse dependency, so stag-tui and other non-CLI consumers can import them
directly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from stag_api.paths import find_repo_root, read_stag_id, resolve_stag_home, resolve_store_dir


class ExtensionAwareStore:
    """Store adapter that attaches extension namespaces after loading a run."""

    def __init__(self, store):
        self._store = store

    def __getattr__(self, name: str):
        return getattr(self._store, name)

    def load_run(self, run_id: str):
        from stag_api.ext import load_extension
        from stag_api.ext.enabled import load_enabled

        run_path = self._store.run_path(run_id)
        for item in load_enabled(run_path):
            load_extension(item.name).register_schema()
        handle = self._store.load_run(run_id)
        from stag_api.ext import attach_enabled_extensions

        attach_enabled_extensions(handle, run_path)
        return handle


def _config_path() -> Path:
    """Return ``<STAG_HOME>/config.json``."""
    return resolve_stag_home() / "config.json"


def resolve_run_id(run_id: str | None) -> str:
    """Resolve a run identifier using the canonical fallback chain.

    1. Explicit *run_id* if provided.
    2. ``STAG_RUN_ID`` environment variable.
    3. Active-run pointer at ``<gitdir>/stag-id`` in the nearest git repo.

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
    # Walk up from cwd to find the gitdir, then read <gitdir>/stag-id.
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


def resolve_user_id(user_id: str | None) -> str:
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


def resolve_work_session_id(work_session_id: str | None) -> str:
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
        from stag_api.storage.jsonl import JsonlRunStore  # noqa: PLC0415
        return ExtensionAwareStore(JsonlRunStore(store_dir))
    if backend == "sqlite":
        from stag_api.storage.sqlite import SqliteRunStore  # noqa: PLC0415
        return ExtensionAwareStore(SqliteRunStore(store_dir))
    raise RuntimeError(f"unknown store backend: {backend!r}. Expected 'jsonl' or 'sqlite'.")


# Keep RunHandleProxy here for completeness — it wraps a RunHandle with lazy
# session-level context (user_id, work_session_id) resolved at call time.
class RunHandleProxy:
    """Thin proxy that binds user/work-session defaults to a RunHandle."""

    def __init__(self, handle, *, user_id: str, work_session_id: str) -> None:
        self._handle = handle
        self._user_id = user_id
        self._work_session_id = work_session_id

    def __getattr__(self, name: str):
        return getattr(self._handle, name)
