# optagent

optagent は、問題解決や最適化の過程を DAG と JSONL で記録するための Python ライブラリです。

最終成果だけでなく、途中で立てた plan、実行前の予測、実際に起きた結果を残すことを目的にしています。現在は 0.1 alpha で、後方互換よりもモデル整理を優先します。古い run 保存形式や旧 API との互換は保証しません。

## 何を構築しているか

optagent が構築しているのは、最適化プロセスのための append-only な履歴グラフです。

コード最適化、カーネル最適化、実験、調査では、最終的な成果物だけでなく、途中で何を試し、どうなると予測し、実際に何が起きたかが重要になります。optagent は、その試行錯誤を `RunGraph` と payload の形で保存します。

CLI や Python API は、この履歴グラフを操作するための入口です。`init` で run を作り、`plan` で次の試行を記録し、`predict` で実行前の見込みを残し、`observe` で実測結果を保存します。`trace` や `show` は、保存された判断の過程を読み返すために使います。

optagent 自体は executor や code generator ではありません。人間、LLM、script、benchmark runner、executor が行った判断や結果を、あとから共有・検証できる構造として残すための基盤です。

## モデル

0.1 の中心は `RunGraph` です。`RunGraph` が run 全体の DAG を持ち、`GraphView` がその部分集合を表します。

```text
RunHandle
  └── run_graph: RunGraph

RunGraph
  ├── nodes
  ├── input_transitions
  ├── output_transitions
  ├── payloads
  └── views

GraphView
  ├── view_id
  └── root_node_id
```

`InputTransition` は複数 input node を受け取る入力側 transition です。`PlanPayload` はここに attach します。`OutputTransition` は 1 つの output node に到達する出力側 transition です。`PredictionPayload` / `ResultPayload` はここに attach します。

node には軽いメモとして `NotePayload` を attach できます。

`RunGraph` は append-only です。一度追加した node / input transition / output transition / payload は削除せず、取り消しや無効化は `CutPayload` と read-time の計算で表します。

## Quick Start

```python
import optagent
from optagent import PlanPayload, Requirement, ResultPayload
from optagent.storage import JsonlRunStore

requirement = Requirement(
    requirement_id="req_kernel",
    target_type="kernel",
    target_id="csc_linear",
)

run = optagent.init(requirement, run_id="demo")

input_transition = run.plan(
    [run.root_node_id],
    PlanPayload(
        payload_id="pending",
        target_id="pending",
        intent="run baseline benchmark",
    ),
)

prediction = run.predict(input_transition.input_transition_id, max_outcomes=1)[0]

observed = run.observe(
    input_transition.input_transition_id,
    ResultPayload(
        payload_id="pending",
        target_id="pending",
        status="completed",
        raw_outputs=("raw/profile.txt",),
        metrics={"latency_ms": 1.5},
        matched_prediction_output_id=prediction.output_transition_id,
    ),
)

history = run.trace(observed.to_node_id)

store = JsonlRunStore("runs")
run.save(store)
loaded = store.load_run("demo")
```

隔離した探索をしたい場合は `GraphView` を作ります。`GraphView` は `root_node_id` だけを持ち、内容は read-time に `RunGraph.reachable_from(root_node_id)` で算出します。

## Install

Python 3.10 以上が必要です。

開発中の checkout から使う場合は、repo root で editable install します。

```bash
python3 -m pip install -e .
```

開発用 dependency も入れる場合は次を使います。

```bash
python3 -m pip install -e ".[dev]"
```

インストールせずに試す場合は、repo root で `PYTHONPATH=src python3 -m optagent.cli.main ...` として実行できます。

## CLI Quick Start

CLI から概念と基本ループを確認するには、次を実行します。

```bash
optagent guide
```

日本語で表示したい場合は `optagent guide --lang ja` を使います。

```bash
optagent init req_kernel \
  --target-type kernel \
  --target-id csc_linear \
  --run-id demo

optagent plan \
  --run demo \
  --input-node n_0000 \
  --intent "run baseline benchmark"

optagent predict \
  --run demo \
  it_0001 \
  --max-outcomes 1

optagent observe \
  --run demo \
  it_0001 \
  --matched-prediction ot_0001 \
  --status completed \
  --raw-output raw/profile.txt \
  --metric latency_ms=1.5

optagent trace --run demo --from-node n_0002
optagent show --run demo
```

未インストールで同じ操作をする場合は、各 command を `PYTHONPATH=src python3 -m optagent.cli.main ...` に置き換えます。

## 主な用語

- `Requirement`: run の目的。
- `RunGraph`: run 全体の DAG と global records。
- `GraphView`: `RunGraph` の部分集合。
- `Node`: pure graph node。
- `InputTransition`: 複数 input node を受け取る入力側 transition。
- `OutputTransition`: 1 つの output node に到達する出力側 transition。
- `NotePayload`: node に attach される軽いメモ。
- `PlanPayload`: `InputTransition` に attach される plan 情報。
- `PredictionPayload`: prediction output に attach される予測情報。
- `ResultPayload`: observed output に attach される実行結果。
- `CutPayload`: input / output transition の無効化を append-only に表す payload。

## 保存形式

`JsonlRunStore` は run をディレクトリとして保存します。

```text
<store-dir>/<run-id>/
  run.json
  graph.json
  views.jsonl
  nodes.jsonl
  input_transitions.jsonl
  output_transitions.jsonl
  payloads.jsonl
```

0.1 alpha では保存形式を破壊的に変える可能性があります。旧 `states.jsonl` / `execution_plans.jsonl` 形式との読み込み互換は持たせません。

## ドキュメント

- [コンセプト](docs/ja/CONCEPT.md)
- [プロジェクトの方向性](docs/ja/DIRECTION.md)
- [状態モデル](docs/ja/STATE_MODEL.md)
- [API](docs/ja/API.md)
- [CLI](docs/ja/CLI.md)
- [問題解決ループ](docs/ja/AGENT_LOOP.md)

## 開発

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q
```

## License

MIT
