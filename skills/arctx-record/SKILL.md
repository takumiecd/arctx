---
name: arctx-record
description: ARCTXが有効なリポジトリで作業の過程（コード変更・意思決定・行き詰まり・調査結果）をARCTXランに記録する。
---

# ARCTX への作業記録

このスキルは、エージェント自身が行う作業、またはユーザー主導の作業をARCTXランに逐一記録するための手順を定める。

`arctx-cli` がインストールされていれば `arctx` コマンドがそのまま使える
（未インストールなら `pip install arctx-cli`）。

## 0. 記録モデルの大前提（必読）

- **コミットは `arctx git commit -m "..."` で行う。** これが実際に `git commit`
  を駆動し、その変更を1つの Transition として記録する。**素の `git commit`
  は ARCTX に自動記録されない**（amend/rebase/revert/cherry-pick/merge の
  追従フックは入るが、通常コミットの新規記録は `arctx git commit` 経由）。
- コミットを伴わない作業（調査・意思決定・行き詰まり）は `transition` /
  `attach` / `cut` で明示的に記録する。
- 複数エージェントが同じランで並行作業するときは、各自が
  `eval "$(arctx work-session env --run <run> --new --user <name>)"` で
  自分の work-session を持つ。各エージェントの最初のコミットはランルートの
  兄弟 Transition として並ぶ（互いに衝突しない）。

## 1. アクティブなランを特定する

```bash
# 現在のアクティブランを確認する
arctx current

# 未設定の場合、git リポジトリルートの .arctx-id を確認する
cat .arctx-id

# 環境変数でも指定可能
echo $ARCTX_RUN_ID
```

ランが存在しない場合は初期化する:

```bash
arctx init <requirement_id> --extension git
```

`--extension git` を付けると `.arctx-id` ファイルが自動で作成され、以降のコマンドがランを自動解決する。

現在の全体構造を把握するには:

```bash
arctx dump --format outline
```

## 2. どのバーブを使うか

| 状況 | バーブ |
|------|--------|
| 作業が新しい状態を生み出した（実装・リファクタ・調査完了） | `transition` |
| 既存ノードに注釈を追加する（メモ・観察・補足） | `attach` |
| 試みた方向を放棄した・行き詰まりだった | `cut` |

### `transition` — 新しい状態への遷移

入力ノードから出力ノードを1つ生成する。作業が前の状態から新しい状態へ進んだときに使う。

```bash
# 汎用 TransitionPayload で記録する
arctx transition create \
  --from <input_node_id> \
  --payload-type transition_payload \
  --field type=implementation \
  --field 'content={"summary": "CSC storage への index dtype 修正を実装"}'

# 出力: {"transition_id": "t_...", "output_node_id": "n_..."}
```

複数ノードからのマージ（fan-in）:

```bash
arctx transition create \
  --from <node_a> --from <node_b> \
  --payload-type transition_payload \
  --field type=merge
```

### `attach` — ノードへの注釈

状態グラフを変えずに既存ノードに情報を追加する。

```bash
# ノードにメモを付ける
arctx payload add \
  --node <node_id> \
  --payload-type node_payload \
  --field type=note \
  --field 'content={"text": "この実装では backward pass が全スロット対象になる（設計上の意図）"}'
```

### `cut` — 行き詰まり・放棄したパスを記録

```bash
# ノードを cut する（そのノード以降のサブツリーが非アクティブになる）
arctx cut node <node_id> --reason "この方向は性能要件を満たさない"

# transition を cut する
arctx cut transition <transition_id>
```

cut は append-only — グラフレコードは削除されない。非アクティブ性は読み取り時に計算される。

## 3. ペイロードタイプの選び方

### 汎用ペイロード（最も多用する）

```
NodePayload(type="note")          — ノードへのメモ・観察
NodePayload(type="finding")       — 調査結果・発見
TransitionPayload(type="refactor") — リファクタリング
TransitionPayload(type="implementation") — 実装作業
TransitionPayload(type="investigation") — 調査フェーズ
TransitionPayload(type="test")    — テスト追加
```

`type` は任意文字列。プロジェクト内で一貫して使う。

### CutPayload — cut マーカー

`arctx cut` コマンドが自動で生成する。直接構築する必要はない。

### git 拡張ペイロード — git コミットを含む作業

git 拡張が有効な場合、`arctx git commit` / `arctx commit` が `GitChangePayload` と `BranchPayload` を自動生成する:

```bash
# 変更をステージしてから arctx git commit で記録する。
# arctx が実際の git commit を駆動し、GitChangePayload / BranchPayload を生成する。
git add -A
arctx git commit -m "fix: INDEX_DTYPE を torch.int32 に統一"
```

入力ノードは明示指定しない（`--from` は無い）。work-session があればその
ポインタ、無ければランルートから解決される。並行作業では先に
`arctx work-session env --new --user <name>` で自分のセッションを持つこと。

amend / rebase / revert / cherry-pick / merge は追従フックが自動で取り込むため
手動記録は不要。ただし**通常の新規コミットは `arctx git commit` 経由が必須**
（素の `git commit` は記録されない）。

## 4. Python API から記録する（エージェント実装内）

```python
from arctx.core.run.handle import RunHandle
from arctx.core.schema.payloads import TransitionPayload, NodePayload

# ランのロード（store の root は <ARCTX_HOME>/runs。runs_dir() がそれを解決する）
from arctx.paths import runs_dir
from arctx.storage import JsonlRunStore
store = JsonlRunStore(runs_dir())
handle = store.load_run(run_id)

# 遷移を記録する
payload = TransitionPayload(
    payload_id="pending",
    target_id="pending",
    type="implementation",
    content={"summary": "CSC index dtype 修正", "files_changed": ["formats/csc.py"]},
)
transition = handle.transition(
    input_node_ids=[current_node_id],
    payload=payload,
)
output_node_id = transition.output_node_id
store.save_run(handle)

# ノードにメモを付ける
note = NodePayload(
    payload_id=handle._next_id("pl"),
    target_id=output_node_id,
    type="note",
    content={"text": "backward pass が全スロット対象なのは設計上の意図"},
)
handle.attach(output_node_id, note)
store.save_run(handle)
```

## 5. ユーザー主導の作業を記録するとき

ユーザーが実施した作業を記録する場合、作業前後に確認する:

1. 作業開始前: `arctx dump --format outline` で現在地を把握
2. 作業完了後: 結果を `transition` で記録し、output_node_id を次の起点として保持
3. 行き詰まりが判明したら: 即座に `cut` で記録

## 6. 記録のタイミングの判断基準

記録する:
- コードの動作が変わった（バグ修正・機能追加・リファクタ）
- 調査が完了し、発見があった
- 意思決定ポイント（複数の選択肢から一つを選んだ）
- 行き詰まりが確定した

記録しない:
- 中間的なコンパイルエラーの修正
- 単純なフォーマット修正（lintの自動修正など）
- 試行中でまだ結果が出ていないもの（後でまとめて記録する）

## 7. 状態の確認コマンド

```bash
# 全体構造をLLM向け形式で表示
arctx dump --format outline

# 特定ノードから下を表示
arctx dump --node <node_id> --depth 3

# 特定ノードの履歴を遡る
arctx trace <node_id>

# ノードのペイロードを確認する
arctx payload list --node <node_id>
```
