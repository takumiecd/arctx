"""``arctx topic`` / ``arctx topics`` — flat, name-keyed bundles of meaning.

A topic bundles records the way a lane bundles work and a trial table bundles
numbers: any node or step can carry a topic name, connectivity is never
required, and every view is derived at read time (see arctx.core.topics).

- ``topic tag NAME ID [ID ...]`` marks records as belonging to the topic.
- ``topic summarize NAME --summary TEXT`` writes the topic's current
  statement ("a strong tag"); the latest one wins, history stays.
- ``topic NAME`` / ``topic show NAME`` prints the statement plus the tagged
  records grouped into islands — two or more islands is the "these regions
  are about the same thing but not yet joined" signal.
- ``topics`` lists every topic one line each.
"""

from __future__ import annotations

import argparse
import json
import sys

from arctx.core import topics as core_topics

from arctx_cli.commands.add import _default_input_node_ids
from arctx_cli.commands.attach import run_attach_command
from arctx_cli.context import (
    resolve_lane_id_from_args,
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
)


def add_topic_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "topic",
        help="Tag records into a named topic; keep its current statement",
    )
    parser.add_argument(
        "args",
        nargs="*",
        metavar="COMMAND|NAME",
        help=(
            "tag NAME ID [ID ...] · summarize NAME · show NAME · log NAME · list. "
            "`arctx topic NAME` is show shorthand; `log` walks the statement "
            "history (latest is the current belief, nothing is deleted)."
        ),
    )
    parser.add_argument("--note", default=None, help="tag: short note on the mark")
    parser.add_argument("--summary", default=None, help="summarize: the statement text")
    parser.add_argument(
        "--source",
        action="append",
        default=None,
        metavar="RECORD_ID",
        help="summarize: evidence record (repeatable, existence-checked)",
    )
    parser.add_argument(
        "--on",
        default=None,
        metavar="NODE_ID",
        help="summarize: node to attach to (default: current lane frontier)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    parser.add_argument("--user", default=None)
    parser.add_argument("--lane", default=None)
    parser.add_argument("--force", action="store_true")
    return parser


def add_topics_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("topics", help="List topics (name, records, islands, statement)")
    parser.add_argument("--json", action="store_true", dest="as_json")
    parser.add_argument("--run", default=None)
    parser.add_argument("--store-dir", default=None)
    return parser


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def run_topic_tag_command(
    *,
    run_id: str,
    name: str,
    record_ids: list[str],
    note: str | None,
    store_dir: str | None,
    user_id: str | None = None,
    lane_id: str | None = None,
    fallback_lane_id: str | None = None,
    force: bool = False,
) -> dict:
    if not record_ids:
        raise ValueError("topic tag needs at least one record id")

    # A tag annotates the record where it lives, so by default the tag event
    # is attributed to *that record's own lane* — tagging while browsing never
    # requires switching lanes or inventing a bookkeeping lane. An explicit
    # --lane still wins, and a record in a closed lane falls back to the
    # caller's lane (writes to closed lanes stay refused).
    from arctx.core.lanes import lane_membership

    record_lane: dict[str, str | None] = {}
    if lane_id is None:
        store = resolve_store(store_dir)
        if not store.run_path(run_id).exists():
            raise KeyError(f"unknown run_id: {run_id}")
        handle = store.load_run(run_id)
        membership = lane_membership(handle.run_graph, root_node_id=handle.root_node_id)
        for record_id in record_ids:
            owner = membership.node_to_lane.get(record_id) or membership.step_to_lane.get(
                record_id
            )
            owner_lane = handle.run_graph.lanes.get(owner) if owner else None
            record_lane[record_id] = (
                owner if owner_lane is not None and owner_lane.status == "open" else None
            )

    results = []
    for record_id in record_ids:
        content: dict = {"topic": name}
        if note:
            content["note"] = note
        result = run_attach_command(
            run_id=run_id,
            target_id=record_id,
            payload_kind=core_topics.TAG_TYPE,
            payload_type=None,
            field_data={},
            json_data=content,
            store_dir=store_dir,
            user_id=user_id,
            lane_id=lane_id or record_lane.get(record_id) or fallback_lane_id,
            force=force,
        )
        results.append(result)
    return {"topic": name, "tagged": record_ids, "payloads": results}


def run_topic_summarize_command(
    *,
    run_id: str,
    name: str,
    text: str,
    sources: list[str] | None,
    on_node: str | None,
    store_dir: str | None,
    user_id: str | None = None,
    lane_id: str | None = None,
    force: bool = False,
) -> dict:
    if not text or not text.strip():
        raise ValueError("topic summarize needs --summary TEXT")
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    graph = handle.run_graph
    for source in sources or []:
        if source not in graph.nodes and source not in graph.steps:
            raise KeyError(f"unknown --source record: {source}")
    target = on_node or _default_input_node_ids(handle, lane_id or "default")[0]
    content: dict = {"topic": name, "text": text.strip()}
    if sources:
        content["sources"] = list(sources)
    return run_attach_command(
        run_id=run_id,
        target_id=target,
        payload_kind=core_topics.SUMMARY_TYPE,
        payload_type=None,
        field_data={},
        json_data=content,
        store_dir=store_dir,
        user_id=user_id,
        lane_id=lane_id,
        force=force,
    )


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def _view_dict(view: core_topics.TopicView) -> dict:
    return {
        "name": view.name,
        "summary": (
            {
                "text": view.summary.text,
                "sources": list(view.summary.sources),
                "payload_id": view.summary.payload_id,
                "target_id": view.summary.target_id,
            }
            if view.summary
            else None
        ),
        "islands": [list(island) for island in view.islands],
        "inactive": list(view.inactive),
        "records": [
            {
                "record_id": r.record_id,
                "kind": r.kind,
                "active": r.active,
                "note": r.note,
            }
            for r in view.records
        ],
    }


def _print_view(view: core_topics.TopicView, history_count: int = 0) -> None:
    print(f"topic: {view.name}")
    if view.summary:
        print(f"  summary: {view.summary.text}")
        if view.summary.sources:
            print(f"  sources: {', '.join(view.summary.sources)}")
        if history_count > 1:
            print(
                f"  history: {history_count} statements — "
                f"arctx topic log {view.name}"
            )
    else:
        print("  summary: (none yet — arctx topic summarize NAME --summary ...)")
    active_count = sum(len(island) for island in view.islands)
    island_word = "island" if len(view.islands) == 1 else "islands"
    print(f"  records: {active_count} active in {len(view.islands)} {island_word}"
          + (f", {len(view.inactive)} cut" if view.inactive else ""))
    notes = {r.record_id: r.note for r in view.records}
    for index, island in enumerate(view.islands, 1):
        print(f"  island {index}:")
        for record_id in island:
            note = notes.get(record_id)
            print(f"    {record_id}" + (f"  — {note}" if note else ""))
    for record_id in view.inactive:
        print(f"  ✂ {record_id}")
    if len(view.islands) > 1:
        example = " --from ".join(island[0] for island in view.islands[:2])
        print(f"  hint: unjoined regions share this topic — e.g. arctx add --from {example} ...")


def cli_topic(args) -> int:
    try:
        run_id = resolve_run_id_from_args(args)
        positional = list(args.args)
        command = positional[0] if positional else "list"
        if command == "tag":
            if len(positional) < 3:
                raise ValueError("usage: arctx topic tag NAME RECORD_ID [RECORD_ID ...]")
            result = run_topic_tag_command(
                run_id=run_id,
                name=positional[1],
                record_ids=positional[2:],
                note=args.note,
                store_dir=args.store_dir,
                user_id=resolve_user_id_from_args(args),
                # Explicit --lane wins; otherwise each tag is attributed to
                # the tagged record's own (open) lane, and only records whose
                # lane is closed fall back to the ambient current lane.
                lane_id=args.lane,
                fallback_lane_id=resolve_lane_id_from_args(args),
                force=args.force,
            )
            print(f"tagged {len(result['tagged'])} records into topic \"{result['topic']}\"")
            return 0
        if command == "summarize":
            if len(positional) < 2:
                raise ValueError("usage: arctx topic summarize NAME --summary TEXT")
            run_topic_summarize_command(
                run_id=run_id,
                name=positional[1],
                text=args.summary or "",
                sources=args.source,
                on_node=args.on,
                store_dir=args.store_dir,
                user_id=resolve_user_id_from_args(args),
                lane_id=resolve_lane_id_from_args(args),
                force=args.force,
            )
            print(f"topic \"{positional[1]}\" summarized")
            return 0
        if command == "log":
            if len(positional) < 2:
                raise ValueError("usage: arctx topic log NAME")
            graph = resolve_store(args.store_dir).load_run(run_id).run_graph
            history = core_topics.topic_summary_history(graph, positional[1])
            if args.as_json:
                print(json.dumps({
                    "topic": positional[1],
                    "history": [
                        {
                            "text": entry.text,
                            "sources": list(entry.sources),
                            "created_at": entry.created_at,
                            "user_id": entry.user_id,
                            "payload_id": entry.payload_id,
                            "current": index == len(history) - 1,
                        }
                        for index, entry in enumerate(history)
                    ],
                }, ensure_ascii=False, indent=2))
                return 0
            if not history:
                print(f'topic "{positional[1]}" has no statements yet')
                return 0
            for index, entry in enumerate(reversed(history)):
                marker = "● current" if index == 0 else "○"
                stamp = (entry.created_at or "")[:16].replace("T", " ")
                who = f" by {entry.user_id}" if entry.user_id else ""
                print(f"{marker}  {stamp}{who}")
                print(f"   {entry.text}")
                if entry.sources:
                    print(f"   sources: {', '.join(entry.sources)}")
            return 0
        name = positional[1] if command in ("show",) and len(positional) > 1 else (
            None if command in ("list", "show") else command
        )
        graph = resolve_store(args.store_dir).load_run(run_id).run_graph
        if name is None:
            views = core_topics.list_topics(graph)
            if args.as_json:
                print(json.dumps({"topics": [_view_dict(v) for v in views]}, ensure_ascii=False, indent=2))
            else:
                _print_overview(views)
            return 0
        if name not in core_topics.topic_names(graph):
            known = ", ".join(core_topics.topic_names(graph)) or "(none yet)"
            raise KeyError(f"unknown topic: {name!r}. Topics in this run: {known}")
        view = core_topics.topic_view(graph, name)
        if args.as_json:
            print(json.dumps(_view_dict(view), ensure_ascii=False, indent=2))
        else:
            _print_view(view, len(core_topics.topic_summary_history(graph, name)))
        return 0
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _print_overview(views: list[core_topics.TopicView]) -> None:
    if not views:
        print("no topics in this run. Start one with:")
        print("  arctx topic tag NAME RECORD_ID   (bundle records by meaning)")
        print('  arctx topic summarize NAME --summary "current statement"')
        return
    for view in views:
        active = sum(len(island) for island in view.islands)
        parts = [f"{active} records", f"{len(view.islands)} islands"]
        if view.inactive:
            parts.append(f"{len(view.inactive)} cut")
        line = view.summary.text if view.summary else "(no summary yet)"
        if len(line) > 90:
            line = line[:89] + "…"
        print(f"{view.name}  ·  {' · '.join(parts)}  ·  {line}")


def cli_topics(args) -> int:
    try:
        run_id = resolve_run_id_from_args(args)
        graph = resolve_store(args.store_dir).load_run(run_id).run_graph
        views = core_topics.list_topics(graph)
        if args.as_json:
            print(json.dumps({"topics": [_view_dict(v) for v in views]}, ensure_ascii=False, indent=2))
        else:
            _print_overview(views)
        return 0
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
