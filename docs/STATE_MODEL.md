# 状態モデル仕様書

## 概要

本ドキュメントは、`kernel_optimizer_architecture.md` で定義された状態モデルを `optagent` に実装したものです。

## 状態の定義

### アルゴリズム状態: X_t = (R, H_<t, C_<t)

| 要素 | 型 | 意味 | 不変性 |
|------|-----|------|--------|
| **R** | `Requirements` | 最適化要求 | ✅ 固定（immutable） |
| **H** | `List[Hypothesis]` | 生成された仮説 | ❌ 追加のみ |
| **C** | `List[EvidenceRecord]` | 観測された証拠 | ❌ 追加のみ |

### ランタイム状態: S_t = (Q_t, A_t, D_t)

| 要素 | 型 | 意味 |
|------|-----|------|
| **Q** | `List[WorkItem]` | 待ち行列にある作業 |
| **A** | `List[WorkItem]` | 実行中の作業 |
| **D** | `List[WorkItem]` | 完了した作業 |

## 状態遷移

### 遷移関数

```text
H_t = propose(R, H_<t, C_<t)      # 仮説生成
B_t = materialize(H_t)             # アーティファクト生成
C_t = evaluate(B_t, R)             # 評価
D_t = decide(C_t, R)               # 意思決定

X_{t+1} = (R, H_≤t, C_≤t)         # 状態更新
```

### Python実装

```python
class OptimizerState:
    """X_t = (R, H_<t, C_<t)"""
    algorithm: AlgorithmState   # (R, H, C)
    runtime: RuntimeState       # (Q, A, D)
    
    def advance(self, new_H, new_C):
        """X_t → X_{t+1}"""
        return OptimizerState(
            algorithm=AlgorithmState(
                requirements=self.algorithm.requirements,  # R は不変
                hypotheses=self.algorithm.hypotheses + new_H,
                evidence=self.algorithm.evidence + new_C,
                round_index=self.algorithm.round_index + 1,
            ),
            runtime=RuntimeState(),  # 新しいラウンドでリセット
        )
```

## Requirements (R)

最適化要求。一度作成したら変更不可。

```python
@dataclass(frozen=True)
class Requirements:
    target_type: str          # "kernel", "config", etc.
    target_id: str            # 具体的な対象ID
    parameters: dict          # パラメータ
    constraints: dict         # 制約
    objective: dict           # 目標（メトリクス、方向、閾値）
    promotion: dict           # 昇格に関する設定
```

### 例

```python
R = Requirements(
    target_type="kernel",
    target_id="csc_linear_forward",
    parameters={
        "device": "cuda",
        "in_features": 1024,
        "out_features": 1024,
    },
    objective={
        "metric": "latency_ms",
        "direction": "minimize",
        "min_speedup": 1.05,
    },
    promotion={
        "allowed": False,
        "require_correctness": True,
        "require_dispatch_diagnosis": True,
    },
)
```

## Hypothesis (H)

反証可能な仮説。

```python
@dataclass
class Hypothesis:
    id: str                   # 一意なID
    target_keys: list[str]    # 対象dispatch key
    claim: str               # 「何が悪いか」
    proposed_change: str     # 「どう変えるか」
    expected_effect: str     # 「どう改善するか」（測定可能）
    risk: str               # 「何が起こるか」
    files_expected: list[str]  # 変更予定ファイル
    stop_conditions: list[str] # 停止条件
```

### 検証基準

- `target_keys` が `Requirements.target_id` と関係しているか
- `expected_effect` が測定可能か
- `claim` が反証可能か

## Artifact (B)

実装成果物。必ず隔離する。

```python
@dataclass
class Artifact:
    hypothesis_id: str        # 由来する仮説
    artifact_type: str        # "patch", "worktree", "declare_only"
    changed_files: list[str]  # 変更ファイル一覧
    candidate_specs: list[str]  # 候補spec名
    patch_path: str | None   # パッチファイルパス
    registry_policy: str      # "declare_only" or "publish"
    notes: str               # 補足説明
```

### 重要: registry_policy

- **`declare_only`**（デフォルト）: 実験用。auto_dispatch の対象にならない
- **`publish`**: 本番用。auto_dispatch で選択可能になる

**Guardrail**: promote 前に `publish` を使うとエラー

## EvidenceRecord (C)

このアーキテクチャの中心。すべての意思決定は証拠に基づく。

```python
@dataclass
class EvidenceRecord:
    hypothesis_id: str        # 由来する仮説
    artifact_id: str         # 評価したアーティファクト
    candidate_spec: str      # 候補spec
    baseline_spec: str       # ベースラインspec
    dispatch_keys: list[list[str]]  # 評価したdispatch key
    correctness: str         # "passed", "failed", "unknown"
    eligible: bool           # 対象keyでeligibleか
    mean_ms_candidate: float | None  # 候補の平均実行時間
    mean_ms_baseline: float | None   # ベースラインの平均実行時間
    speedup: float | None    # 速度向上率
    regressions: list[str]   # 回帰が見つかったkey
    failure_reason: str      # 失敗理由
    decision_recommendation: str  # "accepted", "rejected", etc.
    raw_output: str          # 生のベンチマーク出力パス
```

### 必須項目

証拠として有効になるために必要な項目：

1. ✅ `dispatch_keys` - どのkeyで評価したか
2. ✅ `baseline_spec` - 何と比較したか
3. ✅ `correctness` - 正確性検証結果
4. ✅ `eligible` - eligible判定
5. ✅ `speedup` - 速度向上率
6. ✅ `raw_output` - 生データへの参照

## PromotionGate

証拠に基づいて昇格可否を判断。

```python
class PromotionGate:
    def decide(evidence, requirements) -> str:
        if evidence.correctness != "passed":
            return "rejected"           # 正確性失敗
        
        if not evidence.eligible:
            return "needs_narrower_scope"  # 適用範囲が広すぎる
        
        if evidence.regressions:
            return "needs_narrower_scope"  # 回帰あり
        
        if evidence.speedup < min_speedup:
            return "rejected"           # 速度向上不足
        
        return "accepted"              # 承認
```

### 決定の種類

| 決定 | 意味 | 次のアクション |
|------|------|--------------|
| **accepted** | 承認 | 昇格検討 or PR作成 |
| **rejected** | 拒否 | 記録のみ。次の仮説へ |
| **needs_narrower_scope** | 範囲縮小要請 | eligibilityを絞って再試行 |
| **inconclusive** | 決定不能 | 追加データが必要 |
| **superseded** | 後続あり | 新しい実験で置き換え |

## ManagerAgent の役割

ManagerAgent は実装者ではなく**管理者**。

```
ManagerAgent (親)
  │
  ├── HypothesisAgent (子) → H
  ├── ArtifactBuilder (子) → B
  ├── EvaluatorAgent (子) → C
  ├── Analyzer (子) → 分析
  │
  └── PromotionGate → 決定
```

### 責務

1. **要求の読解** - R を理解
2. **ターゲット解決** - dispatch key を特定
3. **ベースライン解決** - 比較対象を特定
4. **子エージェントへの依頼** - 具体的な作業を依頼
5. **結果の検証** - 構造化された H/B/C を検証
6. **Guardrail 適用** - 安全装置のチェック
7. **PromotionGate** - 昇格判断
8. **状態保存** - 再開可能な状態として記録

### Guardrails（安全装置）

ManagerAgent は以下で停止または差し戻し：

- ❌ target dispatch key が未解決
- ❌ baseline が未解決
- ❌ Hypothesis が target と関係ない
- ❌ Hypothesis の expected effect が測定不能
- ❌ Artifact が想定外のファイルを変更
- ❌ Artifact が `publish` を使っている（promote前）
- ❌ candidate が target dispatch key に eligible でない
- ❌ correctness が失敗
- ❌ benchmark が baseline と同じ条件でない
- ❌ speedup が閾値未満
- ❌ raw benchmark output がない

## ファイルベースプロトコル

親子エージェント間の通信はファイル経由。

```
work_items/
  h_001/                          # 仮説ID
    request.json                  # 親→子の依頼
    response.json                 # 子→親の応答
    patch.diff                    # （任意）パッチ
    logs/
      benchmark.jsonl             # ベンチマーク結果
      build.log                   # ビルドログ
```

### プロトコルの利点

- ✅ **差し替え可能** - Codex, Claude, OpenClaw, ローカルスクリプト
- ✅ **永続化** - 通信履歴が自動的に保存される
- ✅ **デバッグ可能** - request/response を後から確認
- ✅ **分散可能** - 将来のリモート実行に対応

## 並列実行

### 並列化可能なフェーズ

```
Phase 1: Hypothesis生成 → 並列化可能
Phase 2: Artifact生成   → 隔離されていれば並列化可能
Phase 3: Evaluation     → リソースタイプで分離
```

### リソース制約

```yaml
eval:
  compile_workers: 4           # コンパイルは並列可能
  correctness_workers: 2       # 正確性チェック
  gpu_benchmark_workers_per_device: 1  # GPUは1台あたり1つ
```

## 状態の永続化

### 保存形式

```json
{
  "algorithm": {
    "requirements": { ... },
    "hypotheses": [ ... ],
    "evidence": [ ... ],
    "round_index": 2
  },
  "analysis": {
    "decisions": ["accepted"],
    "converged": false
  },
  "timestamp": 1704067200.0
}
```

### 再開手順

```python
# 保存
state.to_file("state_round_2.json")

# 再開
loaded_state = OptimizerState.from_file("state_round_2.json")
new_state = agent.optimize(requirements, state=loaded_state)
```

## 実装ファイル一覧

| ファイル | 内容 |
|---------|------|
| `core/state_model.py` | R, H, B, C, X_t, S_t の定義 |
| `core/manager.py` | ManagerAgent, PromotionGate |
| `protocol.py` | ファイルベース通信プロトコル |
| `agents/hypothesis.py` | HypothesisAgent |
| `agents/artifact.py` | ArtifactBuilder |
| `agents/evaluator.py` | EvaluatorAgent |
| `tests/test_state_model.py` | 状態モデルのテスト |
| `tests/test_manager.py` | ManagerAgentのテスト |

## 使用例

### 基本的な最適化

```python
from optagent import ManagerAgent
from optagent.v1.core.state_model import Requirements

# 1. 要求を定義
R = Requirements(
    target_type="kernel",
    target_id="csc_linear_forward",
    objective={"metric": "latency_ms", "min_speedup": 1.2},
)

# 2. ManagerAgent を作成
agent = ManagerAgent(work_dir="./work")

# 3. 最適化実行
state = agent.optimize(R)

# 4. 結果確認
print(f"Round: {state.algorithm.round_index}")
print(f"Hypotheses: {len(state.algorithm.hypotheses)}")
print(f"Evidence: {len(state.algorithm.evidence)}")

# 5. 決定を確認
for ev in state.algorithm.evidence:
    print(f"Decision: {ev.decision_recommendation}")
    print(f"Speedup: {ev.speedup}")
```

### 状態の再開

```python
# ラウンド1
state1 = agent.optimize(R)

# ラウンド2（状態を引き継ぐ）
state2 = agent.optimize(R)  # 内部で advance() が呼ばれる

# または明示的に
state2 = state1.advance(new_H, new_C)
```

## テスト実行

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests/v1 -q
```

## 参考文献

- `kernel_optimizer_architecture.md` - 元のアーキテクチャ仕様
- `docs/archive/STATE_MODEL_MAPPING.md` - 旧対応表
