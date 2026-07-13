"""Automatic lane-consistency check run after write commands succeed.

Write commands (``add``, ``attach``, ``cut``, ``uncut``, ``reparent``, ``lane
create``/``close``/``open``) already commit their change before this runs, so
:func:`warn_if_invalid` is read-only and never blocks or rolls back a write —
it only reports. It reuses :func:`arctx.core.lanes.validate_lanes`, the same
check ``arctx lane validate`` runs on demand.

Controlled by the ``ARCTX_VALIDATE`` environment variable:

* unset (default): warn on stderr only; the command's exit code is untouched.
* ``"strict"``: also return the issue count so the caller can fail the
  command's exit code.
* ``"off"``: skip the check entirely.
"""

from __future__ import annotations

import os
import sys


def warn_if_invalid(handle_or_run_id, store_dir: str | None, *, command_name: str) -> int:
    """Warn on stderr about lane consistency issues left by a write command.

    ``handle_or_run_id`` accepts either an already-loaded ``RunHandle`` (no
    extra store round-trip — the caller's in-memory handle already reflects
    the write) or a run_id string (loaded fresh from ``store_dir``).

    Returns ``0`` when there is nothing to report, when the check is skipped
    (``ARCTX_VALIDATE=off``), or when issues were found but
    ``ARCTX_VALIDATE`` is not ``"strict"``. Returns the issue count (a
    truthy, non-zero value) when ``ARCTX_VALIDATE=strict`` and issues exist,
    so callers can use it directly as a process exit code.
    """
    mode = os.environ.get("ARCTX_VALIDATE")
    if mode == "off":
        return 0

    try:
        from arctx.core.lanes import validate_lanes  # noqa: PLC0415

        handle = handle_or_run_id
        if isinstance(handle_or_run_id, str):
            from arctx_cli.context import resolve_store  # noqa: PLC0415

            store = resolve_store(store_dir)
            handle = store.load_run(handle_or_run_id)
        issues = validate_lanes(handle.run_graph, root_node_id=handle.root_node_id)
    except Exception as exc:  # noqa: BLE001 — the write already succeeded; never block on this
        print(f"arctx: warning: post-write validation failed: {exc}", file=sys.stderr)
        return 0

    if not issues:
        return 0

    run_id = handle.run_id
    print(
        f"arctx: warning: run {run_id!r} has {len(issues)} consistency "
        f"issue(s) after {command_name}:",
        file=sys.stderr,
    )
    for issue in issues:
        print(f"  - {issue.code}: {issue.message}", file=sys.stderr)
    print(
        "hint: run 'arctx lane validate' for details; "
        "fix with 'arctx lane adopt <LANE>' (claim nodes into a lane) or "
        "'arctx cut <ID>' (retire them); see 'arctx guide' for the data model.",
        file=sys.stderr,
    )

    return len(issues) if mode == "strict" else 0
