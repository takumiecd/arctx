# CLI

## 基本フロー

```bash
arctx init req_demo --run-id demo
arctx transition create --run demo --from <root_node_id> --payload-type transition_payload --field type=experiment --field lr=0.01
arctx payload add --run demo --node <node_id> --payload-type node_payload --field type=note --field text="observed result"
arctx cut node <node_id> --run demo --reason "不採用"
arctx graph dump --run demo --format outline
```

## コマンド一覧

- `arctx init <req_id>` — 新規 run 作成
- `arctx list` — run 一覧
- `arctx use <run_id>` / `arctx current` — active run ポインタ管理

### Node

- `arctx node show <node_id>` — Node を表示
- `arctx node payloads <node_id>` — Node の payload を表示

### Transition

- `arctx transition create --from NODE --payload-type TYPE --field key=value` — 1 Transition と 1 output Node を作成
- `arctx transition show <transition_id>` — Transition を表示
- `arctx transition output <transition_id>` — output Node を表示
- `arctx transition inputs <transition_id>` — input Node IDs を表示
- `arctx transition payloads <transition_id>` — Transition の payload を表示

複数案を作る場合は、同じ input node から `transition create` を複数回実行します。

### Payload

- `arctx payload types` — 登録済み `payload_type` を表示
- `arctx payload schema <payload_type>` — payload type の入力 field を表示
- `arctx payload add --node NODE --payload-type TYPE --field key=value` — Node に payload を追加
- `arctx payload add --transition TRANSITION --payload-type TYPE --field key=value` — Transition に payload を追加
- `arctx payload list --node NODE` / `arctx payload list --transition TRANSITION` — payload 一覧
- `arctx payload show <payload_id>` — payload を表示

### Cut / Git

- `arctx cut node <node_id>` / `arctx cut transition <transition_id>` — CutPayload を追加

git 連携は標準 extension です。正式な command namespace は `arctx git ...` で、
日常用の `arctx commit` などは default alias として残ります。

- `arctx init <req_id> --extension git` — run で git extension を有効化
- `arctx git commit -m "message"` / `arctx commit -m "message"` — git commit を駆動して Transition を記録
- `arctx git branch list` / `arctx branch list` — 記録済み branch 一覧
- `arctx git branch show <name>` / `arctx branch show <name>` — branch tip と member を表示
- `arctx git revert --sha SHA` / `arctx revert --sha SHA` — revert を駆動して記録
- `arctx git cherry-pick --sha SHA` / `arctx cherry-pick --sha SHA` — cherry-pick を駆動して記録
- `arctx git merge --other branch:<name>` / `arctx merge --other branch:<name>` — merge を駆動して記録
- `arctx git reset --node NODE --mode hard` / `arctx reset --node NODE --mode hard` — reset と current 移動を記録
- `arctx git verify` / `arctx verify` — git descendant 制約を検証
- `arctx git hook install` / `arctx hook install` — git hooks を install
- `arctx git add --transition T --commit SHA` — Transition に commit hash を紐づける
- `arctx git list --transition T` — 紐づいた commit hash を表示
- `arctx git show --transition T` — GitChangePayload を表示
- `arctx git worktree add <path> [branch] [--base REF] [--existing-branch]` — `git worktree add` の薄いラッパ。`branch` 省略時はパス末尾の名前で新規 branch を作成。
- `arctx git worktree list` — `git worktree list --porcelain` を JSON にパースして表示。
- `arctx git worktree remove <path> [--force]` — `git worktree remove` の薄いラッパ。

### Worktree attachment

- `arctx work-session start --worktree PATH` / `arctx work-session env --new --worktree PATH` / `arctx work-session spawn --worktree PATH -- <cmd>` — 解決済み worktree path (＋ current branch / `git --git-common-dir`) を `WorkSession.metadata["worktree"]` に記録し、`ARCTX_GIT_WORKTREE=PATH` を export する。
- `ARCTX_GIT_WORKTREE` 環境変数 — セットされていると、すべての git verb (`arctx git commit / revert / cherry-pick / merge / reset / verify` と post-rewrite hook) は git サブプロセスを `cwd=$ARCTX_GIT_WORKTREE` で実行する。`arctx git worktree add` と組み合わせることで、同じ ARCTX run を共有しつつ各 agent に独立した checkout を渡せる。

### Graph

- `arctx graph dump [--format outline|mermaid]` — graph を描画
- `arctx graph trace <node_id>` — 履歴を遡る
- `arctx graph reachable <node_id>` — active subgraph を表示

## 互換コマンド

`arctx show`, `arctx dump`, `arctx trace`, `arctx reachable`, `arctx outcomes` は残っていますが、新しい CLI では `node` / `transition` / `payload` / `graph` namespace を優先します。

## 廃止コマンド

`arctx plan`, `arctx predict`, `arctx observe`, `arctx note` は削除済みです。
