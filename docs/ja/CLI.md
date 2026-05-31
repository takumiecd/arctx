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
- `arctx export [--format md|tex|html]` — run を共有用ドキュメントとして出力

### current run の解決

ミューテーション/参照コマンドが対象 run を決める順序:

```
--run <id>            その場限り（最優先）
ARCTX_RUN_ID          端末（シェル）ごと
<gitdir>/arctx-id     repo ごとの永続デフォルト
```

- `arctx use <run_id>` — `<gitdir>/arctx-id` を書く（**repo 単位・永続**。その repo に
  入る全端末に効く）。
- `arctx use <run_id> --shell` — ファイルを書かず `export ARCTX_RUN_ID=<run>` を出力。
  `eval "$(arctx use <run_id> --shell)"` で**その端末だけ**固定する。複数 repo に
  またがる run を1端末で追うときに便利（env が repo ポインタより優先）。

グローバル（PC 単位）の current ポインタは存在しない。

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
- `arctx git init` — このリポジトリを current run の対応表に登録し、hooks を install
  （内部で `git repo add` を呼ぶ。既存 run に最初の repo を紐づける入口）
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
  （※ `git repo add` とは別物。こちらは commit を Transition に貼る操作）
- `arctx git list --transition T` — 紐づいた commit hash を表示
- `arctx git show --transition T` — GitChangePayload を表示
- `arctx git worktree add <path> [branch] [--base REF] [--existing-branch]` — `git worktree add` の薄いラッパ。`branch` 省略時はパス末尾の名前で新規 branch を作成。
- `arctx git worktree list` — `git worktree list --porcelain` を JSON にパースして表示。
- `arctx git worktree remove <path> [--force]` — `git worktree remove` の薄いラッパ。

### 複数 repo（対応表 / repo registry）

1 つの run は複数の git repo にまたがれる。run は repo の**対応表**（`RepoPayload`）を
持ち、git payload は `repo_id` でそれを参照する。core は repo 非依存のまま。

- `arctx git repo add [--repo-path P] [--slug USER/REPO] [--no-hooks]` — repo を current
  run に登録（「途中で入れる」）。`RepoPayload` 追加 ＋ その repo の `.arctx-id` を
  current run に向けて書く ＋ `.arctx-repo` マーカー作成。冪等。
- `arctx git repo list` — 対応表を一覧（JSON）。
- `arctx git repo show [--repo-id ID | --repo-path P]` — 1 エントリを表示。`--repo-id`
  省略時は cwd の `.arctx-repo` マーカーで解決。

対応表エントリ: `repo_id`（opaque 主キー）/ `slug`（USER/REPO 表示名）/ `remotes`
（ssh・https など全形式）/ `canonical`（正規化キー。ssh と https を同一視）/
`local_path`（このマシンのチェックアウト先）。

`local_path` は環境依存なので、**外に出すとき（export / 共有）はデフォルトで落とす**。
`repo list` / `repo show` はローカル確認用なので表示する。

別 repo を後から足す典型:

```bash
cd ~/dev/frontend && arctx init "機能X" --run-id run_x --extension git
arctx git init                           # frontend を登録
cd ~/dev/backend  && arctx git repo add --run run_x   # backend を同じ run に登録
# 以降は各 repo で commit。tip は (repo_id, branch) キーなので両方 main でも衝突しない
```

### export（共有用ドキュメント）

`arctx export` は `dump`（検査 / LLM 向け）と別物で、人に渡す成果物を出す。

- `--format md|tex|html`（既定 `md`）
- `--exclude-cut` — cut（無効）ノード/遷移を落とす（既定は cut も残す）
- `--include-local` — repo の `local_path` を含める（既定は落とす。共有事故防止）
- `--node` / `--depth` / `--full-payloads` — `dump` と同じ走査オプション
- `--output PATH` / `-o PATH` — ファイル出力（既定は stdout）

対応表があれば Repos セクションを付けて出力する。

### Work session（並列・複数 agent）

複数の agent / 端末が同じ run を共有するときの作業単位。同時書き込みはロック付き
差分追記で安全に直列化されます。運用の詳細は `docs/ja/AGENT_LOOP.md` を参照。

- `arctx work-session start [--user U] [--work-session WS]` — work session を作成して id を表示
- `arctx work-session env [--new] [--run R] [--user U]` — `eval "$(...)"` 用に `ARCTX_RUN_ID` / `ARCTX_WORK_SESSION_ID` / `ARCTX_USER_ID` の export を出力（シェル単位の固定モード）
- `arctx work-session spawn [--user U] -- <cmd>` — 子プロセスだけに一意な work session を渡して `<cmd>`（codex / claude 等）を起動
- `arctx work-session list` / `arctx work-session show <ws_id>` — work session 一覧 / 表示

属性の解決順:

- user: `--user` → `ARCTX_USER_ID` → `<ARCTX_HOME>/config.json` の `user.id` → `user`
- work session: `--work-session` → `ARCTX_WORK_SESSION_ID` → `config.json` の `work_session.id` → `default`

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
