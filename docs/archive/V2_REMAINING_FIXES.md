# v2 Remaining Fixes

最後の小さな仕上げメモ。前ラウンドで 6 件のアルゴリズム修正は終わっており、残るのは局所的な 3+1 件のみ。

## 現状

- 設計書: `docs/PLANNING_AND_RL.md`（特に §4.4, §9.2）
- テスト: `python3 -m pytest tests/test_v2_core.py tests/test_v2_integration.py tests/test_v2_migration.py tests/test_v2_bugs.py -v`
- 現在 63 件 PASS。アルゴリズムの中核（MCTS descent / Pareto domination / incumbent / posture / value 特徴量）はすべて実装済み。

---

## Fix 1 — `ExpectedHypervolumeImprovement` aggregator が hypervolume になっていない

**File**: `src/optagent/v2/reward.py:117-139`

**現状**:
```python
hvol *= max(0.0, value - ref_val)   # 単なる積。hypervolume ではない
```

`value.py` 側のヘルパ `hypervolume_gain_2d` は正しく実装済み（2D exact + n-D Monte-Carlo）。aggregator はそれを再利用するだけ。

**修正**:
1. `hypervolume_gain_2d` と `euclidean_distance` を `value.py` から `pareto.py` に移動（共有概念のため）。
2. `ExpectedHypervolumeImprovement` に `update_front(front: List[Artifact], objectives: List[Objective])` を追加し、active な Pareto front と objectives を保持。
3. `aggregate(metrics: dict)` は metrics から transient `Artifact` を構築 → `hypervolume_gain_2d(self._front, candidate, self._objectives, self.reference_point)` を呼ぶ。

**検証用テスト**（`test_v2_bugs.py` に追加）:
- objectives = `[Objective("a", "minimize"), Objective("b", "minimize")]`
- front に `{a:1, b:1}` を1件
- `aggregate({a:0, b:0})` > 0 を確認
- `aggregate({a:2, b:2})` == 0 を確認

---

## Fix 2 — `value.py` で reference_point がハードコードされている

**File**: `src/optagent/v2/value.py:322`

**現状**:
```python
reference_point={"x": 0.0, "y": 0.0}
```

objective 名が `x`, `y` のとき以外は事実上 reference 無し（gain が常に 0 になる）。現行テストは objective 名を `x`/`y` にしているため通過してしまっている。

**修正**:
`_compute_hypervolume_gain` 内で reference を導出。各 objective について：
1. `obj.reference` が設定されていればそれを使う
2. なければ現行 Pareto front の worst（minimize なら max、maximize なら min）
3. それも無ければ 0

**検証**: 既存の `test_hypervolume_gain_*` を pass させたまま、objective 名を `latency` / `memory` にした新規テストを 1 件追加して非ゼロ gain を確認。

---

## Fix 3 — `test_v2_core.py` に theatrical test が 7 件残っている

**File**: `tests/test_v2_core.py`

過去ラウンドで shape チェックだけのテストを追加しており、`test_v2_bugs.py` に本当のbehavioralテストが入った後も削除されていない。挙動が壊れても通ってしまうため、誤った安心感の元になる。

**削除対象**:
- `TestStateTransition::test_state_advance_creates_new_state`
- `TestStateTransition::test_state_advance_updates_artifact`
- `TestParetoFront::test_pareto_front_is_non_dominated`
- `TestCostAwareUCB::test_cost_aware_ucb_favors_cheaper_actions`
- `TestRewardEvaluation::test_minimize_objective_flips_sign`
- `TestRewardEvaluation::test_reward_evaluation_with_constraints`
- `TestPlanMCTSCoupling::test_plan_posture_strict_filters_actions`

それぞれ `test_v2_bugs.py` の `TestBug1`〜`TestBug6` で代替済み。

**検証**: テスト件数が 63 → 56 になる。それ以外の影響なし。

---

## Fix 4（任意） — Bug 1 のテストを production code path に揃える

**File**: `tests/test_v2_bugs.py:30-72`

`test_mcts_tree_depth_increases_with_simulations` は `mcts.search()` を一度呼んだ後、内部ループを**手書きで再実装**してから assert している。`search()` 本体にバグが混入しても catch しない。

**修正**:
1. `MCTSOptimizer.search` に `return_tree: bool = False` を追加し、True のとき `(best_action, root)` を返す。または `self._last_root` に保持して後から参照可能にする。
2. テスト側は `_, root = mcts.search(..., return_tree=True)` の 1 行だけにし、その root から depth を測る。

これは algorithmic な不具合ではなく、テスト品質の問題なので余裕があれば。

---

## 完了条件

- Fix 1〜3 適用後、`pytest tests/ -v` がすべて pass（Fix 3 で 7 件減 + Fix 1/2 で 1〜2 件追加）
- `reward.py` の EHVI と `value.py` の hypervolume が同一ヘルパ（`pareto.py` 内）を共有している
- theatrical テストが残っていない

工数感: 30〜60 行の編集 + 数件のテスト書き換え。1 回の小さな PR で完結する規模。
