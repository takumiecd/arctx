# 問題解決ループ

optagent は agent そのものではありません。人間、AI、script、executor が同じ文脈を共有するために、計画、予測、実行結果を構造化して保存する基盤です。

## 基本サイクル

```text
input node を選ぶ
  -> 必要なら NotePayload を node に残す
  -> InputTransition + PlanPayload を作る
  -> 必要なら prediction output と PredictionPayload を作る
  -> optagent の外で実行する
  -> observed output と ResultPayload で結果を保存する
  -> trace で履歴を読む
  -> 必要なら GraphView を作って隔離した探索をする
```

## 1. input node を選ぶ

core は mutable な current pointer を持ちません。caller が input node を明示します。

```python
input_node_ids = [run.root_node_id]
```

## 2. plan を作る

plan 情報は graph record ではなく `PlanPayload` です。`run.plan(...)` は `InputTransition` を作り、そこに `PlanPayload` を attach します。

```python
input_transition = run.plan(
    input_node_ids,
    PlanPayload(
        payload_id="pending",
        target_id="pending",
        intent="run benchmark",
    ),
)
```

必要なら node に軽いメモを残せます。

```python
run.note(run.root_node_id, "baseline context looks clean", tags=["context"])
```

## 3. 予測する

予測は `OutputTransition` と `PredictionPayload` として記録します。

```python
predicted = run.predict(input_transition.input_transition_id, max_outcomes=3)
```

1 つの input transition から複数の prediction output を作れます。

## 4. 実行する

optagent は executor を内蔵しません。外部の script、test runner、benchmark runner、AI coding tool が実行します。

実行後、結果を `ResultPayload` として渡します。

```python
result = ResultPayload(
    payload_id="pending",
    target_id="pending",
    status="completed",
    raw_outputs=("raw/bench.txt",),
    metrics={"latency_ms": 1.5},
    matched_prediction_output_id=predicted[0].output_transition_id,
)
```

## 5. 結果を記録する

```python
observed = run.observe(input_transition.input_transition_id, result)
```

`observe` は observed output の `OutputTransition` を追加し、そこに `ResultPayload` を attach します。

## 6. 履歴を読む

```python
history = run.trace(observed.to_node_id, depth=3)
```

取得できるもの:

- `current_node_id`
- `past_node_ids`
- `output_transition_ids`
- `input_transition_ids`
- `result_payload_ids`
- `prediction_output_transition_ids`（`include_predictions=True` の場合のみ収集）
- `note_payload_ids`
- `artifact_refs`（artifacts / raw_outputs / logs の参照）

## 7. GraphView で探索する

長い仮説展開や隔離した探索をしたい場合は `GraphView` を作ります。view の内容は `root_node_id` からの reachability で read-time に算出します。

```python
view = run.view_create("exp-a", root_node_id=observed.to_node_id)
future_input = run.plan(
    [observed.to_node_id],
    PlanPayload(payload_id="pending", target_id="pending", intent="try variant"),
)
run.predict(future_input.input_transition_id, max_outcomes=3)
```

探索結果を main に統合したい場合は、main 内のノードから `exp-a` の `root_node_id` への OutputTransition を `plan` / `observe` で足します。`view_merge` は不要です。

## Cut

間違った plan を無効化したい場合は input transition を cut します。

```python
run.cut(
    input_transition.input_transition_id,
    target_kind="input_transition",
    reason="bad plan",
)
```

予測や実測 output だけを無効化したい場合は output transition を cut します。

```python
run.cut(
    predicted[0].output_transition_id,
    target_kind="output_transition",
    reason="bad prediction",
)
```

cut は削除ではありません。`CutPayload` を append し、active / inactive は read-time に計算します。
