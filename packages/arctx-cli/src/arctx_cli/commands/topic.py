"""``arctx topic`` / ``arctx topics`` — flat, name-keyed bundles of meaning.

A topic bundles records the way a lane bundles work and a trial table bundles
numbers: any node or step can carry a topic name, connectivity is never
required, and every view is derived at read time (see arctx.core.topics).

- ``topic tag NAME ID [ID ...]`` marks records as belonging to the topic.
- ``topic summarize NAME --summary TEXT`` writes the topic's current
  statement ("a strong tag"); the latest one wins, history stays.
- ``topic untag NAME ID [ID ...]`` reverses a tag (append-only supersession;
  the record itself is untouched — that is what makes it different from
  ``cut``).
- ``topic NAME`` / ``topic show NAME`` prints the statement plus the tagged
  records grouped into islands — two or more islands is the "these regions
  are about the same thing but not yet joined" signal.
- ``topics`` lists every topic one line each.

Two or more islands has exactly four resolutions, and each is a verb:

- both lineages are right, under different conditions → ``topic join``: one
  Step from every island tip, and the verdict lives on the Step's output
  node. A join has no "correct side": inputs are a set, and what comes after
  is the new node.
- it was two subjects all along → ``topic split``: move an island to its own
  name. Both topics come out with one island each.
- one island was a dead end → ``arctx cut`` on it.
- the tag was a mistake → ``topic untag``.

``join`` and ``split`` are compositions of existing verbs, not new records.
``join`` exists because doing it by hand does not work: islands are computed
over *tagged* records, so a Step joining two tips leaves the islands split
until the new output node is tagged too.
"""

from __future__ import annotations

import argparse
import json
import sys

from arctx.core import topics as core_topics

from arctx_cli.commands.add import _default_input_node_ids, run_add_step_command
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
            "tag NAME ID [ID ...] · untag NAME ID [ID ...] · summarize NAME · "
            "join NAME · split NAME · show NAME · log NAME · list. "
            "`arctx topic NAME` is show shorthand; `log` walks the statement "
            "history (latest is the current belief, nothing is deleted)."
        ),
    )
    parser.add_argument("--note", default=None, help="tag: short note on the mark")
    parser.add_argument(
        "--island",
        action="append",
        default=None,
        type=int,
        metavar="N",
        help="split: 1-based island number to move out (repeatable)",
    )
    parser.add_argument(
        "--into",
        default=None,
        metavar="NEW_NAME",
        help="split: the topic name the island moves to",
    )
    parser.add_argument(
        "--from",
        action="append",
        default=None,
        dest="input_nodes",
        metavar="NODE_ID",
        help="join: input node (repeatable). Default: every island tip.",
    )
    parser.add_argument("--title", default=None, help="join: title for the joining step")
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


def _record_lane_map(
    *, run_id: str, record_ids: list[str], store_dir: str | None, lane_id: str | None
) -> dict[str, str | None]:
    """Lane to attribute a tag/untag event to, per record.

    A tag annotates the record where it lives, so by default the event is
    attributed to *that record's own lane* — marking things while browsing
    never requires switching lanes or inventing a bookkeeping lane. An
    explicit --lane still wins, and a record in a closed lane falls back to
    the caller's lane (writes to closed lanes stay refused).
    """
    if lane_id is not None:
        return {}

    from arctx.core.lanes import lane_membership

    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    membership = lane_membership(handle.run_graph, root_node_id=handle.root_node_id)
    record_lane: dict[str, str | None] = {}
    for record_id in record_ids:
        owner = membership.node_to_lane.get(record_id) or membership.step_to_lane.get(
            record_id
        )
        owner_lane = handle.run_graph.lanes.get(owner) if owner else None
        record_lane[record_id] = (
            owner if owner_lane is not None and owner_lane.status == "open" else None
        )
    return record_lane


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

    record_lane = _record_lane_map(
        run_id=run_id, record_ids=record_ids, store_dir=store_dir, lane_id=lane_id
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


def _island_count(run_id: str, store_dir: str | None, name: str) -> int:
    graph = resolve_store(store_dir).load_run(run_id).run_graph
    return len(core_topics.topic_view(graph, name).islands)


def run_topic_untag_command(
    *,
    run_id: str,
    name: str,
    record_ids: list[str],
    store_dir: str | None,
    user_id: str | None = None,
    lane_id: str | None = None,
    fallback_lane_id: str | None = None,
    force: bool = False,
) -> dict:
    """Reverse a tag on ``(name, record)`` — append-only, never a delete.

    Untag says *the tag was wrong*; the record keeps every other tag it
    carries and stays active. Re-tagging later wins again (last marker wins).
    """
    if not record_ids:
        raise ValueError("topic untag needs at least one record id")

    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)
    graph = handle.run_graph
    tagged = {r.record_id for r in core_topics.topic_view(graph, name).records}
    for record_id in record_ids:
        if record_id not in graph.nodes and record_id not in graph.steps:
            raise KeyError(f"unknown record_id: {record_id}")
        if record_id not in tagged:
            raise ValueError(
                f'{record_id} is not tagged "{name}" — nothing to untag'
            )

    record_lane = _record_lane_map(
        run_id=run_id, record_ids=record_ids, store_dir=store_dir, lane_id=lane_id
    )
    results = []
    for record_id in record_ids:
        results.append(
            run_attach_command(
                run_id=run_id,
                target_id=record_id,
                payload_kind=core_topics.UNTAG_TYPE,
                payload_type=None,
                field_data={},
                json_data={"topic": name},
                store_dir=store_dir,
                user_id=user_id,
                lane_id=lane_id or record_lane.get(record_id) or fallback_lane_id,
                force=force,
            )
        )
    return {"topic": name, "untagged": record_ids, "payloads": results}


def run_topic_join_command(
    *,
    run_id: str,
    name: str,
    summary: str,
    title: str | None,
    input_node_ids: list[str] | None,
    store_dir: str | None,
    user_id: str | None = None,
    lane_id: str | None = None,
    force: bool = False,
) -> dict:
    """Join a topic's islands with one Step and record the verdict on it.

    Three writes, in the only order that works: the Step, the tag on its
    output node (without which the islands stay split — islands are computed
    over tagged records), then the statement, attached to that same node so
    the verdict sits where the join happened.
    """
    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    graph = store.load_run(run_id).run_graph
    if name not in core_topics.topic_names(graph):
        raise KeyError(f"unknown topic: {name!r}")
    view = core_topics.topic_view(graph, name)

    reused = False
    if not summary or not summary.strip():
        # When the current statement already cites two or more islands, the
        # subject was reconciled in prose and only the graph lagged behind.
        # Re-use that text rather than asking for it a second time.
        _, reconciling = core_topics.island_statements(graph, name)
        if reconciling is None:
            raise ValueError(
                "topic join needs --summary TEXT: joining is recording the "
                "verdict, not just drawing an edge"
            )
        summary = reconciling.text
        reused = True

    tips: list[str] = []
    if input_node_ids:
        inputs = list(dict.fromkeys(input_node_ids))
    else:
        if len(view.islands) < 2:
            raise ValueError(
                f'topic "{name}" already has {len(view.islands)} island — '
                f"nothing to join (pass --from explicitly to join anyway)"
            )
        for island in view.islands:
            tips.extend(core_topics.island_tips(graph, island))
        inputs = []
        for tip in tips:
            node_id = core_topics.record_output_node(graph, tip)
            if node_id is not None and node_id not in inputs:
                inputs.append(node_id)
    if len(inputs) < 2:
        raise ValueError("a join needs at least two input nodes")

    step = run_add_step_command(
        run_id=run_id,
        input_node_ids=inputs,
        title=title or summary.strip()[:60],
        payload_kind="topic_join",
        payload_type="step_payload",
        field_data={},
        json_data={"topic": name},
        store_dir=store_dir,
        user_id=user_id,
        lane_id=lane_id,
        force=force,
    )["step"]
    output_node_id = step["output_node_id"]

    run_topic_tag_command(
        run_id=run_id,
        name=name,
        record_ids=[output_node_id],
        note=None,
        store_dir=store_dir,
        user_id=user_id,
        lane_id=lane_id,
        force=force,
    )
    run_topic_summarize_command(
        run_id=run_id,
        name=name,
        text=summary,
        sources=tips or inputs,
        on_node=output_node_id,
        store_dir=store_dir,
        user_id=user_id,
        lane_id=lane_id,
        force=force,
    )
    return {
        "topic": name,
        "step": step,
        "joined": inputs,
        "islands": _island_count(run_id, store_dir, name),
        "reused_statement": reused,
    }


def run_topic_split_command(
    *,
    run_id: str,
    name: str,
    islands: list[int],
    into: str,
    summary: str,
    store_dir: str | None,
    user_id: str | None = None,
    lane_id: str | None = None,
    force: bool = False,
) -> dict:
    """Move whole islands of *name* to their own topic *into*.

    The resolution for "it was two subjects all along": untag the island from
    the old name, tag it with the new one, and give the new topic the
    statement that made it a separate subject. Both topics come out with one
    island each.
    """
    if not into or not into.strip():
        raise ValueError("topic split needs --into NEW_NAME")
    if into.strip() == name:
        raise ValueError("--into must differ from the topic being split")
    if not summary or not summary.strip():
        raise ValueError(
            "topic split needs --summary TEXT: the new topic needs its own statement"
        )
    if not islands:
        raise ValueError("topic split needs --island N (1-based, as printed)")

    store = resolve_store(store_dir)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    graph = store.load_run(run_id).run_graph
    if name not in core_topics.topic_names(graph):
        raise KeyError(f"unknown topic: {name!r}")
    view = core_topics.topic_view(graph, name)

    moved: list[str] = []
    for number in islands:
        if number < 1 or number > len(view.islands):
            raise ValueError(
                f'topic "{name}" has {len(view.islands)} island(s); --island {number} '
                f"is out of range"
            )
        moved.extend(view.islands[number - 1])
    moved = list(dict.fromkeys(moved))

    anchor_node = core_topics.record_output_node(graph, moved[-1])

    run_topic_untag_command(
        run_id=run_id,
        name=name,
        record_ids=moved,
        store_dir=store_dir,
        user_id=user_id,
        lane_id=lane_id,
        force=force,
    )
    run_topic_tag_command(
        run_id=run_id,
        name=into.strip(),
        record_ids=moved,
        note=None,
        store_dir=store_dir,
        user_id=user_id,
        lane_id=lane_id,
        fallback_lane_id=lane_id,
        force=force,
    )
    run_topic_summarize_command(
        run_id=run_id,
        name=into.strip(),
        text=summary,
        sources=None,
        on_node=anchor_node,
        store_dir=store_dir,
        user_id=user_id,
        lane_id=lane_id,
        force=force,
    )
    return {
        "topic": name,
        "into": into.strip(),
        "moved": moved,
        "islands": _island_count(run_id, store_dir, name),
        "into_islands": _island_count(run_id, store_dir, into.strip()),
    }


def _refuse_cross_island_overwrite(
    graph, *, name: str, text: str, sources: list[str] | None, target: str
) -> None:
    """Stop a statement from silently superseding another lineage's belief.

    A topic keeps one current statement and the latest wins — which is right
    for a single line of reasoning, and wrong across unjoined islands: the
    other lineage's conclusion would vanish from every view while its records
    stay active. That is a merge conflict, so this refuses like one, instead
    of asking a question no agent should answer on its own.
    """
    view = core_topics.topic_view(graph, name)
    if len(view.islands) < 2 or view.summary is None:
        return
    current_islands = core_topics.statement_islands(graph, view.islands, view.summary)
    if len(current_islands) != 1:
        return  # unanchored, or already reconciled across islands
    candidate = core_topics.TopicSummary(
        payload_id="(new)",
        target_id=target,
        text=text,
        sources=tuple(sources or ()),
    )
    new_islands = core_topics.statement_islands(graph, view.islands, candidate)
    if len(new_islands) != 1 or new_islands == current_islands:
        return

    current_index = next(iter(current_islands))
    new_index = next(iter(new_islands))
    raise ValueError(
        f'topic "{name}" is split, and this statement speaks for island '
        f"{new_index + 1} while the current one speaks for island "
        f"{current_index + 1}:\n"
        f"  island {current_index + 1} (current): {view.summary.text}\n"
        f"  island {new_index + 1} (yours):    {text}\n"
        f"Writing this would drop the other lineage's conclusion from every "
        f"view while its records stay active. Which one is right is a "
        f"judgement, not something the data settles — ask, then reconcile:\n"
        f'  both, under different conditions → arctx topic join {name} --summary "..."\n'
        f"  two subjects                     → arctx topic split {name} "
        f'--island {new_index + 1} --into NEW_NAME --summary "..."\n'
        f"  the other island is a dead end   → arctx cut <ID>\n"
        f"  record it anyway                 → --force"
    )


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
    if not force:
        _refuse_cross_island_overwrite(
            graph, name=name, text=text.strip(), sources=sources, target=target
        )
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


def split_notice(graph, view: core_topics.TopicView) -> list[str]:
    """Build the "this subject is split" nudge — a candidate, not an error.

    Four lines because a split has exactly four resolutions, and each one is
    a command the reader can run as printed. Nothing here blocks or prompts:
    arctx is driven by agents as much as by people, and a blocking question
    is poison to both.
    """
    if len(view.islands) < 2:
        return []
    lanes = _record_lanes(graph, view)
    per_island, reconciling = core_topics.island_statements(graph, view.name)
    lines = [f'topic "{view.name}" spans {len(view.islands)} unjoined islands']
    tips_by_island: list[str] = []
    for index, island in enumerate(view.islands, 1):
        tips = core_topics.island_tips(graph, island) or (island[-1],)
        tips_by_island.append(tips[0])
        lane = lanes.get(tips[0])
        lines.append(
            f"  island {index}  {len(island)} records  tip {tips[0]}"
            + (f"  (lane {lane})" if lane else "")
        )
        # Show what each lineage concluded: "2 islands" is a shape, but the
        # contradiction people have to settle lives in the two statements.
        statement = per_island[index - 1]
        lines.append(
            f"    says: {_clip(statement.text)}" if statement is not None
            else "    says: (nothing of its own)"
        )
    last = tips_by_island[-1]
    if reconciling is not None:
        lines += [
            f"  the current statement already cites {len(view.islands)} islands, so the",
            f"  subject is settled in prose and only the graph lags behind:",
            f"    → arctx topic join {view.name}   (reuses that statement as the verdict)",
        ]
    else:
        lines += [
            "  both are right, under different conditions",
            f'    → arctx topic join {view.name} --summary "..."',
        ]
    lines += [
        "  they turned out to be two subjects",
        f'    → arctx topic split {view.name} --island {len(view.islands)} '
        f'--into NEW_NAME --summary "..."',
        f"  island {len(view.islands)} was a dead end",
        f'    → arctx cut {last} --reason "..."',
        "  the tag was a mistake",
        f"    → arctx topic untag {view.name} {last}",
    ]
    return lines


def _clip(text: str, width: int = 72) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= width else collapsed[: width - 1] + "…"


def _record_lanes(graph, view: core_topics.TopicView) -> dict[str, str]:
    from arctx.core.lanes import lane_membership

    membership = lane_membership(graph)
    out: dict[str, str] = {}
    for record in view.records:
        owner = membership.node_to_lane.get(record.record_id) or (
            membership.step_to_lane.get(record.record_id)
        )
        lane = graph.lanes.get(owner) if owner else None
        if lane is not None:
            out[record.record_id] = lane.name
    return out


def warn_if_split(graph, name: str, *, only_if_new_since: int | None = None) -> None:
    """Print the split nudge on stderr, exit code untouched."""
    view = core_topics.topic_view(graph, name)
    if only_if_new_since is not None and len(view.islands) <= only_if_new_since:
        return
    lines = split_notice(graph, view)
    if not lines:
        return
    print(f"notice: {lines[0]}", file=sys.stderr)
    for line in lines[1:]:
        print(line, file=sys.stderr)


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


def _print_view(view: core_topics.TopicView, history_count: int = 0, graph=None) -> None:
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
    if len(view.islands) > 1 and graph is not None:
        for line in split_notice(graph, view):
            print(f"  {line}")


def cli_topic(args) -> int:
    try:
        run_id = resolve_run_id_from_args(args)
        positional = list(args.args)
        command = positional[0] if positional else "list"
        if command == "tag":
            if len(positional) < 3:
                raise ValueError("usage: arctx topic tag NAME RECORD_ID [RECORD_ID ...]")
            before = _island_count(run_id, args.store_dir, positional[1])
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
            # The moment a tag splits the subject is the moment to say so:
            # whoever tagged it is holding both tips right now.
            graph = resolve_store(args.store_dir).load_run(run_id).run_graph
            warn_if_split(graph, positional[1], only_if_new_since=max(before, 1))
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
            graph = resolve_store(args.store_dir).load_run(run_id).run_graph
            warn_if_split(graph, positional[1])
            return 0
        if command == "untag":
            if len(positional) < 3:
                raise ValueError("usage: arctx topic untag NAME RECORD_ID [RECORD_ID ...]")
            result = run_topic_untag_command(
                run_id=run_id,
                name=positional[1],
                record_ids=positional[2:],
                store_dir=args.store_dir,
                user_id=resolve_user_id_from_args(args),
                lane_id=args.lane,
                fallback_lane_id=resolve_lane_id_from_args(args),
                force=args.force,
            )
            print(
                f"untagged {len(result['untagged'])} records from topic "
                f"\"{result['topic']}\" (the records themselves are untouched)"
            )
            return 0
        if command == "join":
            if len(positional) < 2:
                raise ValueError('usage: arctx topic join NAME --summary "verdict"')
            result = run_topic_join_command(
                run_id=run_id,
                name=positional[1],
                summary=args.summary or "",
                title=args.title,
                input_node_ids=args.input_nodes,
                store_dir=args.store_dir,
                user_id=resolve_user_id_from_args(args),
                lane_id=resolve_lane_id_from_args(args),
                force=args.force,
            )
            island_word = "island" if result["islands"] == 1 else "islands"
            print(
                f"joined {len(result['joined'])} lineages of topic "
                f"\"{result['topic']}\" — {result['islands']} {island_word} now"
            )
            print(f"  verdict on {result['step']['output_node_id']}")
            if result.get("reused_statement"):
                print("  (reused the current statement — it already cited both sides)")
            return 0
        if command == "split":
            if len(positional) < 2:
                raise ValueError(
                    'usage: arctx topic split NAME --island N --into NEW --summary "..."'
                )
            result = run_topic_split_command(
                run_id=run_id,
                name=positional[1],
                islands=args.island or [],
                into=args.into or "",
                summary=args.summary or "",
                store_dir=args.store_dir,
                user_id=resolve_user_id_from_args(args),
                lane_id=args.lane,
                force=args.force,
            )
            print(
                f"moved {len(result['moved'])} records from \"{result['topic']}\" "
                f"to \"{result['into']}\""
            )
            print(
                f"  {result['topic']}: {result['islands']} island(s) · "
                f"{result['into']}: {result['into_islands']} island(s)"
            )
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
            _print_view(view, len(core_topics.topic_summary_history(graph, name)), graph)
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
