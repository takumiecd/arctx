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
stag transition create --run demo --from <node_id> \\
  --payload-type transition_payload --field type=experiment --field name=baseline
stag payload add --run demo --node <node_id> \\
  --payload-type node_payload --field type=note --field text="context here"
stag graph dump --run demo
```
""",
    "agent": """\
# Agent Rules

- Treat Node and Transition IDs as opaque.
- Put domain meaning in payloads (TransitionPayload / NodePayload), not in graph fields.
- Use `stag transition create` to record attempts.
- Use `stag payload add` for node or transition annotations.
- Use `stag graph dump` when you need broad context.
- Use CutPayload through `stag cut` instead of deleting records.
""",
    "dump": """\
# Dump

`stag graph dump` renders the active graph in outline or mermaid form. Each
Transition has exactly one output Node. Cut records render with `✂`; revisited
nodes with `↻`.
""",
    "record": """\
# Record One Experiment

```bash
stag init req_demo --run-id demo
stag transition create --run demo --from <root_node_id> \\
  --payload-type transition_payload --field type=experiment --field name=run1
stag transition show --run demo <transition_id> --with-payloads
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

Pass multiple `--from` values to `stag transition create` to create a
Transition with multiple input nodes but still exactly one output node.
""",
    "git": """\
# Git

Git commands attach commit information to a Transition.

```bash
stag git add --run demo --transition <transition_id> --commit <sha>
stag git list --run demo --transition <transition_id>
stag git show --run demo --transition <transition_id>
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

よく使うコマンド:

```bash
stag init req_demo --run-id demo
stag transition create --run demo --from <node_id> \\
  --payload-type transition_payload --field type=experiment --field name=baseline
stag payload add --run demo --node <node_id> \\
  --payload-type node_payload --field type=note --field text="context here"
stag graph dump --run demo
```
""",
    "agent": """\
# Agent Rules

- Node / Transition ID は opaque として扱う。
- ドメイン上の意味は graph record ではなく payload に入れる。
- 作業の記録は `stag transition create` を使う。
- Node / Transition への注釈は `stag payload add` を使う。
- 広い文脈確認は `stag graph dump` を使う。
- 履歴は削除せず、`stag cut` で CutPayload を追加する。
""",
    "dump": """\
# Dump

`stag graph dump` は active graph を outline または mermaid 形式で表示します。
各 Transition は必ず 1 つの output Node を持ちます。Cut 済みレコードは `✂`、
再訪した Node は `↻` で表示されます。
""",
    "record": """\
# 1 つの実験を記録する

```bash
stag init req_demo --run-id demo
stag transition create --run demo --from <root_node_id> \\
  --payload-type transition_payload --field type=experiment --field name=run1
stag transition show --run demo <transition_id> --with-payloads
```
""",
    "payloads": """\
# Payloads

- TransitionPayload は Transition に付けます。`type` で作業ステップの種類を表します。
- NodePayload は Node に付けます。`type` で注釈の種類を表します。
- GitChangePayload は Transition に付け、commit 情報を保持します。
- CutPayload は Node または Transition に付け、inactive として扱うために使います。

独自の PayloadBase サブクラスは `register_payload_class()` で登録できます。
""",
    "cut": """\
# Cut

`stag cut node <node_id>` または `stag cut transition <transition_id>` は
append-only な CutPayload を追加します。レコードは削除されません。inactive な
branch は読み取り時に計算されます。
""",
    "joins": """\
# Joins (Multi-input Transitions)

`stag transition create` に複数の `--from` を渡すと、複数 input node から
1 つの output node へ向かう Transition を作成できます。
""",
    "git": """\
# Git

Git コマンドは Transition に commit 情報を付けます。

```bash
stag git add --run demo --transition <transition_id> --commit <sha>
stag git list --run demo --transition <transition_id>
stag git show --run demo --transition <transition_id>
```
""",
}


GUIDES: dict[str, dict[str, str]] = {
    "ja": TOPICS_JA,
    "en": TOPICS_EN,
}

TOPIC_SUMMARIES: dict[str, dict[str, str]] = {
    "en": {
        "overview": "Concept, RunGraph model, basic loop",
        "agent": "Rules for agents using stag",
        "dump": "stag graph dump output model",
        "record": "Typical workflow to record one experiment",
        "payloads": "Payload types and attachment targets",
        "cut": "Append-only invalidation",
        "joins": "Multi-input transitions",
        "git": "Record Git commits on a Transition",
    },
    "ja": {
        "overview": "概念、RunGraph model、基本ループ",
        "agent": "stag を使う agent 向けルール",
        "dump": "stag graph dump の出力モデル",
        "record": "1 つの実験を記録する基本フロー",
        "payloads": "Payload の種類と attachment target",
        "cut": "Append-only な無効化",
        "joins": "複数 input node の Transition",
        "git": "Transition への Git commit 記録",
    },
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
    summaries = TOPIC_SUMMARIES[lang]
    return {
        "topics": [{"id": tid, "summary": summaries.get(tid, "")} for tid in topics],
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
