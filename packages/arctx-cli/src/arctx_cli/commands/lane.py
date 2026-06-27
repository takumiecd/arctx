"""arctx CLI ``lane`` command — the active work-context, ``git switch`` style.

A **lane** is a solo-or-collaborative, append-only unit of work. Usage mirrors
``source .venv`` / ``git switch``:

    arctx lane create geometry # create lane "geometry"; does not switch
    arctx lane switch geometry # switch to an existing lane
    arctx lane geometry        # shorthand for switch; errors if absent
    arctx lane                 # show the current lane
    arctx lane list            # list lanes in the run
    eval "$(arctx lane switch geometry --shell)"  # shell-local pin

A lane is NOT owned by one user: any actor may switch to a shared lane; per-action
attribution lives on each event. Persistent (file pointer) is the default; the
``--shell`` env override is the opt-in needed only when running explorations in
parallel from several terminals.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from arctx.core.append import AppendBatch
from arctx.core.lanes import lane_edge_node_ids, lane_edge_summaries, validate_lanes

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
)
from arctx_cli.paths import (
    arctx_lane_path,
    find_repo_root,
    read_arctx_lane,
    write_arctx_lane,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``lane`` command."""
    parser = subparsers.add_parser(
        "lane",
        help="Switch/show the active lane (solo or collaborative unit of work)",
        description=(
            "`arctx lane create NAME` creates a lane (status open). `arctx lane switch "
            "NAME` switches to an existing lane and pins it for this checkout. "
            "`arctx lane NAME` is switch shorthand and errors when NAME is absent. "
            "`arctx lane close NAME --summary TEXT` closes a lane (attaching the summary "
            "to its terminal); `arctx lane open NAME` reopens it. Writes to a closed lane "
            "are refused until it is reopened."
        ),
    )
    parser.add_argument(
        "args",
        nargs="*",
        metavar="COMMAND|NAME",
        help=(
            "No args = current lane. Commands: create NAME, switch NAME, "
            "close NAME, open NAME, adopt NAME, validate, list, show LANE, summaries LANE."
        ),
    )
    parser.add_argument("--list", action="store_true", dest="list_lanes",
                        help="List lanes in the run")
    parser.add_argument("--shell", action="store_true",
                        help="Print an export line for shell-local (parallel) use "
                             "instead of writing the persistent pointer")
    parser.add_argument(
        "--record",
        action="append",
        default=None,
        help="Record id to adopt into a lane (repeatable)",
    )
    parser.add_argument(
        "--history",
        default=None,
        metavar="NODE_ID",
        help="Adopt the history ending at NODE_ID into a lane",
    )
    parser.add_argument(
        "--reachable",
        default=None,
        metavar="NODE_ID",
        help="Adopt the active reachable subgraph from NODE_ID into a lane",
    )
    parser.add_argument(
        "--reason",
        default=None,
        help="Reason recorded on a lane adoption / close / open event",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Closing summary (Markdown), attached to the lane's terminal node (lane close)",
    )
    parser.add_argument(
        "--node",
        action="append",
        default=None,
        help="Specific leaf node id to summarise on close "
             "(repeatable; if omitted, uses all active leaf nodes of the lane)",
    )
    parser.add_argument("--user", default=None, help="Actor (created_by) when creating")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def _find_lane_by_name(handle, name: str):
    for session in handle.run_graph.lanes.values():
        if session.name == name:
            return session
    return None


def _find_lane(handle, name_or_id: str):
    lane = handle.run_graph.lanes.get(name_or_id)
    return lane if lane is not None else _find_lane_by_name(handle, name_or_id)


def _append_or_save_lane(store, handle, run_id: str, user_id: str, lane) -> None:
    if hasattr(store, "append_batch"):
        store.append_batch(
            AppendBatch(
                run_id=run_id,
                user_id=user_id or "",
                lane_id=lane.lane_id,
                lane=lane,
                records=(),
                events=(),
            )
        )
    else:
        store.save_run(handle)


def run_lane_create_command(
    *, name: str, run_id: str, user_id: str, store_dir: str | None,
) -> dict:
    """Create a lane by name. Creation does not switch the active lane."""
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    if _find_lane_by_name(handle, name) is not None:
        raise ValueError(f"lane already exists: {name!r}")

    lane = handle.ensure_lane(name=name, created_by=user_id)
    _append_or_save_lane(store, handle, run_id, user_id, lane)
    return {"lane_id": lane.lane_id, "name": name, "created": True}


def run_lane_switch_command(
    *, name: str, run_id: str, user_id: str, store_dir: str | None, shell: bool = False,
) -> dict:
    """Switch to an existing lane by name or id, returning a result dict.

    Persistent mode writes ``<gitdir>/arctx-lane``; ``shell`` mode returns an
    ``export`` line instead (terminal-scoped, for parallel work).
    """
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    lane = _find_lane(handle, name)
    if lane is None:
        raise KeyError(f"unknown lane: {name!r}; create it with `arctx lane create {name}`")

    result = {
        "lane_id": lane.lane_id,
        "name": lane.name,
        "created": False,
    }
    if shell:
        result["export"] = (
            f"export ARCTX_LANE_ID={lane.lane_id}; "
            f"export ARCTX_LANE_ID={lane.lane_id}"
        )
    else:
        repo_root = find_repo_root()
        write_arctx_lane(repo_root, lane.lane_id, run_id=run_id)
        result["arctx_lane_path"] = str(arctx_lane_path(repo_root))
    return result


def run_lane_adopt_command(
    *,
    name: str,
    run_id: str,
    user_id: str,
    store_dir: str | None,
    record_ids: list[str] | None = None,
    history_node_id: str | None = None,
    reachable_node_id: str | None = None,
    reason: str | None = None,
) -> dict:
    """Adopt existing graph records into an existing lane.

    Adoption records current lane membership as a new WorkEvent. It never
    rewrites the original event that created a record.
    """
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    lane = _find_lane(handle, name)
    if lane is None:
        raise KeyError(f"unknown lane: {name!r}; create it with `arctx lane create {name}`")

    ids, mode, target_id = _adoption_record_ids(
        handle,
        record_ids=record_ids or [],
        history_node_id=history_node_id,
        reachable_node_id=reachable_node_id,
    )
    before = graph_counts(handle)
    event = handle.adopt_lane_records(
        lane.lane_id,
        ids,
        user_id=user_id,
        mode=mode,
        target_id=target_id,
        reason=reason,
    )
    maybe_append_or_save(
        store=store,
        handle=handle,
        user_id=user_id,
        lane_id=lane.lane_id,
        before=before,
    )
    return {
        "lane_id": lane.lane_id,
        "name": lane.name,
        "adopted_record_ids": list(ids),
        "count": len(ids),
        "mode": mode,
        "event_id": event.event_id,
    }


def _adoption_record_ids(
    handle,
    *,
    record_ids: list[str],
    history_node_id: str | None,
    reachable_node_id: str | None,
) -> tuple[tuple[str, ...], str, str]:
    sources = [
        bool(record_ids),
        history_node_id is not None,
        reachable_node_id is not None,
    ]
    if sum(1 for enabled in sources if enabled) != 1:
        raise ValueError("choose exactly one of --record, --history, or --reachable")

    if record_ids:
        ids = tuple(dict.fromkeys(str(record_id) for record_id in record_ids))
        return ids, "explicit", ids[0]

    if history_node_id is not None:
        node_id = str(history_node_id)
        if node_id not in handle.run_graph.nodes:
            raise KeyError(f"unknown node_id: {node_id}")
        trace = handle.trace(node_id)
        ids = (
            trace.past_node_ids
            + (trace.current_node_id,)
            + trace.step_ids
            + trace.payload_ids
        )
        return _without_run_root(handle, ids), "history", node_id

    node_id = str(reachable_node_id)
    if node_id not in handle.run_graph.nodes:
        raise KeyError(f"unknown node_id: {node_id}")
    reachable = handle.run_graph.reachable_from(node_id)
    ids = (
        tuple(reachable["node_ids"])
        + tuple(reachable["step_ids"])
        + tuple(reachable["payload_ids"])
    )
    return _without_run_root(handle, ids), "reachable", node_id


def _without_run_root(handle, ids) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(record_id)
            for record_id in ids
            if str(record_id) != handle.root_node_id
        )
    )


def run_lane_current_command(*, run_id: str, store_dir: str | None) -> dict:
    """Resolve the active lane (env > file pointer) and return its id/name."""
    lane_id = os.environ.get("ARCTX_LANE_ID") or os.environ.get("ARCTX_LANE_ID")
    source = "env"
    if not lane_id:
        try:
            lane_id = read_arctx_lane(find_repo_root(), run_id=run_id)
            source = "pointer"
        except RuntimeError:
            lane_id = None
    if not lane_id:
        return {"lane_id": None, "name": None, "source": "default"}
    name = None
    store = resolve_store(store_dir)
    if store.run_path(run_id).exists():
        handle = store.load_run(run_id)
        lane = handle.run_graph.lanes.get(lane_id)
        name = lane.name if lane is not None else None
    return {"lane_id": lane_id, "name": name, "source": source}


def list_lanes(*, run_id: str, store_dir: str | None) -> list[dict]:
    """Return all lanes in the run under lane vocabulary."""
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    sessions = sorted(
        handle.run_graph.lanes.values(),
        key=lambda s: (s.started_at or "", s.lane_id),
    )
    return [
        {
            "lane_id": s.lane_id,
            "name": s.name,
            "created_by": s.user_id,
            "parent_lane_id": s.parent_lane_id,
            "status": s.status,
        }
        for s in sessions
    ]


def show_lane(*, run_id: str, store_dir: str | None, name_or_id: str) -> dict:
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    lane = _find_lane(handle, name_or_id)
    if lane is None:
        raise KeyError(f"unknown lane: {name_or_id}")
    return {"run_id": run_id, "lane": lane.to_dict()}


def lane_summaries(*, run_id: str, store_dir: str | None, name_or_id: str) -> dict:
    """Return summaries attached to the active terminal nodes for one lane."""
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    lane = _find_lane(handle, name_or_id)
    if lane is None:
        raise KeyError(f"unknown lane: {name_or_id}")
    edge_node_ids = lane_edge_node_ids(
        handle.run_graph,
        lane.lane_id,
        root_node_id=handle.root_node_id,
    )
    summaries = lane_edge_summaries(
        handle.run_graph,
        lane.lane_id,
        root_node_id=handle.root_node_id,
    )
    return {
        "run_id": run_id,
        "lane": lane.to_dict(),
        "edge_node_ids": list(edge_node_ids),
        "summaries": [summary.to_dict() for summary in summaries],
        "count": len(summaries),
    }


def validate_lane_run(*, run_id: str, store_dir: str | None) -> dict:
    """Return lane validation issues for a run."""
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    issues = validate_lanes(handle.run_graph, root_node_id=handle.root_node_id)
    return {
        "run_id": run_id,
        "ok": not any(issue.severity == "error" for issue in issues),
        "issues": [issue.to_dict() for issue in issues],
    }


def _lane_active_leaves(handle, lane) -> list[str]:
    """Active leaf nodes of a lane (nodes in the lane with no step extending them)."""
    from arctx.core.cuts import is_active_node
    from arctx.core.lanes import lane_membership

    membership = lane_membership(handle.run_graph)
    group = next((g for g in membership.groups if g.lane_id == lane.lane_id), None)
    if not group:
        return []
    leaves = [
        nid
        for nid in group.node_ids
        if is_active_node(handle.run_graph, nid)
        and not handle.run_graph.steps_from_node(nid)
    ]
    return list(dict.fromkeys(leaves))


def _attach_lane_summary(handle, *, lane, summary: str, node_ids, user_id: str):
    """Stamp a lane's terminal with ``summary``. Returns (summary_node, leaves).

    - 1 leaf  → attach the summary to that existing leaf (no extra node).
    - ≥2 leaves → create one convergence (join) node and summarise that.
    - 0 leaves → nothing to summarise (returns (None, [])).
    """
    from arctx.core.schema.payloads import JoinPayload, SummaryPayload

    leaves = list(dict.fromkeys(node_ids)) if node_ids else _lane_active_leaves(handle, lane)
    if not leaves:
        return None, []

    if len(leaves) == 1:
        target = leaves[0]
    else:
        join_payload = JoinPayload(payload_id=handle._next_id("pl"), target_id="")
        step = handle.add_step(
            input_node_ids=leaves,
            payload=join_payload,
            user_id=user_id,
            lane_id=lane.lane_id,
        )
        target = step.output_node_id

    handle.attach(
        target,
        SummaryPayload(payload_id=handle._next_id("pl"), target_id=target, text=summary),
        user_id=user_id,
        lane_id=lane.lane_id,
    )
    return target, leaves


def run_lane_close_command(
    *,
    name_or_id: str,
    summary: str | None,
    node_ids: list[str] | None,
    reason: str | None,
    run_id: str,
    user_id: str,
    store_dir: str | None,
) -> dict:
    """Close a lane: attach the closing ``summary`` to its terminal, then mark it closed.

    ``summary`` is **Markdown** (rendered as such in the web GUI), so put the full
    closing write-up here. It lands on the lane's single leaf when there is one (no
    redundant node), or on a fresh convergence node when several leaves must be
    merged. Once closed, writes to the lane are refused until it is reopened with
    ``lane open``.
    """
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    lane = _find_lane(handle, name_or_id)
    if lane is None:
        raise KeyError(f"unknown lane: {name_or_id!r}")
    if lane.status == "closed":
        raise ValueError(
            f"lane already closed: {name_or_id!r}; "
            f"reopen it with `arctx lane open {name_or_id}`"
        )

    summary_node, leaves = (None, [])
    if summary:
        summary_node, leaves = _attach_lane_summary(
            handle, lane=lane, summary=summary, node_ids=node_ids, user_id=user_id
        )
    event = handle.set_lane_status(
        lane.lane_id, status="closed", user_id=user_id, reason=reason
    )
    store.save_run(handle)
    return {
        "lane_id": lane.lane_id,
        "name": lane.name,
        "status": "closed",
        "summary_node": summary_node,
        "joined_nodes": leaves,
        "event_id": event.event_id,
    }


def run_lane_open_command(
    *,
    name_or_id: str,
    reason: str | None,
    run_id: str,
    user_id: str,
    store_dir: str | None,
) -> dict:
    """Reopen a closed lane so work can resume. Symmetric to ``lane close``."""
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    lane = _find_lane(handle, name_or_id)
    if lane is None:
        raise KeyError(f"unknown lane: {name_or_id!r}")
    if lane.status != "closed":
        raise ValueError(f"lane is already open: {name_or_id!r}")

    event = handle.set_lane_status(
        lane.lane_id, status="open", user_id=user_id, reason=reason
    )
    store.save_run(handle)
    return {
        "lane_id": lane.lane_id,
        "name": lane.name,
        "status": "open",
        "event_id": event.event_id,
    }


def cli_lane(args) -> int:
    """Dispatch ``lane`` commands."""
    try:
        argv = list(args.args)
        command = argv[0] if argv else None

        if args.list_lanes or command == "list":
            lanes = list_lanes(run_id=resolve_run_id_from_args(args),
                               store_dir=args.store_dir)
            print(json.dumps({"lanes": lanes}, ensure_ascii=False, indent=2))
            return 0

        if command == "validate":
            result = validate_lane_run(
                run_id=resolve_run_id_from_args(args),
                store_dir=args.store_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["ok"] else 1

        if command == "create":
            if len(argv) != 2:
                raise ValueError("usage: arctx lane create NAME")
            result = run_lane_create_command(
                name=argv[1],
                run_id=resolve_run_id_from_args(args),
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
            )
            if args.as_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(result["name"])
            return 0

        if command == "adopt":
            if len(argv) != 2:
                raise ValueError(
                    "usage: arctx lane adopt NAME "
                    "(--record ID... | --history NODE_ID | --reachable NODE_ID)"
                )
            result = run_lane_adopt_command(
                name=argv[1],
                run_id=resolve_run_id_from_args(args),
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
                record_ids=args.record,
                history_node_id=args.history,
                reachable_node_id=args.reachable,
                reason=args.reason,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if command in ("close", "join"):
            if command == "join":
                print(
                    "warning: `arctx lane join` is deprecated; use `arctx lane close` "
                    "(it closes the lane and attaches the summary to its terminal).",
                    file=sys.stderr,
                )
            if len(argv) != 2:
                raise ValueError(
                    "usage: arctx lane close NAME_OR_ID --summary TEXT [--node ID...] [--reason TEXT]"
                )
            result = run_lane_close_command(
                name_or_id=argv[1],
                summary=args.summary,
                node_ids=args.node,
                reason=args.reason,
                run_id=resolve_run_id_from_args(args),
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if command == "open":
            if len(argv) != 2:
                raise ValueError("usage: arctx lane open NAME_OR_ID [--reason TEXT]")
            result = run_lane_open_command(
                name_or_id=argv[1],
                reason=args.reason,
                run_id=resolve_run_id_from_args(args),
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if command in ("switch", "use"):
            if len(argv) != 2:
                raise ValueError(f"usage: arctx lane {command} NAME_OR_ID")
            result = run_lane_switch_command(
                name=argv[1],
                run_id=resolve_run_id_from_args(args),
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
                shell=args.shell,
            )
            if args.shell:
                print(result["export"])
            elif args.as_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(result["name"])
            return 0

        if command == "show":
            if len(argv) != 2:
                raise ValueError("usage: arctx lane show NAME_OR_ID")
            result = show_lane(
                run_id=resolve_run_id_from_args(args),
                store_dir=args.store_dir,
                name_or_id=argv[1],
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if command in ("summary", "summaries"):
            if len(argv) != 2:
                raise ValueError(f"usage: arctx lane {command} NAME_OR_ID")
            result = lane_summaries(
                run_id=resolve_run_id_from_args(args),
                store_dir=args.store_dir,
                name_or_id=argv[1],
            )
            if args.as_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            elif not result["summaries"]:
                print("(none)")
            else:
                for summary in result["summaries"]:
                    print(
                        f"{summary['target_id']} {summary['payload_id']} "
                        f"{summary['text']}"
                    )
            return 0

        if command is not None:
            if len(argv) != 1:
                raise ValueError("usage: arctx lane [NAME_OR_ID]")
            result = run_lane_switch_command(
                name=command,
                run_id=resolve_run_id_from_args(args),
                user_id=resolve_user_id_from_args(args),
                store_dir=args.store_dir,
                shell=args.shell,
            )
            if args.shell:
                print(result["export"])
            elif args.as_json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(result["name"] or result["lane_id"])
            return 0

        # bare `arctx lane` → show current
        result = run_lane_current_command(
            run_id=resolve_run_id_from_args(args), store_dir=args.store_dir
        )
        if args.as_json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(result["name"] or result["lane_id"] or "(default)")
        return 0
    except (KeyError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
