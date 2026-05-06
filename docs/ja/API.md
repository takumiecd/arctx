# API

この文書は、optagent の現在の Python API を説明します。

optagent は、問題解決や最適化の過程を記録するためのライブラリです。
中心になる操作は、次の 2 つです。

- 未来を予測する: `PredictionDAG`
- 実際に起きたことを記録する: `TraceDAG`

ユーザーは `RunHandle` を通して、計画を作り、予測し、実行結果を記録し、履歴を辿ります。

## 最小例

```python
import optagent
from optagent import ActionResult, Requirement

requirement = Requirement(
    requirement_id="req_kernel",
    target_type="kernel",
    target_id="csc_linear",
)

run = optagent.init(requirement, run_id="demo")

plans = run.plan(state_id=run.current_observed_state_id)
predicted = run.predict(plan_id=plans[0].plan_id, max_outcomes=2)

result = ActionResult(
    result_id="r_0001",
    execution_plan_id=plans[0].plan_id,
    status="completed",
    raw_outputs=("raw/profile.txt",),
    metrics={"latency_ms": 1.5},
)

observed = run.promote(
    mode="transition",
    predicted_transition_id=predicted[0].transition_id,
    execution_plan_id=plans[0].plan_id,
    action_result=result,
)

history = run.trace()
```

この例では、実行前に予測を作り、実行後にその予測と実測結果を対応づけています。
予測と対応づけずに結果だけ記録したい場合は `run.observe(...)` を使います。

## 用語

### Requirement

run の目的です。
何を解きたいのか、何を最適化したいのかを表します。

### ObservedState

実際に観測された状態です。
`TraceDAG` に保存されます。

### PredictedState

まだ実行していない未来の状態です。
`PredictionDAG` に保存されます。

### ExecutionPlan

実行可能な計画です。
observed state から作られ、executor に渡せます。

### PredictionPlan

予測上の計画です。
predicted state から作られ、未来展開を考えるために使います。
そのまま executor には渡しません。
実行したい場合は `promote(mode="plan")` で `ExecutionPlan` に変換します。

### PredictedTransition

plan を実行した場合に起きそうな outcome です。
1 つの plan から複数作れます。

### ObservedTransition

実際に実行して得た結果です。
`ExecutionPlan` と `ActionResult` を結びます。
1 つの `ExecutionPlan` につき、原則 1 つだけ作ります。

### ActionResult

実行後に得られた事実です。
artifact、raw output、log、metric、error などを持ちます。

### DerivedRecord

事実から作った構造化メモです。
evidence、decision、finding、summary などを保存できます。
あとから作り直せる解釈なので、source of truth ではありません。

## `optagent.init`

```python
optagent.init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle
```

新しい run を作ります。

作られるもの:

- `TraceDAG` の root observed state: `s_obs_0000`
- `PredictionDAG` の root predicted state: `s_pred_0000`
- current observed state: `s_obs_0000`

`PredictionDAG` の root は current observed state に anchor されます。

```python
run = optagent.init(requirement, run_id="demo")

assert run.current_observed_state_id == "s_obs_0000"
```

## `run.plan`

```python
run.plan(
    state_id: str,
    *,
    planner: str | None = None,
    max_plans: int | None = None,
) -> list[ExecutionPlan | PredictionPlan]
```

指定した state から plan を作ります。

返る plan は、入力 state の種類で変わります。

- observed state から呼ぶと `ExecutionPlan`
- predicted state から呼ぶと `PredictionPlan`

```python
plans = run.plan(state_id=run.current_observed_state_id)
assert plans[0].plan_kind == "execution"

root_id = run.prediction_dag.root_predicted_state_id
future_plans = run.plan(state_id=root_id)
assert future_plans[0].plan_kind == "prediction"
```

現在の実装では、planner はまだ最小の placeholder です。
本格的な planner は domain や workflow 側で差し替える予定です。

## `run.predict`

```python
run.predict(
    plan_id: str,
    *,
    predictor: str | None = None,
    max_outcomes: int | None = None,
) -> list[PredictedTransition]
```

plan を実行した場合に起きそうな outcome を作り、`PredictionDAG` を展開します。

`ExecutionPlan` に対して呼ぶと、現在の observed state から見た次の未来を予測します。
`PredictionPlan` に対して呼ぶと、さらに先の未来を予測します。

1 つの plan から複数の outcome を作れます。

```python
predicted = run.predict(plans[0].plan_id, max_outcomes=3)
assert len(predicted) == 3
```

## `run.select_prediction`

```python
run.select_prediction(
    *,
    predicted_transition_id: str | None = None,
    predicted_transition_ids: list[str] | None = None,
    to_predicted_state_id: str | None = None,
    reason: str = "",
) -> PredictionSelection
```

複数の予測 outcome の中から、注目するものを選びます。

この関数は実行履歴を変更しません。
あとで `promote` するときに、どの予測を現実に対応させたのかを明示するために使います。

```python
selection = run.select_prediction(
    predicted_transition_id=predicted[0].transition_id,
    reason="small shape speedup is the most relevant outcome",
)
```

## `run.promote(mode="plan")`

```python
run.promote(
    *,
    mode="plan",
    prediction_plan_id: str | None = None,
    prediction_path: PredictionPath | None = None,
    observed_state_id: str | None = None,
) -> list[ExecutionPlan]
```

`PredictionDAG` 内の plan を、実行可能な `ExecutionPlan` に変換します。

`PredictionPlan` は予測上の計画なので、そのまま executor に渡しません。
実行したい場合は、現在または指定した observed state に接地して `ExecutionPlan` を作ります。

```python
promoted = run.promote(
    mode="plan",
    prediction_plan_id=future_plans[0].plan_id,
)

assert promoted[0].plan_kind == "execution"
```

複数 step の予測 path をまとめて実行計画にしたい場合は `PredictionPath` を渡します。

## `run.promote(mode="transition")`

```python
run.promote(
    *,
    mode="transition",
    predicted_transition_id: str,
    action_result: ActionResult,
    execution_plan_id: str | None = None,
    derived_records: list[DerivedRecord] | None = None,
) -> ObservedTransition
```

予測 outcome と実測結果を対応づけて、`TraceDAG` に `ObservedTransition` を追加します。

使う場面:

- 実行前に `run.predict(...)` していた
- 実行後に「どの予測 outcome に近かったか」を保存したい

```python
observed = run.promote(
    mode="transition",
    predicted_transition_id=predicted[0].transition_id,
    execution_plan_id=plans[0].plan_id,
    action_result=result,
)
```

`execution_plan_id` を省略した場合、対象の prediction plan から `ExecutionPlan` を作ってから記録します。

## `run.observe`

```python
run.observe(
    execution_plan_id: str,
    action_result: ActionResult,
    *,
    derived_records: list[DerivedRecord] | None = None,
) -> ObservedTransition
```

予測と対応づけずに、実行結果だけを `TraceDAG` に記録します。

使う場面:

- まず事実だけを保存したい
- 実行前に予測を作っていない
- 予測との対応は後で別の derived record として扱いたい

```python
observed = run.observe(
    execution_plan_id=plans[0].plan_id,
    action_result=result,
)
```

`run.result(...)` は `run.observe(...)` の alias です。

## `run.refresh`

```python
run.refresh(
    *,
    from_state_id: str | None = None,
    mode: str = "reset",
) -> PredictionDAG
```

`PredictionDAG` を observed state から作り直します。

実行結果を記録すると current observed state が進みます。
古い未来予測は現在の状態とズレるため、必要に応じて `refresh` します。

```python
run.refresh()

assert run.prediction_dag.anchor_observed_state_id == run.current_observed_state_id
```

## `run.trace`

```python
run.trace(
    state_id: str | None = None,
    *,
    depth: int | None = None,
    include_derived: bool = True,
    include_raw_refs: bool = True,
) -> TraceContext
```

observed state から過去の実行履歴を辿ります。

返るもの:

- 過去の state id
- observed transition id
- execution plan id
- action result id
- 対応した predicted transition id
- derived record id
- artifact / raw output / log の参照

```python
history = run.trace(depth=3)

print(history.observed_transition_ids)
print(history.artifact_refs)
```

`run.history(...)` は `run.trace(...)` の alias です。

## 不変条件

optagent の API は、次のルールを守ります。

- `PredictionPlan` は直接実行しない
- 実行する前に `ExecutionPlan` にする
- `ExecutionPlan` は `ActionResult` を持たない
- 実行結果は `ObservedTransition` に保存する
- `PredictedTransition` は実測結果を持たない
- 1 つの plan から複数の `PredictedTransition` を作れる
- 1 つの `ExecutionPlan` につき `ObservedTransition` は原則 1 つ
- `TraceDAG` は実際に起きたことの履歴として扱う

## 現在の実装範囲

現在の API は in-memory 実装です。

実装済み:

- run の作成
- plan の作成
- prediction の作成
- prediction の選択
- prediction plan の execution plan への変換
- action result の記録
- trace の取得
- prediction DAG の refresh

未実装または今後追加するもの:

- JSONL / run directory への永続化
- 実用的な planner / predictor
- executor との統合
- domain-specific workflow
- CLI command
