"""Environment/config-level session resolution for ARCTX.

These helpers resolve store backends, run IDs, user IDs, and lane IDs
from environment variables and the ARCTX config file.  They carry no CLI /
argparse dependency, so arctx-tui and other non-CLI consumers can import them
directly.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from arctx.paths import (
    find_repo_root,
    read_arctx_id,
    read_arctx_lane,
    resolve_arctx_home,
    resolve_store_dir,
)


class ExtensionAwareStore:
    """Store adapter that attaches extension namespaces after loading a run."""

    def __init__(self, store):
        self._store = store

    def __getattr__(self, name: str):
        return getattr(self._store, name)

    def load_run(self, run_id: str):
        from arctx.ext import load_extension
        from arctx.ext.enabled import load_enabled

        run_path = self._store.run_path(run_id)
        for item in load_enabled(run_path):
            try:
                load_extension(item.name).register_schema()
            except KeyError:
                # Unknown extension name (e.g. "asset", now a core payload, or a
                # third-party ext not installed). Skip rather than crash on load.
                continue
        handle = self._store.load_run(run_id)
        from arctx.ext import attach_enabled_extensions

        attach_enabled_extensions(handle, run_path)
        return handle


def _config_path() -> Path:
    """Return ``<ARCTX_HOME>/config.json``."""
    return resolve_arctx_home() / "config.json"


def resolve_run_id(run_id: str | None) -> str:
    """Resolve a run identifier using the canonical fallback chain.

    1. Explicit *run_id* if provided.
    2. ``ARCTX_RUN_ID`` environment variable.
    3. Active-run pointer at ``<gitdir>/arctx-id`` in the nearest git repo.

    Raises
    ------
    RuntimeError
        If no run_id can be resolved.
    """
    if run_id:
        return run_id
    env = os.environ.get("ARCTX_RUN_ID")
    if env:
        return env
    # Walk up from cwd to find the gitdir, then read <gitdir>/arctx-id.
    try:
        repo_root = find_repo_root()
        arctx_id = read_arctx_id(repo_root)
        if arctx_id:
            return arctx_id
    except RuntimeError:
        pass
    raise RuntimeError(
        "no current run set. "
        "Run 'arctx init' to create a run, or set ARCTX_RUN_ID, "
        "or pass --run."
    )


def resolve_user_id(user_id: str | None) -> str:
    """Resolve user attribution for mutating commands."""
    if user_id:
        return user_id
    env = os.environ.get("ARCTX_USER_ID")
    if env:
        return env
    config_path = _config_path()
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        configured = data.get("user", {}).get("id")
        if configured:
            return str(configured)
    return "user"


def resolve_lane_id(
    lane_id: str | None,
    *,
    run_id: str | None = None,
) -> str:
    """Resolve the active lane for mutating commands.

    Chain (mirrors :func:`resolve_run_id`):
    1. Explicit *lane_id*.
    2. ``ARCTX_LANE_ID`` env var, then legacy ``ARCTX_LANE_ID``.
    3. Active-lane pointer for *run_id* at ``<gitdir>/arctx-lanes.json`` when a
       run is known, falling back to the legacy ``<gitdir>/arctx-lane`` pointer.
    4. ``<ARCTX_HOME>/config.json`` ``lane.id``.
    5. ``"default"``.
    """
    if lane_id:
        return lane_id
    env = os.environ.get("ARCTX_LANE_ID")
    if env:
        return env
    try:
        repo_root = find_repo_root()
        lane = read_arctx_lane(repo_root, run_id=run_id)
        if lane:
            return lane
    except RuntimeError:
        pass
    config_path = _config_path()
    if config_path.exists():
        data = json.loads(config_path.read_text(encoding="utf-8"))
        configured = data.get("lane", {}).get("id")
        if configured:
            return str(configured)
    return "default"




def resolve_store(store_dir: str | None):
    """Pick a RunStore implementation.

    Resolution chain:
    1. ARCTX_STORE env var ("jsonl" | "sqlite")
    2. <ARCTX_HOME>/config.json ``storage.backend``
    3. default: "jsonl"

    If *store_dir* is None, ``<ARCTX_HOME>/runs`` is used.

    Raises
    ------
    RuntimeError
        If the resolved backend name is not "jsonl" or "sqlite".
    """
    if store_dir is None:
        store_dir = resolve_store_dir()

    backend: str | None = os.environ.get("ARCTX_STORE")
    if not backend:
        config_path = _config_path()
        if config_path.exists():
            data = json.loads(config_path.read_text(encoding="utf-8"))
            backend = data.get("storage", {}).get("backend")
    if not backend:
        backend = "jsonl"

    if backend == "jsonl":
        from arctx.storage.jsonl import JsonlRunStore  # noqa: PLC0415
        return ExtensionAwareStore(JsonlRunStore(store_dir))
    if backend == "sqlite":
        from arctx.storage.sqlite import SqliteRunStore  # noqa: PLC0415
        return ExtensionAwareStore(SqliteRunStore(store_dir))
    raise RuntimeError(f"unknown store backend: {backend!r}. Expected 'jsonl' or 'sqlite'.")


# Keep RunHandleProxy here for completeness — it wraps a RunHandle with lazy
# session-level context (user_id, lane_id) resolved at call time.
class RunHandleProxy:
    """Thin proxy that binds user/lane defaults to a RunHandle."""

    def __init__(self, handle, *, user_id: str, lane_id: str) -> None:
        self._handle = handle
        self._user_id = user_id
        self._lane_id = lane_id

    def __getattr__(self, name: str):
        return getattr(self._handle, name)
