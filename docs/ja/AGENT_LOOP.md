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

- past node ids
- note payload ids
- input transition ids
- output transition ids
- plan payload ids
- prediction payload ids
- result payload ids
- artifact / raw output / log refs

## 7. GraphView で探索する

長い仮説展開や隔離した探索をしたい場合は `GraphView` を作ります。record の実体は `RunGraph` にあります。

```python
view = run.view_create("exp-a", root_node_ids=[observed.to_node_id])
future_input = run.plan(
    [observed.to_node_id],
    PlanPayload(payload_id="pending", target_id="pending", intent="try variant"),
    view=view.view_id,
)
run.predict(future_input.input_transition_id, view=view.view_id, max_outcomes=3)
```

採用したい path は view merge で main の membership に追加します。record はコピーしません。

```python
run.view_merge("exp-a", into="main")
```

## Rewind

間違った plan を無効化したい場合は input transition を cut します。

```python
run.rewind(
    input_transition.input_transition_id,
    target_kind="input_transition",
    reason="bad plan",
)
```

予測や実測 output だけを無効化したい場合は output transition を cut します。

```python
run.rewind(
    predicted[0].output_transition_id,
    target_kind="output_transition",
    reason="bad prediction",
)
```

rewind は削除ではありません。`CutPayload` を append し、active / inactive は read-time に計算します。
