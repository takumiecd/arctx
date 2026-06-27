"""CLI current-run context persistence.

Session-level resolution logic (resolve_store, resolve_run_id, resolve_user_id,
resolve_lane_id, _config_path, RunHandleProxy, ExtensionAwareStore) now
lives in arctx.session.  This module re-exports those names so existing CLI
code keeps working, and adds the argparse-Namespace helpers that belong here.
"""

from __future__ import annotations

import os

from arctx.session import (  # noqa: F401
    ExtensionAwareStore,
    RunHandleProxy,
    _config_path,
    resolve_run_id,
    resolve_store,
    resolve_user_id,
    resolve_lane_id,
)


def resolve_run_id_from_args(args) -> str:
    """Resolve a run_id from a parsed argparse namespace.

    Reads the ``--run`` flag and falls back to the env var and the
    ``<gitdir>/arctx-id`` pointer.
    """
    return resolve_run_id(getattr(args, "run", None))


def require_existing_run_from_args(args, store) -> str:
    """Resolve a run_id and verify the run actually exists on disk.

    Raises a friendly :class:`RuntimeError` (rendered by the CLI as a clean
    ``arctx: ...`` line) when the resolved run is missing. The message
    distinguishes a stale current-run pointer from an explicit bad ``--run`` so
    the user knows how to recover.
    """
    run_id = resolve_run_id_from_args(args)
    if store.run_path(run_id).exists():
        return run_id

    explicit = getattr(args, "run", None) or os.environ.get("ARCTX_RUN_ID")
    if explicit:
        raise RuntimeError(
            f"unknown run: {run_id!r}. See 'arctx list' for available runs."
        )
    # No --run / env: the id came from the <gitdir>/arctx-id current-run pointer.
    raise RuntimeError(
        f"current run {run_id!r} no longer exists (set in <gitdir>/arctx-id). "
        "Point it at an existing run with 'arctx use <run_id>', "
        "or see 'arctx list'."
    )


def resolve_user_id_from_args(args) -> str:
    """Resolve user attribution from parsed CLI args."""
    return resolve_user_id(getattr(args, "user", None))


def resolve_lane_id_from_args(args) -> str:
    """Resolve lane attribution from parsed CLI args."""
    run_id = getattr(args, "run", None)
    if run_id is None:
        try:
            run_id = resolve_run_id_from_args(args)
        except RuntimeError:
            run_id = None
    return resolve_lane_id(
        getattr(args, "lane", None) or getattr(args, "lane", None),
        run_id=run_id,
    )

