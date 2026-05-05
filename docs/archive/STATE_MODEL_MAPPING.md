# 状態モデル対応表

`kernel_optimizer_architecture.md` で定義された状態モデルと、`optagent` の実装対応です。

## 数学的状態モデル

```text
アルゴリズム状態: X_t = (R, H_<t, C_<t)
ランタイム状態:   S_t = (Q_t, A_t, D_t)
```

## 対応表

| 数学記号 | 意味 | 実装クラス | ファイル |
|---------|------|-----------|---------|
| **R** | 固定要件 | `Requirements` | `core/state_model.py` |
| **H** | 仮説集合 | `Hypothesis` | `core/state_model.py` |
| **B** | アーティファクト | `Artifact` | `core/state_model.py` |
| **C** | 証拠記録 | `EvidenceRecord` | `core/state_model.py` |
| **Q** | 待ち行列 | `RuntimeState.queue` | `core/state_model.py` |
| **A** | 実行中 | `RuntimeState.active` | `core/state_model.py` |
| **D** | 完了済み | `RuntimeState.done` | `core/state_model.py` |
| **X_t** | アルゴリズム状態 | `AlgorithmState` | `core/state_model.py` |
| **S_t** | ランタイム状態 | `RuntimeState` | `core/state_model.py` |
| **X_{t+1}** | 次状態 | `advance()` メソッド | `core/state_model.py` |

## 状態遷移関数

### 理論

```text
H_t = propose(R, H_<t, C_<t)
B_t = materialize(H_t)
C_t = evaluate(B_t, R)
D_t = decide(C_t, R)

X_{t+1} = (R, H_≤t, C_≤t)
```

### 実装

```python
# ManagerAgent.optimize() で実行
state = OptimizerState(algorithm=AlgorithmState(requirements=R))

# Phase 1: H_t = propose(R, H_<t, C_<t)
hypotheses = self._generate_hypotheses(state)
state.algorithm.hypotheses.extend(hypotheses)

# Phase 2: B_t = materialize(H_t)
artifacts = self._build_artifacts(approved_hypotheses, state)

# Phase 3: C_t = evaluate(B_t, R)
evidence = self._evaluate_artifacts(artifacts, state)
state.algorithm.evidence.extend(evidence)

# Phase 4: D_t = decide(C_t, R)
decisions = self._apply_promotion_gate(evidence, R)

# Phase 5: X_{t+1} = advance(X_t)
new_state = state.advance(new_hypotheses, new_evidence)
```

## ManagerAgent の役割

### 理論

```text
ManagerAgent
  |
  |-- HypothesisAgent(s)  -> H: Hypothesis
  |-- ArtifactBuilder(s)  -> B: Artifact
  |-- EvaluatorAgent(s)   -> C: EvidenceRecord
  |-- AnalyzerAgent       -> analysis / next action
  |
  '-- PromotionGate       -> accepted / rejected / retry / narrow_scope
```

### 実装

```python
class ManagerAgent:
    def __init__(self,
        hypothesis_agent,   # HypothesisAgent.generate()
        artifact_builder,   # ArtifactBuilder.build()
        evaluator,          # EvaluatorAgent.evaluate()
        analyzer,           # 分析関数
    ):
        self.promotion_gate = PromotionGate()  # decide(C_t, R)
```

## Guardrails（安全装置）

### 理論

ManagerAgent は以下で停止または差し戻し：

- target dispatch key が未解決
- baseline が未解決
- Hypothesis が target と関係ない
- Artifact が想定外ファイルを変更
- Artifact が publish を使っている（declare_only が必要）
- candidate が target dispatch key に eligible でない
- correctness が失敗
- benchmark が baseline と同じ条件でない
- speedup が threshold 未満
- raw benchmark output がない

### 実装

```python
class ManagerAgent:
    def _review_hypotheses(self, hypotheses, state):
        for h in hypotheses:
            if not h.expected_effect:
                raise GuardrailError("No measurable expected_effect")
    
    def _build_artifacts(self, hypotheses, state):
        for artifact in artifacts:
            if artifact.registry_policy == "publish":
                raise GuardrailError("Must use declare_only before promotion")
    
    def _evaluate_artifacts(self, artifacts, state):
        for evidence in evidence_list:
            if not evidence.dispatch_keys:
                raise GuardrailError("Missing dispatch_keys")
```

## 構造化 Contract（H/B/C）

### Hypothesis (H)

```json
{
  "id": "h_001",
  "target_keys": ["op:conv2d_forward", "kernel_size:3x3"],
  "claim": "generic path has avoidable branching",
  "proposed_change": "add specialized KernelSpec",
  "expected_effect": "lower mean_ms for target cluster",
  "risk": "may regress padded non-square cases",
  "files_expected": ["kernels/ops/bscr/conv_forward.py"],
  "stop_conditions": ["correctness failure", "speedup below threshold"]
}
```

→ `Hypothesis` dataclass に対応

### Artifact (B)

```json
{
  "hypothesis_id": "h_001",
  "artifact_type": "patch",
  "changed_files": ["kernels/ops/bscr/conv_forward.py"],
  "candidate_specs": ["bscr_conv_fwd_3x3_unit_cuda"],
  "patch_path": "artifacts/h_001/patch.diff",
  "registry_policy": "declare_only",
  "notes": "candidate is not published to auto dispatch"
}
```

→ `Artifact` dataclass に対応

### EvidenceRecord (C)

```json
{
  "hypothesis_id": "h_001",
  "candidate_spec": "bscr_conv_fwd_3x3_unit_cuda",
  "baseline_spec": "bscr_conv_fwd_generic_cuda",
  "dispatch_keys": [["op:conv2d_forward", "device:cuda", ...]],
  "correctness": "passed",
  "eligible": true,
  "mean_ms_candidate": 0.82,
  "mean_ms_baseline": 0.91,
  "speedup": 1.11,
  "decision_recommendation": "accepted",
  "raw_output": "outputs/kernel_optimizer/h_001.jsonl"
}
```

→ `EvidenceRecord` dataclass に対応

## ファイルベースプロトコル

### 理論

```text
work_items/
  h_001/
    request.json
    response.json
    patch.diff
    logs/
```

### 実装

```python
class WorkItemDir:
    def __init__(self, base_dir, item_id):
        self.path = base_dir / item_id
        self.request_path = self.path / "request.json"
        self.response_path = self.path / "response.json"
        self.patch_path = self.path / "patch.diff"
        self.logs_dir = self.path / "logs"
```

## PromotionGate の決定

### 理論

```python
class PromotionGate:
    def decide(self, evidence, requirements):
        if not evidence.correctness.passed:
            return "rejected"
        if not evidence.eligibility.all_target_keys_supported:
            return "needs_narrower_scope"
        if evidence.regressions:
            return "needs_narrower_scope"
        if evidence.speedup < requirements.min_speedup:
            return "rejected"
        return "accepted"
```

### 実装

```python
class PromotionGate:
    def decide(self, evidence: EvidenceRecord, requirements: Requirements) -> str:
        if evidence.correctness != "passed":
            return "rejected"
        if not evidence.eligible:
            return "needs_narrower_scope"
        if evidence.regressions:
            return "needs_narrower_scope"
        min_speedup = requirements.objective.get("min_speedup", 1.05)
        if evidence.speedup is None or evidence.speedup < min_speedup:
            return "rejected"
        return "accepted"
```

## 子エージェントの差し替え

### 理論

```yaml
agents:
  hypothesis:
    provider: claude_code
    max_workers: 3
  implementation:
    provider: codex
    max_workers: 2
  evaluation:
    provider: local
    max_workers: 1
```

### 実装

```python
# HypothesisAgent 差し替え
agent = ManagerAgent(
    work_dir="./work",
    hypothesis_agent=my_custom_hypothesis_generator,
    artifact_builder=my_custom_builder,
    evaluator=my_custom_evaluator,
)

# 各 agent は Callable[[Path], Path] として渡す
# (request.json のパスを受け取り、response.json のパスを返す)
```

## テスト対応

| テスト項目 | 理論的根拠 | テストファイル |
|-----------|----------|--------------|
| Requirements は immutable | R は固定 | `test_state_model.py::TestRequirements::test_immutable` |
| Artifact は declare_only | 実験と本番の分離 | `test_state_model.py::TestArtifact::test_isolation` |
| Evidence は complete | C に必要な情報を全て含む | `test_state_model.py::TestEvidenceRecord::test_complete_evidence` |
| 状態遷移 X_t → X_{t+1} | advance() メソッド | `test_state_model.py::TestAlgorithmState::test_state_transition` |
| PromotionGate | decide(C_t, R) | `test_manager.py::TestPromotionGate` |
| Guardrails | 安全装置 | `test_manager.py::TestManagerAgent` |
