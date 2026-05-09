# optagent

optagent は、問題解決や最適化の過程を DAG と JSONL で記録するための Python ライブラリです。

最終成果だけでなく、途中で立てた plan、実行前の予測、実際に起きた結果を残すことを目的にしています。現在は 0.1 alpha で、後方互換よりもモデル整理を優先します。古い run 保存形式や旧 API との互換は保証しません。

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

## CLI Quick Start

```bash
export PYTHONPATH=src

python3 -m optagent.cli.main init req_kernel \
  --target-type kernel \
  --target-id csc_linear \
  --run-id demo

python3 -m optagent.cli.main plan \
  --run demo \
  --input-node n_0000 \
  --intent "run baseline benchmark"

python3 -m optagent.cli.main predict \
  --run demo \
  it_0001 \
  --max-outcomes 1

python3 -m optagent.cli.main observe \
  --run demo \
  it_0001 \
  --matched-prediction ot_0001 \
  --status completed \
  --raw-output raw/profile.txt \
  --metric latency_ms=1.5

python3 -m optagent.cli.main trace --run demo --from-node n_0002
python3 -m optagent.cli.main show --run demo
```

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
