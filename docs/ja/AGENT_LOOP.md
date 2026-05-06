# 問題解決ループ

この文書は、optagent を使って問題解決や最適化のサイクルをどう回すかを説明します。

optagent は、AI agent そのものではありません。
人間、AI、script、executor が同じ文脈を共有するために、計画、予測、実行結果、メモを構造化して保存する基盤です。

## 基本サイクル

問題解決や最適化では、通常次の流れを繰り返します。

```text
調べる
  -> 仮説を立てる
  -> 実行する
  -> 結果を見る
  -> 理解を更新する
  -> 次の行動を決める
```

optagent では、この流れを次の API 操作に対応させます。

```text
current observed state
  -> plan
  -> predict
  -> execute outside optagent
  -> observe / promote
  -> trace
  -> refresh
```

## 1. current observed state を読む

run は常に current observed state を持ちます。

```python
state_id = run.current_observed_state_id
```

この state は、実際に観測された現在地です。
次の plan は、通常ここから作ります。

## 2. plan を作る

```python
plans = run.plan(state_id=run.current_observed_state_id)
```

observed state から作った plan は `ExecutionPlan` です。
これは executor に渡せる実行用の計画です。

predicted state から作った plan は `PredictionPlan` です。
これは未来予測を広げるための計画で、直接実行しません。

## 3. 予測する

```python
predicted = run.predict(plan_id=plans[0].plan_id, max_outcomes=3)
```

`predict` は、plan を実行した場合に起きそうな outcome を作ります。

1 つの plan に対して、複数の outcome を持てます。

```text
Plan
  ├── success
  ├── partial improvement
  └── regression
```

これにより、実行前に「うまくいく場合」「悪化する場合」「追加調査が必要な場合」を分けて考えられます。

## 4. 実行する

optagent は、現在の core では executor を内蔵していません。
実行は外部の script、test runner、benchmark runner、AI coding tool などが行います。

実行後、得られた結果を `ActionResult` として渡します。

```python
result = ActionResult(
    result_id="r_0001",
    execution_plan_id=plans[0].plan_id,
    status="completed",
    raw_outputs=("raw/bench.txt",),
    metrics={"latency_ms": 1.5},
)
```

## 5. 結果を記録する

予測と対応づけずに結果だけ記録する場合:

```python
observed = run.observe(
    execution_plan_id=plans[0].plan_id,
    action_result=result,
)
```

予測 outcome と実測結果を対応づける場合:

```python
observed = run.promote(
    mode="transition",
    predicted_transition_id=predicted[0].transition_id,
    execution_plan_id=plans[0].plan_id,
    action_result=result,
)
```

`observe` と `promote(mode="transition")` は、どちらも `TraceDAG` に `ObservedTransition` を追加します。
違いは、予測との対応を保存するかどうかです。

## 6. derived record を残す

実行結果から作った解釈や判断は `DerivedRecord` として保存します。

```python
derived = DerivedRecord(
    derived_id="d_0001",
    source_transition_id="t_obs_0001",
    derived_type="evidence",
    payload={
        "correctness": "passed",
        "speedup": 1.12,
    },
    generator="benchmark_parser",
)
```

derived record は、事実に対する構造化メモです。
後から作り直せるため、実行結果そのものとは分けて扱います。

## 7. 履歴を読む

```python
history = run.trace(depth=3)
```

`trace` は observed state から過去の実行履歴を辿ります。

取得できるもの:

- past state ids
- observed transition ids
- execution plan ids
- action result ids
- matched predicted transition ids
- derived record ids
- raw output / artifact / log refs

この履歴を使って、次の plan を作ります。

## 8. PredictionDAG を更新する

実行結果を記録すると、current observed state が進みます。
その時点で、古い未来予測は現在地とズレている可能性があります。

```python
run.refresh()
```

`refresh` は、current observed state に anchor された新しい `PredictionDAG` を作ります。

## ループの使い分け

### 調査フェーズ

原因がまだ分からない段階では、調査 plan を作ります。

```text
profile
inspect logs
run small benchmark matrix
compare baseline
```

この段階では、derived record として observation や summary が増えます。

### 実装フェーズ

方向性が見えたら、実装 plan を作ります。

```text
try scoped optimization
generate candidate patch
change dispatch rule
```

実装後は correctness、latency、regression などを derived record として残します。

### 検証フェーズ

採用前には、検証 plan を作ります。

```text
run full tests
run benchmark matrix
check numerical error
check regression by shape
```

この段階では、decision や finding が重要になります。

## optagent が保存したいもの

optagent が重視するのは、コードそのものよりも、問題解決の過程です。

保存したい問い:

- なぜその plan を選んだのか
- 何が起きると予測したのか
- 実際に何が起きたのか
- 予測と実測はどれくらい合っていたのか
- どの artifact や raw output が根拠なのか
- その結果から何を学んだのか
- 次に避けるべきことは何か

この情報が残っていると、人間も AI も後から同じ文脈を読み直せます。
