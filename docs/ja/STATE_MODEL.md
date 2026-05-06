# 状態モデル

この文書は、optagent が問題解決や最適化の過程をどう記録するかを説明します。

optagent の状態モデルは、予測と実測を分けます。

```text
PredictionDAG:
  まだ実行していない未来の候補。

TraceDAG:
  実際に起きたことの履歴。
```

この分離により、次の 2 つを同時に扱えます。

- 実行前に「何が起きそうか」を複数考える
- 実行後に「実際に何が起きたか」を事実として残す

## 全体像

```text
Requirement
  └── RunHandle
      ├── PredictionDAG
      │   ├── PredictedState
      │   ├── PredictionPlan
      │   └── PredictedTransition
      │
      └── TraceDAG
          ├── ObservedState
          ├── ExecutionPlan
          └── ObservedTransition
              ├── ActionResult
              └── DerivedRecord
```

`PredictionDAG` は未来の候補を持ちます。
`TraceDAG` は実際に起きたことを持ちます。

## State

State は、ある時点の状態です。

optagent には 2 種類の state があります。

```text
ObservedState:
  実際に観測された状態。
  TraceDAG に保存される。

PredictedState:
  予測上の状態。
  PredictionDAG に保存される。
```

state は、それ単体で過去や未来の遷移を全部持ちません。
過去を辿る index は `TraceDAG` が持ち、未来を辿る index は `PredictionDAG` が持ちます。

state が持つ中心情報は `StateSnapshot` です。

## StateSnapshot

`StateSnapshot` は、次の plan を考えるための作業文脈です。

含めるもの:

- requirement
- 現在参照している artifact
- これまでに得た finding の参照
- 未解決の問い
- active branch
- 予測の要約
- budget
- metadata

`StateSnapshot` は source of truth ではありません。
実行履歴から作った作業メモです。

重要な事実は `TraceDAG` の `ExecutionPlan`、`ActionResult`、`ObservedTransition` に残します。

## Plan

Plan は、ある state から何をするかを表します。

optagent には 2 種類の plan があります。

```text
PredictionPlan:
  predicted state から作る未来予測用の plan。
  そのまま実行しない。

ExecutionPlan:
  observed state に接地された実行用の plan。
  executor に渡せる。
```

`PredictionPlan` を実行したい場合は、`promote(mode="plan")` で `ExecutionPlan` に変換します。

## Transition

Transition は、state から state への変化です。

optagent には 2 種類の transition があります。

```text
PredictedTransition:
  plan を実行した場合に起きそうな outcome。
  PredictionDAG に保存される。

ObservedTransition:
  execution plan を実行して実際に得た outcome。
  TraceDAG に保存される。
```

1 つの plan から複数の `PredictedTransition` を作れます。

```text
PredictionPlan P
  ├── PredictedTransition: success
  ├── PredictedTransition: regression
  └── PredictedTransition: failure
```

一方、1 つの `ExecutionPlan` に対する実行結果は原則 1 つです。

```text
ExecutionPlan P
  └── ObservedTransition
      └── ActionResult
```

同じ操作をもう一度実行したい場合は、新しい `ExecutionPlan` を作ります。

## ActionResult

`ActionResult` は実行後に得られた事実です。

含めるもの:

- artifacts
- raw outputs
- logs
- metrics
- errors
- actual cost

`ActionResult` は `ObservedTransition` に保存されます。
予測側の `PredictedTransition` には保存しません。

## DerivedRecord

`DerivedRecord` は、事実から作った構造化メモです。

例:

- observation
- evidence
- prediction error
- decision
- finding
- summary

derived record は重要ですが、source of truth ではありません。
あとから別の evaluator、人間、LLM によって作り直せる解釈です。

source of truth と derived record を分けることで、あとから同じ実行結果を別の観点で再評価できます。

```text
source of truth:
  ExecutionPlan
  ActionResult
  ObservedTransition

derived records:
  Evidence
  Decision
  Finding
  Summary
```

## PredictionDAG

`PredictionDAG` は、現在の observed state から見た未来予測です。

役割:

- predicted state を保存する
- prediction plan を保存する
- predicted transition を保存する
- depth ごとに未来を辿れるようにする
- 1 plan に複数 outcome を持てるようにする

実行結果を記録して current observed state が進むと、古い `PredictionDAG` は現在とズレます。
その場合は `run.refresh()` で作り直します。

## TraceDAG

`TraceDAG` は、実際に起きたことの履歴です。

役割:

- observed state を保存する
- execution plan を保存する
- observed transition を保存する
- action result を保存する
- derived record を transition に紐づける
- 過去の履歴を辿れるようにする

`TraceDAG` は、optagent における source-of-truth の中心です。

## 予測と実測の対応

予測と実測を対応づけたい場合は、`promote(mode="transition")` を使います。

```text
PredictedTransition
  + ActionResult
  -> ObservedTransition
       matched_predicted_transition_id = ...
```

予測が完全に当たるとは限りません。
一致、部分一致、不一致などの評価は `PredictionMatch` や `DerivedRecord` として保存します。

## 基本ループ

```text
1. current observed state を見る
2. ExecutionPlan を作る
3. 必要なら predict で未来 outcome を作る
4. 外部 executor で ExecutionPlan を実行する
5. ActionResult を作る
6. observe または promote で TraceDAG に記録する
7. trace で履歴を読み、次の判断に使う
8. 必要なら refresh で PredictionDAG を作り直す
```

このループにより、問題解決の過程を「何を考え、何を実行し、何が起きたか」として保存できます。
