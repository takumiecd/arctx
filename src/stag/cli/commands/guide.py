"""stag CLI guide command."""

from __future__ import annotations

import argparse
import sys

TOPICS_EN: dict[str, str] = {
    "overview": """\
# stag guide

stag records optimization and problem-solving work as an append-only RunGraph DAG.

The graph skeleton has only three record types:

- Node: a state or point in the work history.
- Transition: an attempted step from one or more nodes.
- Edge: connectivity only, either Node -> Transition or Transition -> Node.

Meaning is attached as payloads. PlanPayload, PredictionPayload, ResultPayload,
GitChangePayload, NotePayload, and CutPayload explain what a node or transition
means without changing the graph skeleton.

Basic loop:

```text
init -> plan -> predict (optional) -> external work -> observe -> dump
```

Common commands:

```bash
stag init req_demo --run-id demo
stag plan --run demo --input-node <node_id> --intent "try baseline"
stag predict --run demo <transition_id> --max-outcomes 2
stag observe --run demo <transition_id> --status completed
stag dump --run demo
```
""",
    "agent": """\
# Agent Rules

- Treat Node and Transition IDs in the RunGraph as opaque.
- Put domain meaning in payloads, not graph record fields.
- Use `transition_id` for plan/predict/observe/outcomes/git operations.
- Use `stag dump` when you need broad context.
- Use CutPayload through `stag cut` instead of deleting records.
""",
    "dump": """\
# Dump

`stag dump` renders the active graph in outline or mermaid form. The graph is a
simple DAG of Node and Transition records connected by Edge records. Payloads
are shown as annotations, not as structural graph records. Result transitions
render with `→`; prediction transitions render with `⇢`; cut records render with `✂`;
revisited nodes may render with `↻`.
""",
    "record": """\
# Record One Experiment

```bash
stag init req_demo --run-id demo
stag plan --run demo --input-node <root_node_id> --intent "run benchmark"
stag observe --run demo <transition_id> --status completed --metric score=0.8
stag show --run demo --transition <transition_id> --with-payloads --outputs
```
""",
    "payloads": """\
# Payloads

- PlanPayload attaches to a Transition.
- PredictionPayload attaches to a Transition and may reference predicted output nodes in metadata.
- ResultPayload attaches to a Transition and may reference the observed output node in metadata.
- GitChangePayload attaches to a Transition with a ResultPayload.
- NotePayload attaches to a Node.
- CutPayload attaches to a Node or Transition.
""",
    "cut": """\
# Cut

`stag cut --node <node_id>` or `stag cut --transition <transition_id>` appends
an append-only CutPayload. Records are not deleted; inactive branches are computed at read time.
""",
    "joins": """\
# Joins

Pass multiple `--input-node` values to `stag plan` to create a Transition with
multiple incoming Node -> Transition edges.
""",
    "git": """\
# Git

Git sessions attach commit and diff information to a Transition.

```bash
stag git start <transition_id>
stag git finish <session_id> --status completed
stag git diff --transition <transition_id>
stag git log --transition <transition_id>
```
""",
}


TOPICS_JA: dict[str, str] = {
    "overview": """\
# stag guide

stag は作業履歴を append-only な DAG として記録します。

グラフ骨格はこの 3 種類だけです。

- Node: 作業履歴上の状態や地点。
- Transition: 1 つ以上の Node から試した作業。
- Edge: 接続だけを表す。Node -> Transition または Transition -> Node。

意味は payload に分離します。PlanPayload / PredictionPayload / ResultPayload /
GitChangePayload / NotePayload / CutPayload が、Node や Transition に意味を付けます。

基本ループ:

```text
init -> plan -> predict (任意) -> 外部で作業 -> observe -> dump
```
""",
    "agent": """\
# Agent Rules

- Node / Transition ID は opaque として扱う。
- ドメイン上の意味は graph record ではなく payload に入れる。
- plan/predict/observe/outcomes/git は `transition_id` を中心に扱う。
- 広い文脈確認は `stag dump` を使う。
- 履歴は削除せず、`stag cut` で CutPayload を追加する。
""",
    "dump": TOPICS_EN["dump"],
    "record": TOPICS_EN["record"],
    "payloads": TOPICS_EN["payloads"],
    "cut": TOPICS_EN["cut"],
    "joins": TOPICS_EN["joins"],
    "git": TOPICS_EN["git"],
}


GUIDES: dict[str, dict[str, str]] = {
    "ja": TOPICS_JA,
    "en": TOPICS_EN,
}

TOPIC_SUMMARIES: dict[str, str] = {
    "overview": "Concept, RunGraph model, basic loop",
    "agent": "Rules for agents using stag",
    "dump": "stag dump output model",
    "record": "Typical workflow to record one experiment",
    "payloads": "Payload types and attachment targets",
    "cut": "Append-only invalidation",
    "joins": "Multi-input transitions",
    "git": "Record Git commits and diffs on a Transition",
}

_DEFAULT_TOPIC = "overview"


def run_guide_command(*, lang: str = "en", topic: str = _DEFAULT_TOPIC) -> dict:
    """Return the guide text for *topic* in *lang*."""
    topics = GUIDES[lang]
    if topic not in topics:
        valid = ", ".join(sorted(topics))
        raise ValueError(f"Unknown topic {topic!r}. Valid topics: {valid}")
    return {"guide": topics[topic], "lang": lang, "topic": topic}


def run_guide_list(lang: str = "en") -> dict:
    """Return topic id + summary pairs for *lang*."""
    topics = GUIDES[lang]
    return {
        "topics": [{"id": tid, "summary": TOPIC_SUMMARIES.get(tid, "")} for tid in topics],
        "lang": lang,
    }


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``guide`` subcommand parser."""
    parser = subparsers.add_parser(
        "guide",
        help="Show the stag concept and CLI workflow guide",
        description="Show the stag concept, graph structure, and CLI workflow guide.",
    )
    parser.add_argument(
        "--lang",
        choices=sorted(GUIDES),
        default="en",
        help="Guide language (default: en)",
    )
    parser.add_argument(
        "--topic",
        default=None,
        metavar="NAME",
        help="Show a specific subtopic (see --list for names)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_topics",
        help="List available topic names and descriptions",
    )
    return parser


def cli_guide(args) -> int:
    """Entry point for ``stag guide`` subcommand."""
    if args.list_topics:
        result = run_guide_list(lang=args.lang)
        for entry in result["topics"]:
            print(f"  {entry['id']:<12}  {entry['summary']}")
        return 0

    topic = args.topic if args.topic is not None else _DEFAULT_TOPIC
    try:
        result = run_guide_command(lang=args.lang, topic=topic)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("Run `stag guide --list` to see available topics.", file=sys.stderr)
        return 1

    print(result["guide"])
    return 0
