# API 仕様ドラフト

## 目的

optagent の API は、問題解決や最適化の過程を **予測と実測を分けた状態遷移** として扱い、
あとから再解釈できる形で保存するためのものです。

中心にあるのは、次の 2 つの DAG です。

```text
PredictionDAG:
  まだ実行していない未来予測。

TraceDAG:
  実際に起きた実行履歴。
  source-of-truth facts を保存する。
```

`PredictionDAG` は current observed state から見た未来展開です。
`TraceDAG` は、実際に実行した plan と result の履歴です。

## 基本方針

### ActionSpec は作らない

`ActionSpec` という独立 object は作りません。

実行内容は plan の本体です。
`Plan` と `ActionSpec` を分けると、どちらが action の意図、入力、期待観測を持つのかが重なりやすくなります。

```text
Plan:
  どの state から、何を、どの意図で、どの入力で行うか。
```

したがって、`action_type`、`intent`、`inputs`、`expected_observation`、
`estimated_cost`、`safety_policy` などは plan に直接持たせます。

### Plan は 2 種類に分ける

Plan は context を混ぜないために 2 種類に分けます。

```text
PredictionPlan:
  PredictionDAG 内で作られる仮説上の plan。
  そのまま実行しない。

ExecutionPlan:
  TraceDAG / current observed state に接地された実行用 plan。
  executor に渡して ActionResult を受け取れる。
```

`PredictionPlan` を実行したい場合は、PredictionDAG の selected path / selected transition を明示して、
`ExecutionPlan` に promote します。

### Transition も 2 種類に分ける

```text
PredictedTransition:
  Plan を実行した場合に起きるかもしれない outcome。
  1 つの plan から複数作られてよい。

ObservedTransition:
  ExecutionPlan を実際に実行して得た result。
  1 つの ExecutionPlan につき、原則 1 つだけ作る。
```

prediction 側では 1 plan から複数 outcome が出ます。
trace 側では 1 execution plan の実行結果は 1 つです。

```text
Prediction:
  Plan P
    ├── PredictedTransition T_pred_a
    ├── PredictedTransition T_pred_b
    └── PredictedTransition T_pred_c

Trace:
  ExecutionPlan P_exec
    └── ObservedTransition T_obs
          matched_predicted_transition_id = T_pred_b
```

## 最小 API

初期 API は以下です。

```text
init
plan
predict
select_prediction
promote
observe/result
refresh
trace/history
```

補助 API として以下を持てます。

```text
prune
select
explain
search_findings
```

## init

新しい run を開始し、初期状態、TraceDAG、PredictionDAG を作ります。

```python
init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle
```

初期状態:

```text
TraceDAG:
  S_obs_0000

PredictionDAG:
  S_pred_root_0000
    anchor_observed_state_id = S_obs_0000
    snapshot_hash == S_obs_0000.snapshot_hash

current = S_obs_0000
```

## plan

指定した state から plan を作ります。

```python
plan(
    state_id: str,
    *,
    planner: str | None = None,
    max_plans: int | None = None,
) -> list[ExecutionPlan | PredictionPlan]
```

入力 state の種類によって生成される plan の種類が変わります。

```text
plan(ObservedState)  -> ExecutionPlan
plan(PredictedState) -> PredictionPlan
```

`ExecutionPlan` は実行可能です。
`PredictionPlan` は PredictionDAG 内でだけ有効です。

```text
ExecutionPlan
├── plan_id
├── plan_kind = execution
├── from_observed_state_id
├── action_type
├── intent
├── inputs
├── expected_observation
├── expected_state_delta
├── estimated_cost
├── safety_policy
├── assumptions
├── status
└── metadata
```

```text
PredictionPlan
├── plan_id
├── plan_kind = prediction
├── from_predicted_state_id
├── action_type
├── intent
├── inputs
├── expected_observation
├── expected_state_delta
├── estimated_cost
├── safety_policy
├── assumptions
├── confidence
├── status
└── metadata
```

## predict

plan を実行した場合に何が起きそうかを予測し、PredictionDAG を展開します。

```python
predict(
    plan_id: str,
    *,
    predictor: str | None = None,
    max_outcomes: int | None = None,
) -> list[PredictedTransition]
```

`predict` は `ExecutionPlan` にも `PredictionPlan` にも使えます。

`ExecutionPlan` に対する predict は、current observed state から見た depth 1 の未来予測です。
`PredictionPlan` に対する predict は、PredictionDAG 内のさらに先の未来予測です。

```text
PredictedTransition
├── transition_id
├── parent_plan_id
├── parent_plan_kind
├── from_state_id
├── outcome_id
├── outcome_label
├── predicted_result
├── predicted_state_delta
├── to_predicted_state_id
├── confidence
├── assumptions
└── metadata
```

## select_prediction

複数の predicted transitions の中から、現実に対応させる outcome を選びます。

```python
select_prediction(
    *,
    predicted_transition_id: str | None = None,
    predicted_transition_ids: list[str] | None = None,
    to_predicted_state_id: str | None = None,
) -> PredictionSelection
```

```text
PredictionSelection
├── selection_id
├── selected_transition_ids
├── selected_path_id | None
├── reason
└── metadata
```

単発なら `selected_transition_ids` は 1 つです。
複数 step を promote する場合は、path として複数 transition を持ちます。

## promote

PredictionDAG の指定範囲を、TraceDAG 側に反映できる形にします。

`promote` は prediction を無条件に事実扱いする操作ではありません。

```text
plan mode:
  PredictionPlan / prediction path を ExecutionPlan として trace 側に接地する。

transition mode:
  selected PredictedTransition + ActionResult を ObservedTransition として trace に記録する。
```

### promote plan/range

PredictionDAG 内の selected path / selected range に含まれる `PredictionPlan` を、
current observed state 側に接地された `ExecutionPlan` として作り直します。

```python
promote(
    *,
    mode: Literal["plan"],
    prediction_plan_id: str | None = None,
    prediction_path: PredictionPath | None = None,
    observed_state_id: str | None = None,
) -> list[ExecutionPlan]
```

```text
PredictionPlan + compatible ObservedState
  -> ExecutionPlan
```

複数 step の prediction path を指定した場合、path 上の `PredictionPlan` 群を
`ExecutionPlan` 群に変換します。

### promote transition

selected `PredictedTransition` と実際の `ActionResult` を対応づけて、
`ObservedTransition` を作ります。

```python
promote(
    *,
    mode: Literal["transition"],
    predicted_transition_id: str,
    action_result: ActionResult,
    execution_plan_id: str | None = None,
    derived_records: list[DerivedRecord] | None = None,
) -> ObservedTransition
```

```text
PredictedTransition T_pred_b + ActionResult
  -> ObservedTransition T_obs
       matched_predicted_transition_id = T_pred_b
```

`execution_plan_id` が指定されない場合は、元の prediction plan から compatible な
`ExecutionPlan` を作ってから `ObservedTransition` を作ります。

## observe / result

予測対応なしで、`ExecutionPlan` の実行結果を TraceDAG に記録します。

```python
observe(
    execution_plan_id: str,
    action_result: ActionResult,
    *,
    derived_records: list[DerivedRecord] | None = None,
) -> ObservedTransition
```

`observe` は `ExecutionPlan` だけを受け付けます。
`PredictionPlan` は observe できません。

```text
ExecutionPlan + ActionResult -> ObservedTransition
```

prediction と対応づけたい場合は、`promote(mode="transition")` を使います。

重要ルール:

```text
1 つの ExecutionPlan につき ObservedTransition は原則 1 つ。
同じ操作を再実行したい場合は、新しい ExecutionPlan を作る。
```

## refresh

PredictionDAG を current observed state から作り直します。

```python
refresh(
    *,
    from_state_id: str | None = None,
    mode: str = "reset",
) -> PredictionDAG
```

refresh 後の PredictionDAG root は、必ず current observed state に anchor されます。

```text
PredictionDAG.root.anchor_observed_state_id == current_observed_state_id
PredictionDAG.root.snapshot_hash == current_observed_state.snapshot_hash
```

古い PredictionDAG は削除してもよいですが、保存する場合は `stale` と明示します。

## trace / history

現在または指定した observed state から、過去の observed transitions を辿ります。

```python
trace(
    state_id: str | None = None,
    *,
    depth: int | None = None,
    include_derived: bool = True,
    include_raw_refs: bool = True,
) -> TraceContext
```

```text
TraceContext
├── current_state_id
├── past_state_ids
├── observed_transition_ids
├── execution_plan_ids
├── action_result_ids
├── matched_predicted_transition_ids
├── derived_record_ids
├── artifact_refs
└── metadata
```

## データモデル

```python
StateKind = Literal["observed", "predicted"]
PlanKind = Literal["execution", "prediction"]
TransitionKind = Literal["observed", "predicted"]
```

### PredictionPlan

```python
@dataclass(frozen=True)
class PredictionPlan:
    plan_id: str
    plan_kind: Literal["prediction"]
    from_predicted_state_id: str
    action_type: str
    intent: str
    inputs: dict[str, JSONValue]
    expected_observation: dict[str, JSONValue] = field(default_factory=dict)
    expected_state_delta: dict[str, JSONValue] = field(default_factory=dict)
    estimated_cost: dict[str, JSONValue] = field(default_factory=dict)
    safety_policy: dict[str, JSONValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    confidence: float | None = None
    status: str = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)
```

### ExecutionPlan

```python
@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    plan_kind: Literal["execution"]
    from_observed_state_id: str
    action_type: str
    intent: str
    inputs: dict[str, JSONValue]
    expected_observation: dict[str, JSONValue] = field(default_factory=dict)
    expected_state_delta: dict[str, JSONValue] = field(default_factory=dict)
    estimated_cost: dict[str, JSONValue] = field(default_factory=dict)
    safety_policy: dict[str, JSONValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    status: str = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)
```

### PredictedTransition

```python
@dataclass(frozen=True)
class PredictedTransition:
    transition_id: str
    transition_kind: Literal["predicted"]
    parent_plan_id: str
    parent_plan_kind: PlanKind
    from_state_id: str
    outcome_id: str
    outcome_label: str
    predicted_result: dict[str, JSONValue]
    predicted_state_delta: dict[str, JSONValue]
    to_predicted_state_id: str
    confidence: float | None = None
    assumptions: tuple[str, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)
```

### ObservedTransition

```python
@dataclass(frozen=True)
class ObservedTransition:
    transition_id: str
    transition_kind: Literal["observed"]
    execution_plan_id: str
    from_observed_state_id: str
    to_observed_state_id: str
    action_result: ActionResult
    matched_predicted_transition_id: str | None = None
    prediction_match: PredictionMatch | None = None
    derived_records: tuple[DerivedRecord, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)
```

### PredictionPath / PredictionStepRef

```python
@dataclass(frozen=True)
class PredictionPath:
    path_id: str
    anchor_observed_state_id: str
    steps: tuple[PredictionStepRef, ...]
    metadata: dict[str, JSONValue] = field(default_factory=dict)


@dataclass(frozen=True)
class PredictionStepRef:
    prediction_plan_id: str
    selected_predicted_transition_id: str
    from_predicted_state_id: str
    to_predicted_state_id: str
```

### PredictionMatch

```python
@dataclass(frozen=True)
class PredictionMatch:
    matched_predicted_transition_id: str
    match_status: Literal["exact", "compatible", "partial", "mismatch"]
    prediction_error: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)
```

## 不変条件

### Plan

```text
1. ActionSpec は作らない。
2. Plan 自体が action_type / intent / inputs を持つ。
3. PredictionPlan は PredictedState からしか作らない。
4. ExecutionPlan は ObservedState からしか作らない。
5. PredictionPlan は直接 observe できない。
6. PredictionPlan を実行したい場合は promote(mode="plan") で ExecutionPlan を作る。
7. ExecutionPlan は ActionResult を持たない。
8. observe には ExecutionPlan と ActionResult が必須である。
```

### Transition

```text
1. PredictedTransition は ActionResult を持たない。
2. PredictedTransition は 1 plan から複数作られてよい。
3. ObservedTransition は ActionResult を必ず持つ。
4. ObservedTransition は 1 ExecutionPlan につき原則 1 つ。
5. PredictedTransition を ObservedTransition に対応づける場合は matched_predicted_transition_id を必ず保存する。
6. どの predicted outcome を採用したかは selected_predicted_transition_id / matched_predicted_transition_id で明示する。
```

### promote

```text
1. promote は PredictionDAG の指定範囲を TraceDAG に反映するための操作である。
2. PredictionPlan を trace 側に移す場合は、新しい ExecutionPlan を作る。
3. PredictedTransition を trace 側に移す場合は、必ず ActionResult が必要である。
4. 1 plan に複数 predicted transitions がある場合、どれを採用するかを必ず selected_predicted_transition_id で指定する。
5. path を promote する場合、各 step は prediction_plan_id と selected_predicted_transition_id のペアを持つ。
```

## 推奨 ID prefix

```text
ObservedState:       s_obs_0001
PredictedState:      s_pred_0001
ExecutionPlan:       p_exec_0001
PredictionPlan:      p_pred_0001
ObservedTransition:  t_obs_0001
PredictedTransition: t_pred_0001
PredictionPath:      path_pred_0001
PredictionSelection: sel_pred_0001
DerivedRecord:       d_0001
Finding:             f_0001
```

## 基本ループ

### 実測を伴う最小ループ

```python
run = optagent.init(requirement)

plans = run.plan(state_id=run.current_observed_state_id)

predicted = run.predict(plan_id=plans[0].plan_id)

actual_result = executor.execute(plans[0])

observed = run.promote(
    mode="transition",
    predicted_transition_id=predicted[0].transition_id,
    action_result=actual_result,
    execution_plan_id=plans[0].plan_id,
)

run.refresh()
```

### prediction path を promote する場合

```python
path = PredictionPath(
    path_id="path_pred_0001",
    anchor_observed_state_id=run.current_observed_state_id,
    steps=(
        PredictionStepRef(
            prediction_plan_id="p_pred_0001",
            selected_predicted_transition_id="t_pred_0001b",
            from_predicted_state_id="s_pred_0001",
            to_predicted_state_id="s_pred_0002",
        ),
    ),
)

execution_plans = run.promote(
    mode="plan",
    prediction_path=path,
    observed_state_id=run.current_observed_state_id,
)
```
