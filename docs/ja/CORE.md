# ARCTX コアコマンド（基本これだけ）

日常はこの**5つの動詞**で足ります。残り（`log`/`dump`/`show`/`list`/`export`/
`use`/`serve`/`git` …）は閲覧・配管・拡張で、コアではありません。

| 動詞 | 役割 | 一言 |
|------|------|------|
| `init` | run を作る（1回） | 始点 |
| `lane` | 作業の**文脈**（ソロ/協働の作業の線） | どのレーンで作業するか |
| `add`  | node/step を作る＝**トポロジ**を伸ばす | グラフを育てる |
| `attach` | 既存 node/step に payload を足す＝**注釈** | 結果・計測・意図を貼る |
| `cut`  | 非活性化（理由付き）＝**却下/撤回** | 消さずに残す |

心象：**`init` で始め、`lane` で文脈を選び、`add`(構造)＋`attach`(注釈) で育て、
`cut` で撤回。** 失敗も過去も DAG に残る。

## 1. 始める

```bash
arctx init my_task --run-id scd-dev      # run を作成（<gitdir>/arctx-id に記録）
```

## 2. レーン（作業の文脈）— `source .venv` / `git switch` 風

```bash
arctx lane geometry        # レーン "geometry" に切替（無ければ作成）。
                           # <gitdir>/arctx-lane に記録 → シェルが変わっても同じ。eval 不要
arctx lane                 # 今どのレーンか表示
arctx lane --list          # レーン一覧
```

レーンは**1ユーザー専有ではない**：別の人が同じレーンに参加してよい（属性は各操作の
actor 単位）。**並行探索**を複数ターミナルで走らせるときだけ、シェルローカルに固定する：

```bash
eval "$(arctx lane geometry --shell)"    # この端末だけ env で固定（env はファイルより優先）
```

→ 普段は eval 不要（ファイルポインタが既定）。eval は**並行のときだけ**。

## 3. グラフを育てる

```bash
arctx add step --from <node> --title "explore ProductGeometry"   # 構造を伸ばす
arctx add step --from <A> --from <B> --title "merge A and B"      # 多入力 = 統合(join/merge)
arctx attach <node> --type result --json '{"recall@k":"rough at scale"}'  # 注釈を貼る
```

## 4. 却下（残す）

```bash
arctx cut --node <tip> --reason "grow-score not smooth at scale"  # 非活性化（理由付き、削除しない）
```

採用（merge）は **cut しないだけ**。続けるなら tip から `add` を重ねる。

## 5. 同期 = union

複数人/複数マシンの統合は **ID-aware な union**（append-only・冪等）。可換・冪等・
収束。運搬は git（push/pull）。**手作業の調停は無い** — 却下は cut として残るだけ。

---

### PR の流れ（新コマンド不要）

| やること | コマンド |
|---|---|
| ワークスペースを開く | `arctx lane <name>` |
| 提案（PR） | `git push`（store が repo 管理） |
| レビュー | `arctx log` / `arctx dump` |
| 採用 | 何もしない（active のまま） |
| 却下 | `arctx cut --reason ...` |
| 結果の統合 | `arctx add step --from A --from B` |
| 同期 | `git pull` / `push`（union 収束） |
