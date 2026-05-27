"""CLI current-run context persistence.

Session-level resolution logic (resolve_store, resolve_run_id, resolve_user_id,
resolve_work_session_id, _config_path, RunHandleProxy, ExtensionAwareStore) now
lives in arctx.session.  This module re-exports those names so existing CLI
code keeps working, and adds the argparse-Namespace helpers that belong here.
"""

from __future__ import annotations

from arctx.session import (  # noqa: F401
    ExtensionAwareStore,
    RunHandleProxy,
    _config_path,
    resolve_run_id,
    resolve_store,
    resolve_user_id,
    resolve_work_session_id,
)


def resolve_run_id_from_args(args) -> str:
    """Resolve a run_id from a parsed argparse namespace.

    Reads the ``--run`` flag and falls back to the env var and the
    ``<gitdir>/arctx-id`` pointer.
    """
    return resolve_run_id(getattr(args, "run", None))


def resolve_user_id_from_args(args) -> str:
    """Resolve user attribution from parsed CLI args."""
    return resolve_user_id(getattr(args, "user", None))


def resolve_work_session_id_from_args(args) -> str:
    """Resolve work-session attribution from parsed CLI args."""
    return resolve_work_session_id(getattr(args, "work_session", None))
