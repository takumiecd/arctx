# ワークフロー詳細

## 1回の最適化で何が起こるのか

optagent で1回の最適化（`ManagerAgent.optimize()` を1回呼ぶ）で行われる処理を、ステップバイステップで解説します。

### Step 0: 準備（ユーザー側）

ユーザーは以下を準備します：

```python
from optagent import ManagerAgent, Requirement

# 1. 最適化対象の指定
requirement = Requirement(
    target_type="kernel",                    # 最適化の種類
    target_id="csc_linear_forward",          # 具体的な対象
    parameters={                             # パラメータ
        "device": "cuda",
        "in_features": 1024,
        "out_features": 1024,
    },
    objective={                              # 目標
        "metric": "latency_ms",
        "direction": "minimize",
    },
)

# 2. エージェントの構成
agent = ManagerAgent(work_dir="./runs/csc_linear_forward")

# 3. 1 round 実行
state = agent.optimize(requirement)
```

補足: `KernelOptimizationStrategy`, `OpenCodeBackend`, `MultiSizeEvaluator` は
v1 component として存在しますが、トップレベル API ではなく
`optagent.v1.*` から直接 import します。現在の最小 workflow は
file protocol と default mock path で動き、Evidence Graph を run directory に保存します。

### Step 1: INITIALIZE（初期化）

ManagerAgent が Strategy を初期化します。

```python
def _hook_initialize(context):
    state = context["state"]
    strategy.initialize(state)
    # → strategyがstateに初期メタデータを設定
```

**何が起こるのか**:
- Strategy が状態を確認
- 必要なリソースが利用可能かチェック
- ワークディレクトリの準備

**例**: `KernelOptimizationStrategy` の場合
- サポートされているフォーマットの一覧を state.metadata に記録
- カーネルレジストリへの接続確認

### Step 2: ANALYZE_TARGET（対象分析）

最適化対象を分析し、ベースラインを取得します。

```python
def _hook_analyze(context):
    analysis = strategy.analyze(state.requirement)
    # → 対象の特性、最適化の余地、ベースライン情報
```

**何が起こるのか**:
- Requirement の内容を解析
- 現在の実装（ベースライン）の性能を把握
- ボトルネックの特定

**例**: CSC linear_forward の場合
- 現在の実装が `CSCLinearForwardCPU` であることを特定
- 小バッチでのレイテンシを測定 → 10ms
- メモリアクセスパターンを分析 → 非連続アクセスが多い

### Step 3: PROPOSE_HYPOTHESES（仮説生成）

Backend（LLM）が最適化仮説を生成します。

```python
def _hook_propose(context):
    hypotheses = backend.propose_hypotheses(state, analysis)
    # → 仮説のリスト
```

**何が起こるのか**:
- Backend に対象情報と分析結果を渡す
- LLM が仮説を自然言語で生成
- 複数の仮説が生成されることもある

**例**:
```
仮説1: "Pythonループのオーバーヘッドが支配的。Cython化で改善"
仮説2: "メモリアクセスが非連続。並列入れ替えで改善"
仮説3: "スパースパターンが規則的。専用データ構造で改善"
```

### Step 4: GENERATE_ARTIFACTS（アーティファクト生成）

各仮説に対して、Backend が具体的なアーティファクト（コード等）を生成します。

```python
def _hook_generate(context):
    for hypothesis in hypotheses:
        artifact = backend.generate_artifact(hypothesis, state)
        # → 最適化コード、設定変更、 etc.
```

**何が起こるのか**:
- 仮説に基づいて LLM がコードを生成
- プロンプトに API ドキュメントを注入（重要！）
- 生成物をファイルとして保存

**例**:
```python
# 生成されたアーティファクト
class CSCLinearForwardOpt(KernelSpec):
    name = "csc_linear_forward_opt"
    base_rank = 20
    
    def launch(self, adapter, x, ...):
        # 最適化実装
        ...
```

### Step 5: EVALUATE_ARTIFACTS（評価）

Evaluator が各アーティファクトを評価します。

```python
def _hook_evaluate(context):
    for artifact in artifacts:
        evidence = evaluator.evaluate(artifact, state)
        # → 性能測定、正確性チェック
```

**何が起こるのか**:
- 複数サイズでのベンチマーク実行
- 正確性の検証（数値比較）
- 速度向上率の計算

**例**:
```
Size: small (batch=1)
  Baseline: 10ms, Candidate: 8ms → Speedup: 1.25x
  
Size: medium (batch=16)
  Baseline: 50ms, Candidate: 30ms → Speedup: 1.67x
  
Size: large (batch=64)
  Baseline: 200ms, Candidate: 180ms → Speedup: 1.11x
  
Geometric mean: 1.32x
Correctness: PASSED
```

### Step 6: VALIDATE_RESULTS（結果検証）

評価結果を検証します。

```python
def _hook_validate(context):
    for evidence in evidence_list:
        if config.require_correctness and not evidence.is_correct:
            # 正確性失敗 → 拒否
```

**検証項目**:
- ✅ 正確性: 数値結果が一致するか
- ✅ 適格性: 対象条件で実行可能か
- ✅ 安定性: 複数回実行で同じ結果か

**拒否理由の例**:
- "数値誤差が大きすぎる（相対誤差 1e-3 > 閾値 1e-5）"
- "大きいサイズでセグメンテーション違反"

### Step 7: MAKE_DECISION（意思決定）

最終決定を行います。

```python
def _hook_decide(context):
    # ベストの速度向上率を確認
    if best_speedup >= target_speedup:
        decision = Decision(accepted=True, ...)
    else:
        decision = Decision(accepted=False, ...)
```

**決定の種類**:

| 決定 | 意味 | 次のアクション |
|------|------|--------------|
| **accepted** | 承認 | 実験ログ記録後、本番適用の検討 |
| **rejected** | 拒否 | 実験ログ記録。知見として残す |
| **inconclusive** | 決定不能 | より良い実験設計が必要 |
| **needs_narrower_scope** | 部分的 | 適用範囲を絞って再試行 |

**例**:
```
Decision: accepted
Reason: "Geometric mean speedup 1.32x exceeds target 1.20x. 
        All sizes show improvement. Correctness verified."
Promoted: ["csc_linear_forward_opt"]
```

### Step 8: FINALIZE（最終処理）

結果を記録し、必要に応じて適用します。

```python
def _hook_finalize(context):
    if decision.accepted and config.allow_promotion:
        strategy.apply_changes(state)
```

**何が起こるのか**:
- 状態をJSONとして保存
- 実験ログの生成
- findings の更新
- (オプション) 本番への適用

**保存されるファイル**:
```
work_dir/
  state_round_1.json          # 完全な状態
  experiment_log.md           # 人間が読める実験ログ
  generated_code.py           # 生成されたコード
```

## 状態遷移図

```
[INITIAL]
   ↓
[ANALYZE] ──(分析結果)──→ 保存
   ↓
[PROPOSE] ──(仮説リスト)──→ 保存
   ↓
[GENERATE] ──(アーティファクト)──→ 保存
   ↓
[EVALUATE] ──(証拠リスト)──→ 保存
   ↓
[VALIDATE] ──(検証結果)──→ 保存
   ↓
[DECIDE]
   ↓
┌──────────┬──────────┐
↓          ↓          ↓
[ACCEPTED] [REJECTED] [INCONCLUSIVE]
   ↓          ↓          ↓
[FINALIZE] [FINALIZE] [FINALIZE]
   ↓          ↓          ↓
(適用)    (記録のみ)  (再試行準備)
```

## 複数ラウンドの最適化

1回の `optimize()` で1ラウンド。複数回呼ぶことで反復改善が可能です。

```python
state = None
for i in range(config.max_rounds):
    state = agent.optimize(requirement, state=state)
    
    if state.decisions[-1].accepted:
        print(f"Round {i+1}: Accepted!")
        break
    else:
        print(f"Round {i+1}: {state.decisions[-1].reason}")
```

**ラウンド間で引き継がれるもの**:
- 前回の仮説・実験結果
- 最適化の試行歴史
- 設定の調整

## エラーハンドリング

各ステップでエラーが発生した場合：

```python
try:
    context = self.workflow.execute_step(step, context)
except Exception as e:
    # エラーを記録
    state.metadata["error"] = str(e)
    # 可能な限り継続
    continue
finally:
    # 必ず状態を保存
    self._save_state(state)
```

**エラーの種類と対処**:

| 発生箇所 | エラー例 | 対処 |
|---------|---------|------|
| PROPOSE | LLM応答なし | タイムアウト、フォールバック |
| GENERATE | 無効なコード | 構文エラーチェック、再生成 |
| EVALUATE | 実行時エラー | 記録、次の候補へ |
| VALIDATE | 正確性失敗 | 拒否決定 |

## ログの見方

```
[Round 1] Optimizing: csc_linear_forward
  [Step 1/8] INITIALIZE ✓
  [Step 2/8] ANALYZE ✓
    Baseline: 10ms (small), 50ms (medium), 200ms (large)
  [Step 3/8] PROPOSE ✓
    Generated 1 hypothesis: "loop fusion"
  [Step 4/8] GENERATE ✓
    Generated 1 artifact
  [Step 5/8] EVALUATE ✓
    small: 1.25x, medium: 1.67x, large: 1.11x
    Geometric mean: 1.32x
  [Step 6/8] VALIDATE ✓
    Correctness: PASSED
  [Step 7/8] DECIDE ✓
    Decision: ACCEPTED (speedup 1.32x >= target 1.20x)
  [Step 8/8] FINALIZE ✓
    State saved to: ./optagent/state_round_1.json
```
