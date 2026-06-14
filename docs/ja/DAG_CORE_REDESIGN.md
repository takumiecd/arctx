# Arctx DAG Core Redesign Memo

この文書は、Arctx を「仕様履歴を残すツール」から「DAG を編集・整理・共有するためのツール」へ再定義するための設計メモです。

現時点では実装仕様の確定版ではなく、MVP に向けた議論用のたたき台です。

## 目的

Arctx の中心を、曖昧な「仕様の履歴」ではなく、明確な「append-only な DAG 操作ログ」に置く。

ユーザーが理解すべき基本概念を減らし、CLI / GUI / agent 連携のどれから触っても同じモデルに見えるようにする。

## 現行コードの見え方

現行実装は、すでに大きくはこの方向に近い。

- `RunGraph` が `nodes`, `transitions`, `payloads`, `views`, `work_sessions`, `work_events` を保持している。
- `Node` は純粋な DAG 上の点として実装されている。
- `Transition` は `input_node_ids` と `output_node_id` を持ち、多入力から単一出力 Node を作る。
- `Payload` は Node / Transition に後付けされる意味情報として実装されている。
- `CutPayload` は削除ではなく append-only な無効化 marker として実装されている。
- extension 機構は payload / verb / CLI / validation を追加できる形で存在している。

一方で、ユーザー向けの概念としては複雑さが出ている。

- `run`, `graph`, `view`, `current`, `work-session` の関係が直感的ではない。
- `GraphView` が MVP の表面概念としては重い。
- CLI が `transition create`, `payload add`, `graph dump`, `view`, `git commit` などに分散している。
- `Transition` という名前は正確だが、ユーザー向けにはやや硬く、状態機械的な印象が強い。
- Git extension が表面に出すぎると、Arctx の中心単位が DAG 操作なのか Git commit なのか分かりにくくなる。

## 新しい中核定義

```text
Arctx = one append-only DAG log
```

Arctx は、1 つの DAG に対して Node / Step / Payload を追記していくシステムとして扱う。

Git のような「変更を commit にまとめる」モデルではなく、Arctx では各操作そのものが履歴単位になる。

```text
add node
add step
attach payload
cut
```

これらはすべて append-only な操作として記録される。

`revise step` のような修正操作も将来的には必要だが、最初の MVP では `add step`, `attach`, `cut` の組み合わせで表現する。

## 基本モデル

### Node

DAG 上の点。

状態、成果物、判断、観測、設計断片、実験結果、外部 repo 参照などを表す。

Node 自体はできるだけ薄く保ち、意味情報は Payload に持たせる。

### Step

1 つ以上の Node から、新しい Node を生む操作。

現行実装の `Transition` に相当する。ユーザー向けの名前は `Step` に寄せる。

```text
Node(s) -- Step --> Node
```

重要な制約:

- Step は 1 つ以上の入力 Node を持てる。
- Step は必ず 1 つの出力 Node を持つ。
- fan-out は同じ入力 Node から複数の Step を作ることで表す。
- join は複数入力の Step で表す。
- 既存 Node の依存関係を後から直接変えるのではなく、新しい Step / Node を作る。

### Payload

Node / Step に付く追加情報。

Payload は Arctx の意味拡張ポイントであり、core も extension も Payload を通じて情報を付ける。

例:

- note
- rationale
- result
- repo-ref
- git-change
- agent.prompt
- agent.tool_use
- cut

### Cut

Cut は独立した基本概念ではなく、Payload の一種。

`CutPayload` は Node / Step に付与される append-only marker であり、対象とその下流を現在の有効 DAG から外す。

削除ではない。履歴は残る。

CLI では重要操作として `arctx cut` を残してよいが、意味的には以下の専用ショートカットである。

```bash
arctx attach <target-id> --type cut
```

## RunGraph の位置づけ

`RunGraph` はユーザーが最初に理解すべき概念ではなく、Node / Step / Payload をまとめる保存・検証・同期の単位とする。

MVP の説明では、基本的に「Arctx は 1 つの DAG を持つ」と言えばよい。

実装上は次のような構造になる。

```text
RunGraph
  nodes
  steps
  payloads
  work_sessions
  work_events
  metadata
```

現行実装では `steps` は `transitions` として存在する。短期的には内部名を残してもよい。

## GraphView の扱い

MVP では `GraphView` を表の概念から外す。

理由:

- 1 つの DAG を理解する前に view が出ると、ユーザーが混乱しやすい。
- view は「別の DAG」なのか「見方」なのかが分かりにくい。
- まずは RunGraph 全体から必要な部分を query / filter する方が自然。

代替:

```bash
arctx show --from <node>
arctx show --active-only
arctx log --from <node>
```

つまり、GraphView は「保存された別ビュー」ではなく、「表示時の query」として扱う。

短期的には `RunGraph.views` をすぐ削除しなくてもよい。

移行方針:

1. CLI / docs から `view` を前面に出さない。
2. 新しい主要 CLI は `RunGraph` 全体を対象にする。
3. 必要なら後で storage schema から `views` を削除する。

## CLI 方針

CLI は少なく、厳密に、agent から扱いやすくする。

主要コマンド案:

```bash
arctx init
arctx current
arctx use <node>

arctx add node
arctx add step
arctx attach
arctx cut

arctx show
arctx log
```

MVP では、仕様が曖昧な補助コマンドを無理に入れない。

特に `link`, `sync`, `debug`, `status` は、現時点では必須コマンドにしない。

- `link`: core model に Edge がないため、意味が曖昧になりやすい。
- `sync`: remote / GitHub / local file sharing の方針が固まるまで保留する。
- `debug`: 何を診断するかは実装後に見えてくるため、最初は `show` / `log` で代替する。
- `status`: Git のような working tree がないなら、必須とは限らない。

### add node

依存を持たない Node を作る。

これは非常に重要。DAG の中に、まだ何にも依存していない点を明示的に置ける。

```bash
arctx add node --title "baseline"
```

### add step

入力 Node から Step を作り、出力 Node を自動生成する。

```bash
arctx add step --from n_123 --title "try new design"
```

複数入力:

```bash
arctx add step --from n_a --from n_b --title "merge results"
```

`--from` を省略した場合は current node から作る。

### attach

Node / Step に Payload を付ける。

```bash
arctx attach n_123 --type note --field text="baseline"
arctx attach s_456 --type result --field score=0.91
```

`attach` は `annotate` より広い。注釈だけでなく、外部参照、実験結果、git 情報、agent 情報などを付けられる。

### cut

CutPayload を付ける専用コマンド。

```bash
arctx cut n_123 --reason "assumption invalidated"
arctx cut s_456 --reason "bad derivation"
```

ID から Node / Step を自動判定できるなら、ユーザーに種別を入力させない。

ただし曖昧な場合は明示を要求する。

## link コマンドについて

`link` は採用しない。

理由:

- Arctx の core model には独立した Edge record がない。
- `link A B` は「既存 Node B の依存に A を追加する」ように見える。
- 既存 Node の依存関係を後から変えると、append-only な意味論と衝突しやすい。

依存関係を増やす操作は `add step --from ...` に統一する。

`link` という別名を作ると、「Edge を直接張れる」という誤解を生むため、MVP では入れない。

## status / debug / sync について

`status`, `debug`, `sync` は一見便利だが、MVP の中核操作ではない。

Arctx では Git のような未コミット working tree を前提にしないため、`status` の意味は自明ではない。

`debug` も、最初から独立コマンドにすると仕様が広がりすぎる。まずは `show` と `log` で確認できる情報を増やし、実際に診断したい不具合が見えてから分離する。

`sync` は共有機能の名前としては自然だが、GitHub に置くのか、Arctx 独自 remote を作るのか、ファイルを配布するのかで意味が変わる。そのため、remote 方針が固まるまでは主要 CLI に入れない。

将来必要になった場合だけ、次のように追加する。

- `status`: current node / active graph / validation summary を短く表示する。
- `debug`: storage / graph invariant / extension validation を詳しく調べる。
- `sync`: remote backend と同期する。

## commit は不要

Arctx のユーザー向けモデルに `commit` は不要。

理由:

- Arctx の操作はそれ自体が append-only な履歴単位である。
- `add node`, `add step`, `attach`, `cut`, `revise` がすでに意味のある変更として記録される。
- Git の commit は「ファイル変更をまとめる」ための単位であり、Arctx の DAG 操作単位とはズレる。

Git を使うとしても、それは保存・同期・共有の実装層として扱う。

ユーザーに見せる共有操作の名前は、remote 方針が固まってから決める。

## revise step について

`revise step` は重要だが、MVP の最初の実装には入れない。

理由は、既存 Step をどう修正済みとして扱うか、つまり supersede marker / revision payload / 新 Step のどれで表現するかをまだ決める必要があるため。

当面は、修正したい場合も新しい `add step` と必要な `cut` / `attach` の組み合わせで表現する。

## Git / GitHub との関係

GitHub に載せられる強みは大きい。

ただし、Arctx の中心モデルを Git commit に寄せすぎない。

短期案:

- Arctx のデータはファイルまたは DB として保存する。
- Git 管理できる形式は維持する。
- GitHub への共有方法は、主要 DAG 操作とは分けて検討する。
- ユーザーは `arctx commit` を意識しない。

中長期案:

- Arctx Hub / GitHub App / DAG-native remote を検討する。
- ファイル差分ではなく、DAG 差分、Payload 差分、Step 履歴をレビュー対象にする。

## Extension 方針

Extension は残す。むしろ core を小さくするほど重要になる。

core:

- Node
- Step
- Payload
- RunGraph
- add node
- add step
- attach
- cut
- show / log

extension:

- custom payload type
- custom validation
- custom CLI
- custom GUI panel
- repo integration
- agent integration
- import / export
- sync backend

現行の extension 仕組みは活かせる。

改善したい点:

- extension が top-level CLI を増やしすぎると、また分かりにくくなる。
- extension CLI は原則 namespace 配下に置く。
- 日常 alias は少数にする。
- validation は当面 `show` / `log` / extension 固有 command で確認し、必要になったら `status` / `debug` に分離する。

## GUI と CLI の分担

DAG 操作は GUI の方が自然。

人間向け:

- GUI で Node を選ぶ。
- 選択 Node から Step を作る。
- Payload をフォームで追加する。
- Cut の影響範囲を視覚的に確認する。

CLI / agent 向け:

- ID で Node / Step を指定する。
- `current node` を持つ。
- `--json` 出力で構造を返す。
- `show` と `log` を組み合わせて周辺情報を取得する。

CLI は GUI の代替というより、スクリプト・agent・厳密操作の入口として設計する。

## show / log / context

MVP の確認コマンドは `show` と `log` に絞る。

`show` は 1 つの record の現在状態を見る。

```bash
arctx show n_123
arctx show s_456
arctx show pl_789
```

表示する情報:

- kind
- id
- active / inactive
- Node / Step / Payload の本体
- 付いている Payload
- Step の inputs / output
- CutPayload があればその理由

`log` は DAG の連なりを見る。

```bash
arctx log
arctx log --from n_123
arctx log --to n_456
```

`log --from` は指定 Node から下流を見る。

`log --to` は指定 Node がどう作られたかを上流へたどる。

`context` は MVP の主要 CLI には入れない。

将来、Codex / Claude Code などに渡すための agent 向け合成ビューとして追加する可能性はある。

その場合も、`context` は新しい基本操作ではなく、`show` と `log` を組み合わせた読み取り用 command として扱う。

## Codex / Claude Code からの見え方

agent からは、次のように扱えるのが理想。

```bash
arctx show current --json
arctx log --from current --depth 3 --json
arctx add step --from n_123 --title "implemented parser" --json
arctx attach n_456 --type note --field text="..." --json
arctx cut n_789 --reason "invalid assumption" --json
```

agent が必要とするのは、曖昧な表示ではなく構造化された現在状態。

そのため、`show` と `log` は JSON 出力を第一級に扱う。

## 実装移行案

### Phase 1: 表面仕様の整理

- この設計メモを元に README / docs の方向性を更新する。
- `Transition` をユーザー向けには `Step` と呼ぶ。
- `Cut` は Payload の一種だと明記する。
- `GraphView` を MVP の主要説明から外す。
- `commit` を主要概念から外す。

### Phase 2: 新 CLI の追加

- `arctx add node`
- `arctx add step`
- `arctx attach <target-id>`

既存の `transition create`, `payload add`, `graph dump` などは一旦残してよいが、主要ドキュメントでは新 CLI を前面に出す。

### Phase 3: 内部 API の整理

短期:

- 内部 class 名 `Transition` は残す。
- CLI / docs では `Step` と表示する。
- ID prefix は当面 `t_` のままでもよい。

中期:

- `Transition` -> `Step`
- `transition_id` -> `step_id`
- `TransitionPayload` -> `StepPayload`
- `target_kind="transition"` -> `target_kind="step"`

この変更は storage schema に影響するため、ベータ中にやるならまとめて実行する。

### Phase 4: GraphView の退避

- `view` CLI を非推奨または hidden にする。
- `show --from`, `log --from` を整備する。
- `RunGraph.views` を削除するか、内部互換フィールドとして残すかを判断する。

### Phase 5: remote / sharing 方針

- remote / sharing の意味を定義する。
- GitHub に置く場合、ユーザーに Git commit を意識させない設計を検討する。
- DAG-native remote は長期課題として分離する。

## 未決事項

- 内部名 `Transition` をいつ `Step` に変えるか。
- ID prefix を `t_` のままにするか、`s_` に変えるか。
- `revise step` の正確なデータモデル。
- `current node` を work-session ごとに持つか、run 全体で持つか。
- 共有機能を Git wrapper にするか、Arctx 独自 remote の抽象にするか。
- GraphView を完全削除するか、内部機能として残すか。
- GUI と CLI の責務境界。

## 現時点の推奨判断

MVP では、次の判断を採用する。

- 基本概念は Node / Step / Payload の 3 つに絞る。
- Cut は Payload の一種として扱う。
- RunGraph は保存・検証・同期の単位であり、ユーザー向けには前面に出しすぎない。
- GraphView は MVP の表面から外す。
- commit はユーザー向け主要操作から外す。
- CLI は `add node`, `add step`, `attach`, `cut`, `show`, `log` を中心にする。
- `link`, `status`, `debug`, `sync` は MVP の主要 CLI から外す。
- `context` は `show` / `log` を組み合わせた agent 向け合成ビューとして後から検討する。
- Extension は core の小ささを保つための重要機構として残す。
- Git / GitHub は共有・同期の実装層として扱い、Arctx の意味論は DAG 操作に置く。
