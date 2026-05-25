"""stag CLI guide command."""

from __future__ import annotations

import argparse
import sys

TOPICS_EN: dict[str, str] = {
    "overview": """\
# stag guide

stag records optimization and problem-solving work as an append-only RunGraph DAG.

The graph skeleton has two record types:

- Node: a state or point in the work history.
- Transition: a step from one or more input nodes to exactly one output node.

Meaning is attached as payloads. TransitionPayload, NodePayload,
GitChangePayload, and CutPayload explain what a node or transition means.

Basic loop:

```text
init -> transition -> dump
```

Common commands:

```bash
stag init req_demo --run-id demo
stag transition --run demo --inputs <node_id> --type experiment --content '{"name": "baseline"}'
stag attach --run demo --node <node_id> --type note --content '{"text": "context here"}'
stag dump --run demo
```
""",
    "agent": """\
# Agent Rules

- Treat Node and Transition IDs as opaque.
- Put domain meaning in payloads (TransitionPayload / NodePayload), not in graph fields.
- Use `stag transition` to record attempts. Use `stag attach` for node annotations.
- Use `stag dump` when you need broad context.
- Use CutPayload through `stag cut` instead of deleting records.
""",
    "dump": """\
# Dump

`stag dump` renders the active graph in outline or mermaid form. Each Transition
has exactly one output Node. Cut records render with `✂`; revisited nodes with `↻`.
""",
    "record": """\
# Record One Experiment

```bash
stag init req_demo --run-id demo
stag transition --run demo --inputs <root_node_id> --type experiment --content '{"name": "run1"}'
stag show --run demo --transition <transition_id> --with-payloads
```
""",
    "payloads": """\
# Payloads

- TransitionPayload attaches to a Transition. Use `type` to describe the kind of step.
- NodePayload attaches to a Node. Use `type` to describe the kind of annotation.
- GitChangePayload attaches to a Transition with git commit / diff info.
- CutPayload attaches to a Node or Transition to mark it inactive.

Custom subclasses of PayloadBase can be registered with `register_payload_class()`.
""",
    "cut": """\
# Cut

`stag cut --node <node_id>` or `stag cut --transition <transition_id>` appends
an append-only CutPayload. Records are not deleted; inactive branches are computed at read time.
""",
    "joins": """\
# Joins (Multi-input Transitions)

Pass multiple `--inputs` values to `stag transition` to create a Transition with
multiple input nodes but still exactly one output node.
""",
    "git": """\
# Git

Git sessions attach commit and diff information to a Transition.

```bash
stag git start <transition_id>
stag git finish <session_id>
stag git diff --transition <transition_id>
stag git log --transition <transition_id>
```
""",
}


TOPICS_JA: dict[str, str] = {
    "overview": """\
# stag guide

stag は作業履歴を append-only な DAG として記録します。

グラフ骨格はこの 2 種類だけです。

- Node: 作業履歴上の状態や地点。
- Transition: 1 つ以上の Node から 1 つの output Node への作業ステップ。

意味は payload に分離します。TransitionPayload / NodePayload /
GitChangePayload / CutPayload が、Node や Transition に意味を付けます。

基本ループ:

```text
init -> transition -> dump
```
""",
    "agent": """\
# Agent Rules

- Node / Transition ID は opaque として扱う。
- ドメイン上の意味は graph record ではなく payload に入れる。
- 作業の記録は `stag transition`、ノードへの注釈は `stag attach`。
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
    parser = subparsers.add_parser(
        "guide",
        help="Show the stag concept and CLI workflow guide",
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
