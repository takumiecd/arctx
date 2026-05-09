"""optagent CLI guide command."""

from __future__ import annotations

import argparse


GUIDE_TEXT_JA = """# optagent guide

optagent は、最適化や問題解決の過程を append-only な履歴グラフとして記録するための基盤です。

optagent は executor、code generator、benchmark runner、chatbot framework ではありません。実行や生成は外側の system が担当します。optagent は、それらが何を計画し、何を予測し、実際に何を観測し、何を無効化したのかを保存します。

## optagent が構築するもの

1 つの run は `RunGraph` です。`RunGraph` は状態と transition の DAG です。

- `Node`: 問題解決プロセス上の 1 つの地点。
- `InputTransition`: 1 つ以上の input node から何を試すか。
- `OutputTransition`: その試行から到達した 1 つの outcome node。
- `GraphView`: ある node を root とする名前付き view。中身は reachability で計算されます。

意味のある情報は graph record に直接埋め込まず、payload として attach します。

- `PlanPayload`: 何を試すつもりだったか。
- `PredictionPayload`: 実行前にどうなると見込んだか。
- `ResultPayload`: 実際に何が起きたか。
- `NotePayload`: node に対する軽い文脈やメモ。
- `CutPayload`: 間違った plan、prediction、result の append-only な無効化。

## 基本ループ

```text
init
  -> plan
  -> predict
  -> optagent の外で実行
  -> observe
  -> trace / show / outcomes
```

## CLI との対応

- `optagent init`: run を作り、root node を作成する。
- `optagent plan`: 次の試行を input transition として記録する。
- `optagent predict`: plan に対する実行前の予測を記録する。
- `optagent observe`: 外部実行後の実測結果を記録する。
- `optagent note`: node に人間や evaluator 向けの文脈を残す。
- `optagent rewind`: 履歴を消さずに transition を無効化する。
- `optagent trace`: ある node に至る履歴を読む。
- `optagent outcomes`: 1 つの input transition の予測と実測を比較する。
- `optagent reachable`: node や view から見える active subgraph を調べる。
- `optagent view`: 名前付き graph view を作成・表示する。
- `optagent show`: run 内の record を表示する。
- `optagent list`, `current`, `use`: 保存済み run を管理する。

## 最小例

```bash
optagent init req_kernel --target-type kernel --target-id csc_linear --run-id demo
optagent plan --run demo --input-node n_0000 --intent "run baseline benchmark"
optagent predict --run demo it_0001 --max-outcomes 1
optagent observe --run demo it_0001 --matched-prediction ot_0001 \\
  --status completed --raw-output raw/profile.txt --metric latency_ms=1.5
optagent trace --run demo --from-node n_0002
optagent show --run demo
```

既定では run は `.optagent/runs` 以下に保存されます。
"""


GUIDE_TEXT_EN = """# optagent guide

optagent is a foundation for recording optimization and problem-solving processes as an
append-only history graph.

It is not an executor, code generator, benchmark runner, or chatbot framework. Those
systems run outside optagent. optagent records what they planned, predicted, observed,
and invalidated so the process can be inspected later.

## What optagent builds

Each run is a `RunGraph`: a DAG of states and transitions.

- `Node`: a point in the process.
- `InputTransition`: the operation to try from one or more input nodes.
- `OutputTransition`: one possible outcome node reached from an input transition.
- `GraphView`: a named view rooted at one node; its contents are computed by reachability.

Meaning is attached with payloads instead of being embedded directly in graph records.

- `PlanPayload`: what we intended to try.
- `PredictionPayload`: what we expected before running it.
- `ResultPayload`: what actually happened.
- `NotePayload`: lightweight context on a node.
- `CutPayload`: append-only invalidation for a bad plan, prediction, or result.

## Core loop

```text
init
  -> plan
  -> predict
  -> run outside optagent
  -> observe
  -> trace / show / outcomes
```

## CLI mapping

- `optagent init`: create a run and seed the root node.
- `optagent plan`: record the next trial as an input transition.
- `optagent predict`: record expected outcomes for a plan.
- `optagent observe`: record actual results after external execution.
- `optagent note`: attach human or evaluator context to a node.
- `optagent rewind`: invalidate a transition without deleting history.
- `optagent trace`: read the path that led to a node.
- `optagent outcomes`: compare predictions and observations for one input transition.
- `optagent reachable`: inspect the active subgraph from a node or view.
- `optagent view`: create and inspect named graph views.
- `optagent show`: inspect run records.
- `optagent list`, `current`, `use`: manage saved runs.

## Minimal example

```bash
optagent init req_kernel --target-type kernel --target-id csc_linear --run-id demo
optagent plan --run demo --input-node n_0000 --intent "run baseline benchmark"
optagent predict --run demo it_0001 --max-outcomes 1
optagent observe --run demo it_0001 --matched-prediction ot_0001 \\
  --status completed --raw-output raw/profile.txt --metric latency_ms=1.5
optagent trace --run demo --from-node n_0002
optagent show --run demo
```

By default, runs are stored under `.optagent/runs`.
"""


GUIDES = {
    "ja": GUIDE_TEXT_JA,
    "en": GUIDE_TEXT_EN,
}


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``guide`` subcommand parser."""
    parser = subparsers.add_parser(
        "guide",
        help="Show the optagent concept and CLI workflow guide",
        description="Show the optagent concept, graph structure, and CLI workflow guide.",
    )
    parser.add_argument(
        "--lang",
        choices=sorted(GUIDES),
        default="en",
        help="Guide language (default: en)",
    )
    return parser


def run_guide_command(*, lang: str = "en") -> dict:
    """Return the built-in optagent guide."""
    return {"guide": GUIDES[lang], "lang": lang}


def cli_guide(args) -> int:
    """Entry point for ``optagent guide`` subcommand."""
    result = run_guide_command(lang=args.lang)
    print(result["guide"])
    return 0
