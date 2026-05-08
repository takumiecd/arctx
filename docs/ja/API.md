# API

この文書は、0.1 alpha で目指す Python API を説明します。破壊的変更を許容し、旧 API との互換は維持しません。

## 最小例

```python
import optagent
from optagent import PlanPayload, Requirement, ResultPayload

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
        intent="run benchmark",
        inputs={"shape": "small"},
    ),
)

prediction = run.predict(input_transition.input_transition_id, max_outcomes=1)[0]

observed = run.observe(
    input_transition.input_transition_id,
    ResultPayload(
        payload_id="pending",
        target_id="pending",
        status="completed",
        raw_outputs=("raw/bench.txt",),
        metrics={"latency_ms": 1.5},
        matched_prediction_output_id=prediction.output_transition_id,
    ),
)

history = run.trace(observed.to_node_id)
```

## Public Dataclasses

主な public model:

- `Requirement`
- `RunGraph`
- `GraphView`
- `Node`
- `InputTransition`
- `OutputTransition`
- `PayloadBase`
- `NotePayload`
- `PlanPayload`
- `PredictionPayload`
- `ResultPayload`
- `CutPayload`
- `TraceContext`

`Dag` は全体 graph を表す名前としては使わず、`RunGraph` に置き換えます。部分集合は `GraphView` です。

`Plan` は graph record としては使いません。plan 情報は `InputTransition` に attach される `PlanPayload` です。

`SnapshotPayload` / `DerivedPayload` / `MatchPayload` / `PredictionSelection` / `PredictionPath` は 0.1 の最小 API から外します。

## `optagent.init`

```python
optagent.init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle
```

新しい run を作ります。

作られるもの:

- `run.run_graph`: run 全体の `RunGraph`
- `run.run_graph.views["main"]`: default `GraphView`（root は `n_0000`）
- root node: `run.root_node_id`

## `run.plan`

```python
run.plan(
    input_node_ids: list[str] | tuple[str, ...],
    payload: PlanPayload,
    *,
    user_id: str | None = None,
) -> InputTransition
```

複数 input node を受け取り、`InputTransition` を作ります。plan の intent、入力、制約、仮定などは `PlanPayload` としてその input transition に attach します。

cut 済み input transition の下流 node や inactive な node を渡すと `ValueError` です。

## `run.note`

```python
run.note(
    node_id: str,
    text: str,
    *,
    tags: list[str] | tuple[str, ...] = (),
    user_id: str | None = None,
) -> NotePayload
```

node に軽いメモとして `NotePayload` を attach します。既存 node や transition は変更しません。

## `run.predict`

```python
run.predict(
    input_transition_id: str,
    *,
    payloads: list[PredictionPayload] | None = None,
    max_outcomes: int | None = None,
    user_id: str | None = None,
) -> list[OutputTransition]
```

prediction output の `OutputTransition` を作ります。各 output transition には `PredictionPayload` が attach されます。

## `run.observe`

```python
run.observe(
    input_transition_id: str,
    result: ResultPayload,
    *,
    user_id: str | None = None,
) -> OutputTransition
```

実行結果を observed output の `OutputTransition` として記録します。新しい output transition に `ResultPayload` を attach します。

予測と実測の対応は `ResultPayload.matched_prediction_output_id` で表します。

1 つの input transition から prediction output は複数作れますし、observed output も複数作れます。確率的に結果が変わる操作では同じ input transition の下に複数 observed output を並べて記録できます。

`run.result(...)` は `run.observe(...)` の alias です。

## `run.rewind`

```python
run.rewind(
    target_id: str,
    *,
    target_kind: Literal["input_transition", "output_transition"],
    reason: str | None = None,
    user_id: str | None = None,
) -> CutPayload
```

`CutPayload` を attach します。既存レコードは削除しません。

`target_kind="input_transition"` の場合は plan 全体を inactive にします。`target_kind="output_transition"` の場合は prediction / result output だけを inactive にします。

## `run.trace`

```python
run.trace(
    node_id: str,
    *,
    depth: int | None = None,
    include_predictions: bool = False,
    include_raw_refs: bool = True,
) -> TraceContext
```

node から過去の output transition、input transition、input node を辿ります。`include_predictions=False` の場合は observed output を中心に履歴を作ります。`run.history(...)` は alias です。

## GraphView API

```python
run.view_create(name: str, *, root_node_id: str) -> GraphView
run.view_list() -> list[GraphView]
run.view_show(name: str) -> GraphView
```

view の内容は `run.run_graph.reachable_from(view.root_node_id)` で read-time に算出します。

```python
run.run_graph.reachable_from(node_id: str) -> dict
# 返り値: {"node_ids": [...], "input_transition_ids": [...],
#           "output_transition_ids": [...], "payload_ids": [...]}
```

「view を統合する」場合は、統合先のノードから統合元の `root_node_id` への OutputTransition を通常の `plan` / `observe` で足すだけです。`view_merge` は廃止しました。

## Storage

```python
from optagent.storage import JsonlRunStore

store = JsonlRunStore("runs")
run.save(store)
loaded = store.load_run("demo")
```

保存されるファイル:

- `run.json`
- `graph.json`
- `views.jsonl`
- `nodes.jsonl`
- `input_transitions.jsonl`
- `output_transitions.jsonl`
- `payloads.jsonl`

0.1 alpha では旧 storage schema の読み込み互換はありません。
