# optagent

optagent は、問題解決や最適化の過程を構造化して保存するための Python ライブラリです。

最終的なコードや結果だけでなく、途中で何を計画し、何が起きると予測し、実際に何が起き、そこから何を学んだかを残すことを目的にしています。

基本的な考え方は次の通りです。

```text
何をするかを計画する
何が起きそうかを予測する
optagent の外で実行する
実際に起きたことを記録する
結果から作ったメモを紐づける
```

## 中心モデル

optagent は、予測と実測を分けて保存します。

```text
PredictionDAG:
  まだ実行していない未来の候補。

TraceDAG:
  実際に起きたことの履歴。
```

これにより、実行前に複数の未来を考え、実行後にどの予測に近かったかを保存できます。

## 向いている用途

- コード最適化
- カーネル最適化
- benchmark を伴う開発
- 実験ログの整理
- AI coding tool と人間が同じ文脈を共有する作業

## 現在の状態

現在は、`PredictionDAG` / `TraceDAG` を中心にした新しい API を実装している段階です。

実装済み:

- in-memory run API
- CLI (`init`, `plan`, `predict`, `observe`, `promote`, `trace`, `refresh`, `show`, `list`)
- `init`
- `plan`
- `predict`
- `select_prediction`
- `promote`
- `observe` / `result`
- `refresh`
- `trace` / `history`
- run directory / JSONL への保存と読み込み

未実装:

- 実用的な planner / predictor
- executor / evaluator 連携
- code / kernel optimization workflow

## Quick Start

```python
import optagent
from optagent import ActionResult, Requirement
from optagent.storage import JsonlRunStore

requirement = Requirement(
    requirement_id="req_kernel",
    target_type="kernel",
    target_id="csc_linear",
)

run = optagent.init(requirement, run_id="demo")

plans = run.plan(from_state_id="s_obs_0000")
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

history = run.trace(state_id=observed.to_observed_state_id)

store = JsonlRunStore("runs")
run.save(store)
loaded = store.load_run("demo")
```

### CLI Quick Start

```bash
export PYTHONPATH=src

# 1. Initialize a run
python3 -m optagent.cli.main init req_kernel --target-type kernel --target-id csc_linear --run-id demo

# 2. Create a plan
python3 -m optagent.cli.main plan --run demo --from-state s_obs_0000 --planner default --max-plans 1

# 3. Predict outcomes
python3 -m optagent.cli.main predict --run demo p_exec_0001 --max-outcomes 2

# 4. Record observation
python3 -m optagent.cli.main observe --run demo --plan p_exec_0001 \
  --result-id r_0001 --status completed \
  --metric latency_ms=1.5

# 5. Show details
python3 -m optagent.cli.main show --run demo

# 6. Trace history
python3 -m optagent.cli.main trace --run demo --from-state s_obs_0001

# 7. Refresh prediction DAG
python3 -m optagent.cli.main refresh --run demo --from-state s_obs_0001

# 8. List all runs
python3 -m optagent.cli.main list
```

See `examples/basic_cli_loop.sh` for a complete working example.

## 主な用語

`Requirement` は run の目的です。

`ExecutionPlan` は observed state から作る実行用の計画です。

`PredictionPlan` は `PredictionDAG` 内で使う未来予測用の計画です。

`PredictedTransition` は実行前に考えた outcome です。

`ObservedTransition` は実行後に実際に起きた outcome です。

`ActionResult` は artifact、raw output、log、metric、error などの実行結果です。

`DerivedRecord` は evidence、decision、finding、summary など、実行結果から作った構造化メモです。

## ドキュメント

- [プロジェクトの方向性](docs/ja/DIRECTION.md)
- [API](docs/ja/API.md)
- [状態モデル](docs/ja/STATE_MODEL.md)
- [問題解決ループ](docs/ja/AGENT_LOOP.md)

## ディレクトリ構成

```text
src/optagent
├── cli/        # CLI commands
├── core/       # public model と in-memory run API
├── workflows/  # workflow layer。まだ初期段階
├── domains/    # domain plugin。まだ初期段階
├── execution/  # executor / evaluator interface。まだ初期段階
├── search/     # search policy。まだ初期段階
└── storage/    # run directory / JSONL storage
```

public API は `optagent` と `optagent.core` にあります。

## 開発

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q
```

## License

MIT
