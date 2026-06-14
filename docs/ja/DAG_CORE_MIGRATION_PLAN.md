# DAG Core Migration Plan

この文書は、Arctx を新しい DAG core 方針へ移行するための実装計画です。

設計方針は `docs/ja/DAG_CORE_REDESIGN.md` を前提にする。

移行は大きく 2 フェーズに分ける。

1. 表現・CLI レイヤーだけを先に新仕様へ寄せる。
2. 内部実装・schema・storage を新仕様へ寄せる。

この分離により、ユーザー向けの分かりやすさを先に改善しつつ、内部リネームによる大きな破壊的変更を後でまとめて扱える。

## Phase 1: 表現と CLI の移行

### 目的

内部実装は大きく変えず、ユーザーから見える言葉と操作体系を新仕様へ寄せる。

このフェーズでは、内部 class 名 `Transition` や storage field `transitions` は原則そのまま残す。

外向きには `Transition` を `Step` と呼ぶ。

### やること

#### 1. 新 CLI を追加する

MVP の主要 CLI を追加する。

```bash
arctx add node
arctx add step
arctx attach <target-id>
arctx cut <target-id>
arctx show <id>
arctx log
```

旧CLIは順次、登録から外す。

```bash
arctx graph dump
```

`transition`, `payload`, `node` はトップレベル登録から外した。
`graph dump` は当面 compatibility / plumbing として残す。

`arctx view` と `arctx guide` は Phase 1 の途中でCLI登録から削除した。

#### 2. `arctx add node`

依存を持たない Node を作る。

想定:

```bash
arctx add node --title "baseline"
arctx add node --type note --field text="initial observation"
```

内部処理:

- `Node` を mint する。
- `RunGraph.add_node()` で追加する。
- `--title`, `--type`, `--field` があれば `NodePayload` を付ける。
- work event を記録する。
- `--json` では作成した Node / Payload を返す。

主な変更候補:

- `packages/arctx/src/arctx/core/run/handle.py`
- `packages/arctx/src/arctx/core/run/` に `node.py` か `add.py` を追加
- `packages/arctx-cli/src/arctx_cli/commands/add.py`
- `packages/arctx-cli/src/arctx_cli/commands/__init__.py`

#### 3. `arctx add step`

入力 Node から Step を作り、出力 Node を自動生成する。

想定:

```bash
arctx add step --from n_123 --title "try new design"
arctx add step --from n_a --from n_b --title "merge results"
```

内部処理:

- 現行の `RunHandle.transition()` を使う。
- CLI 表示では `transition` ではなく `step` と呼ぶ。
- 作成される内部 record は当面 `Transition` のままでよい。
- `--json` では `kind: "step"` として返す。

主な変更候補:

- `packages/arctx-cli/src/arctx_cli/commands/add.py`
- `packages/arctx-cli/src/arctx_cli/payload_builder.py`
- `packages/arctx/src/arctx/core/run/transition.py`

#### 4. `arctx attach <target-id>`

Node / Step に Payload を付ける。

想定:

```bash
arctx attach n_123 --type note --field text="baseline"
arctx attach t_456 --type result --field score=0.91
```

Phase 1 では Step ID は内部都合で `t_...` のままでもよい。

内部処理:

- `target-id` から Node / Transition を自動判定する。
- Node なら `NodePayload` を作る。
- Transition なら `TransitionPayload` を作る。
- `RunGraph.attach_payload()` で追加する。

現行の `RunHandle.attach()` は node-targeting payload 専用なので、次のどちらかにする。

- CLI 側で Node / Transition を判定し、直接 `RunGraph.attach_payload()` を使う。
- core 側に汎用 attach API を追加する。

推奨は後者。

```text
RunHandle.attach(target_id, payload, target_kind=None)
```

または、

```text
RunHandle.attach_payload(target_id, payload)
```

として Node / Step 両方に対応する。

主な変更候補:

- `packages/arctx/src/arctx/core/run/attach.py`
- `packages/arctx-cli/src/arctx_cli/commands/attach.py`
- `packages/arctx-cli/src/arctx_cli/commands/payload.py`

#### 5. `arctx cut <target-id>`

Cut は Payload の一種だが、重要操作なので専用 CLI は残す。

想定:

```bash
arctx cut n_123 --reason "invalid assumption"
arctx cut t_456 --reason "bad derivation"
```

内部処理:

- `target-id` から Node / Transition を自動判定する。
- 現行の `RunHandle.cut()` を使う。
- CLI 表示では `transition` ではなく `step` と呼ぶ。

既存形式も当面残してよい。

```bash
arctx cut node <id>
arctx cut transition <id>
```

主な変更候補:

- `packages/arctx-cli/src/arctx_cli/commands/cut.py`

#### 6. `arctx show <id>`

Node / Step / Payload を 1 件表示する統合コマンドにする。

想定:

```bash
arctx show n_123
arctx show t_456
arctx show pl_789
```

表示方針:

- Node は `kind: node`
- Transition は `kind: step`
- Payload は `kind: payload`
- Transition の内部 ID が `t_...` でも、表示語彙は Step にする。

表示したい情報:

- id
- kind
- active / inactive
- payloads
- Step の inputs / output
- CutPayload があれば reason

主な変更候補:

- `packages/arctx-cli/src/arctx_cli/commands/show.py`
- `packages/arctx/src/arctx/core/cuts.py`

#### 7. `arctx log`

DAG の連なりを見るコマンドにする。

想定:

```bash
arctx log
arctx log --from n_123
arctx log --to n_456
```

Phase 1 では既存の `dump`, `trace`, `reachable` の機能を整理して使う。

- `log` は全体または root から下流を見る。
- `log --from` は指定 Node から下流を見る。
- `log --to` は指定 Node までの上流を見る。

主な変更候補:

- `packages/arctx-cli/src/arctx_cli/commands/log.py`
- `packages/arctx/src/arctx/core/run/dump.py`
- `packages/arctx/src/arctx/core/run/trace.py`
- `packages/arctx/src/arctx/core/run_graph.py`

#### 8. `context`, `status`, `debug`, `sync`, `link` は入れない

MVP の主要 CLI には入れない。

- `context` は将来、`show` と `log` を組み合わせた agent 向け合成ビューとして検討する。
- `status` は Git 的 working tree がないため、意味が固まってから考える。
- `debug` は実際の診断項目が見えてから分離する。
- `sync` は remote / sharing 方針が固まってから名前を決める。既存の `arctx sync` CLI は削除済み。
- `link` は Edge を直接張れるように見えるため採用しない。

#### 9. `revise step` は後続で検討する

`revise step` は Step の修正を append-only に表す重要操作だが、Phase 1 の最初の実装には含めない。

未決事項:

- supersede marker を Payload として持つか。
- revision 専用 Payload を作るか。
- 新しい Step を作り、旧 Step を cut する運用に寄せるか。

当面は `add step`, `attach`, `cut` の組み合わせで表現する。

### Phase 1 の完了条件

- README / docs の主要説明で `Node / Step / Payload` が使われている。
- ユーザーが `arctx add node` で孤立 Node を作れる。
- ユーザーが `arctx add step` で Node から Step を作れる。
- ユーザーが `arctx attach <id>` で Node / Step に Payload を付けられる。
- ユーザーが `arctx cut <id>` で Node / Step を cut できる。
- ユーザーが `arctx show <id>` で record を確認できる。
- ユーザーが `arctx log` で DAG の流れを確認できる。
- JSON 出力では外向き語彙として `step` を返せる。
- 既存テストは維持する。
- 新 CLI のテストを追加する。

### Phase 1 でやらないこと

- `Transition` class のリネーム。
- `transition_id` field のリネーム。
- `target_kind="transition"` の変更。
- storage schema の破壊的変更。
- `views` field は削除済み。
- Git extension の大規模変更。
- remote / sharing の実装。

## Phase 2: 内部実装の移行

### 目的

外向きの `Step` という表現に合わせて、内部実装も `Transition` から `Step` へ寄せる。

このフェーズは storage schema と public API に影響するため、Phase 1 より大きな破壊的変更として扱う。

### やること

#### 1. Core schema のリネーム

候補:

```text
Transition -> Step
transition_id -> step_id
TransitionPayload -> StepPayload
target_kind="transition" -> target_kind="step"
transitions -> steps
transitions.jsonl -> steps.jsonl
payloads_by_transition -> payloads_by_step
transition_by_output_node -> step_by_output_node
transitions_by_input_node -> steps_by_input_node
```

主な変更候補:

- `packages/arctx/src/arctx/core/schema/graph.py`
- `packages/arctx/src/arctx/core/schema/payloads.py`
- `packages/arctx/src/arctx/core/run_graph.py`
- `packages/arctx/src/arctx/storage/jsonl.py`
- `packages/arctx/src/arctx/storage/sqlite.py`

#### 2. RunHandle API のリネーム

候補:

```text
RunHandle.transition(...) -> RunHandle.add_step(...)
transition_impl -> add_step_impl
```

既存の `transition()` は互換 shim にするか、ベータなので削除するかを決める。

現行方針では、ベータ中の破壊的変更は許容されるため、不要な shim は増やさない。

#### 3. CLI plumbing の整理

Phase 1 で残した旧 CLI を整理する。

候補:

- `arctx transition ...` はトップレベルCLI登録から外した。内部 helper は互換用途で残す。
- `arctx payload ...` はトップレベルCLI登録から外した。payload 追加は `attach` に寄せる。
- `arctx node ...` はトップレベルCLI登録から外した。参照は `show <id>` に寄せる。
- `arctx graph dump` を `arctx log` に寄せる。
- `arctx view` は削除済み。

#### 4. Storage migration 方針

ベータ中なので、旧 schema の自動 migration を必須にしない選択肢がある。

選択肢:

1. 旧 run を捨てる前提で schema を一気に変える。
2. `arctx migrate` で `transitions` から `steps` に変換する。
3. 読み込みだけ旧 schema を許し、保存は新 schema にする。

推奨は、ユーザー数と既存データ量を見て決める。

MVP の速度を優先するなら 1。

公開済み beta への配慮を少し残すなら 2。

#### 5. GraphView の退避

MVP では表に出さない方針なので、内部的にも不要かを判断する。

候補:

- `RunGraph.views` を削除する。完了済み。
- storage の `views.jsonl` を削除する。新規保存では作らない。
- `view` CLI を削除する。完了済み。
- 代わりに `show --from`, `log --from`, `log --to` を整備する。

ただし、将来 GUI の保存済みフィルタや named query として復活する可能性はある。

その場合は `GraphView` ではなく、より明確な名前にする。

候補:

- `SavedQuery`
- `Workspace`
- `Selection`

#### 6. Extension API の更新

Extension が `Transition` や `target_kind="transition"` に依存しているため、Step へ更新する。

主な対象:

- git extension
- command extension
- claude-code / codex adapter
- payload registry
- validation
- default aliases

特に git extension は `GitChangePayload` が Transition に付く前提なので、`Step` に付く payload として言い換える。

#### 7. Tests の全面更新

対象:

- core schema tests
- run API tests
- storage tests
- CLI tests
- extension tests
- docs examples

旧語彙 `transition` を期待しているテストを `step` に更新する。

### Phase 2 の完了条件

- 内部 schema が `Step` を第一級に扱っている。
- storage が `steps` として保存できる。
- public API が `Step` 語彙になっている。
- CLI から `transition` 語彙が主要面に出ない。
- docs / README / examples が `Node / Step / Payload` に統一されている。
- extension が Step 前提で動く。
- 全テストが新語彙で通る。

## 推奨する最初の実装順

最初の PR / commit では Phase 1 の中でもさらに小さく切る。

### Step 1

ドキュメントを追加する。

- `DAG_CORE_REDESIGN.md`
- `DAG_CORE_MIGRATION_PLAN.md`

### Step 2

`arctx add node` を実装する。

これは GraphView なしで DAG に点を置く最小操作なので、新仕様の核になる。

### Step 3

`arctx add step` を実装する。

内部では既存 `RunHandle.transition()` を使い、外向きだけ `step` にする。

### Step 4

`arctx attach <target-id>` を実装する。

Node / Step の両方に Payload を付けられるようにする。

### Step 5

`arctx show <id>` を Step 表記に寄せる。

### Step 6

`arctx cut <target-id>` を簡略化する。

### Step 7

`arctx log` を整備する。

## リスク

### `Step` と内部 `Transition` の二重語彙

Phase 1 では外向き `Step`、内部 `Transition` になる。

実装者には一時的に分かりにくい。

対策:

- docs に「Phase 1 では内部名は Transition のまま」と明記する。
- CLI 出力は一貫して `step` にする。
- 内部コメントは無理に全部変えない。

### `attach` の汎用化

現行 `RunHandle.attach()` は node 専用。

Step にも Payload を付けるため、API 設計を雑にすると混乱する。

対策:

- `attach_payload` のような汎用名を検討する。
- CLI では `attach <target-id>` に統一する。
- `target-id` 自動判定をテストする。

### 旧 CLI との共存

新旧 CLI が併存すると help が膨らむ。

対策:

- Phase 1 では既存 CLI を plumbing として扱う。
- help 上で hidden にできるものは隠す。
- README では新 CLI だけを前面に出す。

### Storage schema 変更

Phase 2 で大きな変更になる。

対策:

- Phase 1 では storage を触らない。
- Phase 2 の開始時に migration 方針を決める。

## 現時点の判断

まず Phase 1 を進める。

内部実装の全面 Step 化はまだ始めない。

理由:

- ユーザー体験の改善を先に出せる。
- 新 CLI の使い勝手を見てから内部名を確定できる。
- storage schema 変更を後回しにできる。
- 既存 extension / tests を大きく壊さずに進められる。
