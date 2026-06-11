# CLI

## クイックスタート

1つの git repo で通常の git 連携 run を始める場合:

```bash
cd ~/dev/my-repo
arctx init req_demo --run-id demo --extension git
arctx git init
arctx current
arctx git commit -m "implement first step"
arctx graph dump --format outline
```

セットアップ系コマンドの役割:

- `arctx init <req_id>` は `<ARCTX_HOME>/runs` に run を作成する。
- `arctx init ... --extension git` は、その run で git extension も有効化する。
  git repo 内で実行した場合は、この repo の `<gitdir>/arctx-id` を書き、さらに
  `--no-hooks` / `--git-no-hooks` がなければ hooks を install する。
- `arctx git init` は current run の repo registry に current repo を登録し、
  repo pointer、`.arctx-repo` marker、hooks を設定する。run に明示的に紐づけたい
  repo ごとに1回実行する。
- `arctx use <run_id>` は、既存 run をこの repo の current run にするため
  `<gitdir>/arctx-id` を書く。
- `eval "$(arctx use <run_id> --shell)"` は、ファイルを書かずに
  `ARCTX_RUN_ID` を export して、この端末だけ current run を切り替える。

グローバル、つまりPC単位の current run は存在しない。

## current run の解決

多くの参照/変更コマンドは `--run` を受け取る。省略した場合、ARCTX は対象 run を
次の順で解決する:

```text
--run <id>            そのコマンドだけ（最優先）
ARCTX_RUN_ID          current shell / process tree
<gitdir>/arctx-id     この git checkout の永続デフォルト
```

使い分け:

- **その場限り:** `--run <id>` を渡す。
- **1つの repo に留まる:** その repo で `arctx use <run_id>` を1回実行する。
- **1つの端末で複数 repo を移動する:** `eval "$(arctx use <run_id> --shell)"` を使う。
  環境変数は各 repo の pointer より優先される。
- **複数 agent / 並列作業:** `arctx work-session env` または
  `arctx work-session spawn` で run と work-session を process-local な環境変数に固定する。

`arctx current` は repo pointer（`<gitdir>/arctx-id`）を読んで、その repo の永続
デフォルトを表示する。`ARCTX_RUN_ID` による上書きは表示しない。

## 基本 graph フロー

```bash
arctx init req_demo --run-id demo
arctx transition create --run demo --from <root_node_id> --payload-type transition_payload --field type=experiment --field lr=0.01
arctx payload add --run demo --node <node_id> --payload-type node_payload --field type=note --field text="observed result"
arctx cut node <node_id> --run demo --reason "不採用"
arctx graph dump --run demo --format outline
```

基本コマンド:

- `arctx init <req_id>`: run を作成。
- `arctx list`: run 一覧。
- `arctx current`: repo-scoped な current run pointer を表示。
- `arctx use <run_id>`: repo-scoped な current run pointer を書く。
- `arctx use <run_id> --shell`: shell-local 固定用の `ARCTX_RUN_ID` export を表示。
- `arctx export [--format md|tex|html]`: run を共有用ドキュメントとして出力。

## Node

- `arctx node show <node_id>`
- `arctx node payloads <node_id>`

## Transition

- `arctx transition create --from NODE --payload-type TYPE --field key=value`
- `arctx transition show <transition_id>`
- `arctx transition output <transition_id>`
- `arctx transition inputs <transition_id>`
- `arctx transition payloads <transition_id>`

各 transition は必ず1つの output node を持つ。fan-out は同じ input node から
`transition create` を複数回実行して作る。multi-input join は `--from` を複数回渡す。

## Payload

- `arctx payload types`
- `arctx payload schema <payload_type>`
- `arctx payload add --node NODE --payload-type TYPE --field key=value`
- `arctx payload add --transition TRANSITION --payload-type TYPE --field key=value`
- `arctx payload list --node NODE` / `arctx payload list --transition TRANSITION`
- `arctx payload show <payload_id>`

## Cut

- `arctx cut node <node_id>`
- `arctx cut transition <transition_id>`

cut は無効な枝を記録する。履歴は削除しない。

## Git 連携

git 連携は標準 extension。正式な command namespace は `arctx git ...` で、
日常用の `arctx commit` などは shortcut alias として残る。

extension の command namespace は、解決された current run から読み込まれる。
`arctx git ...` が見えない場合は、まず `--extension git` で作成された run を解決できる
状態にする。方法は `--run <id>` を渡す、`ARCTX_RUN_ID` を設定する、または
`<gitdir>/arctx-id` がある repo から実行する、のいずれか。

セットアップ:

- `arctx init <req_id> --extension git`: run を作成し git extension を有効化する。
  git repo 内なら `<gitdir>/arctx-id` と hooks も設定する。ただし repo registry に
  明示登録したい場合は `arctx git init` を使う。
- `arctx git init [--repo-path P] [--slug USER/REPO] [--no-hooks]`: current run に
  repo を登録し hooks を install する。「この checkout をこの run に紐づける」
  推奨コマンド。
- `arctx git repo add [--repo-path P] [--slug USER/REPO] [--no-hooks]`: 同じ登録処理の
  primitive。別 repo を既存 run に参加させるときに使う。
- `arctx git repo list`: 登録 repo を JSON で一覧。
- `arctx git repo show [--repo-id ID | --repo-path P]`: repo registry の1件を表示。

日常の git verbs:

- `arctx git commit -m "message"` / `arctx commit -m "message"`
  - 入力ノードは通常 work-session / branch tip から解決されるが、
    `--from NODE` を渡すと指定ノードから分岐できる（複数指定で fan-in）。
    共有 baseline から実験を兄弟として枝分かれさせるときに使う。
- `arctx git branch list` / `arctx branch list`
- `arctx git branch show <name>` / `arctx branch show <name>`
- `arctx git revert --sha SHA` / `arctx revert --sha SHA`
- `arctx git cherry-pick --sha SHA` / `arctx cherry-pick --sha SHA`
- `arctx git merge --other branch:<name>` / `arctx merge --other branch:<name>`
- `arctx git reset --node NODE --mode hard` / `arctx reset --node NODE --mode hard`
- `arctx git verify` / `arctx verify`
- `arctx git hook install` / `arctx hook install`

commit 紐づけ:

- `arctx git add --transition T --commit SHA`: commit hash を transition に貼る。
  `arctx git repo add` とは別物。
- `arctx git list --transition T`
- `arctx git show --transition T`

worktree helpers:

- `arctx git worktree add <path> [branch] [--base REF] [--existing-branch]`:
  `git worktree add` の薄い wrapper。`branch` 省略時は path 末尾の名前で新規 branch を作る。
- `arctx git worktree list`: `git worktree list --porcelain` を JSON に parse。
- `arctx git worktree remove <path> [--force]`: `git worktree remove` の wrapper。

## 複数 repo

1つの ARCTX run は複数の git repo にまたがれる。run は repo registry
（`RepoPayload`）を持ち、git payload は `repo_id` で repo を参照する。core graph
record は repo 非依存のまま。

典型フロー:

```bash
cd ~/dev/frontend
arctx init "機能X" --run-id run_x --extension git
arctx git init

cd ~/dev/backend
arctx git repo add --run run_x
```

以後、どちらの repo の commit も同じ run に積まれる。branch tip は
`(repo_id, branch)` で管理されるため、`frontend/main` と `backend/main` は衝突しない。

registry entry の fields:

- `repo_id`: run に保存される opaque primary key。
- `slug`: `USER/REPO` のような表示名。
- `remotes`: 検出された remote URL 全形式。
- `canonical`: SSH / HTTPS 形式を同一視する正規化 remote key。
- `local_path`: このマシン上の checkout path。

`local_path` は環境依存。`arctx export` ではデフォルトで落とす。
`arctx git repo list` と `arctx git repo show` はローカル確認用なので表示する。

## Work Sessions

work session は、同じ run で並列作業する agent / terminal の attribution 単位。
変更系CLIコマンドは lock 下で append するため、同時 writer は既存履歴を上書きせず、
新規 record の追記として直列化される。

- `arctx work-session start [--user U] [--work-session WS]`: work session を作成して id を表示。
- `arctx work-session env [--new] [--run R] [--user U]`: `ARCTX_RUN_ID`,
  `ARCTX_WORK_SESSION_ID`, `ARCTX_USER_ID` の shell exports を表示。
- `arctx work-session spawn [--user U] -- <cmd>`: child-only な work session で子コマンドを実行。
- `arctx work-session list` / `arctx work-session show <ws_id>`: work session を確認。

固定モードの例:

```bash
eval "$(arctx work-session env --run run_x --new --user codex)"
arctx transition create --from NODE_ID --payload-type transition_payload --field type=suggestion
```

spawn の例:

```bash
arctx work-session spawn --run run_x --user codex -- codex
arctx work-session spawn --run run_x --user claude-code -- claude
```

attribution の解決順:

- user: `--user` -> `ARCTX_USER_ID` -> `<ARCTX_HOME>/config.json` の `user.id` -> `user`
- work session: `--work-session` -> `ARCTX_WORK_SESSION_ID` ->
  `<ARCTX_HOME>/config.json` の `work_session.id` -> `default`

## Claude Code 連携（hooks adapter）

`arctx claude-code` は Claude Code の hooks からセッションを自動記録するアダプタ。
手動の記録操作なしで、エージェントの行動が run に落ちる。

```bash
arctx claude-code install        # .claude/settings.json に hook entries を冪等マージ
arctx claude-code install --print  # 書き込まずに hooks JSON snippet を表示
```

構造は二層: 記録の意味論はハーネス中立な `arctx.ext.agents.SessionRecorder`
（payload type は `agent.prompt` / `agent.tool_use` / `agent.stop` /
`agent.session_end`、ハーネス名は payload metadata の `harness`）が持ち、
`arctx.ext.claude_code` は hook event JSON をそこへ翻訳する薄い adapter。
別ハーネス（Codex 等）の対応は翻訳器を足すだけで、保存される語彙は共通になる。

記録のマッピング:

- 1 Claude Code セッション → 1 WorkSession（`ws_cc_<session_id>`、transcript_path
  等を `metadata["agent"]` に保持）
- `UserPromptSubmit` → Transition + `TransitionPayload(type="agent.prompt")`
- `PostToolUse` → Transition + `TransitionPayload(type="agent.tool_use")`
  （既定 matcher は `Write|Edit|MultiEdit|NotebookEdit|Bash`。`--matcher` で変更）
- `Stop` / `SessionEnd` → セッション先端 node への `NodePayload(type="agent.stop" / "agent.session_end")`

各セッションの transition はそのセッションの先端（最後に作った transition の
output node）に連鎖し、並列セッションは root からの sibling 枝として fan-out する。
先端は work events から読み取り時に導出されるため、状態ファイルは持たない。
cut 済みの枝は自動でスキップされる。

`arctx claude-code hook` が hook 本体で、stdin から hook event JSON を 1 件読む。
fail-safe が既定: run が未解決・JSON 不正・store エラーでも exit 0 で no-op し、
Claude Code を決してブロックしない（デバッグには `--strict`）。stdout には何も
出力しない（`UserPromptSubmit` では stdout がモデルの context に注入されるため）。

- run の解決は他コマンドと同じ（`--run` → `ARCTX_RUN_ID` → `<gitdir>/arctx-id`）。
- user attribution の最終 fallback だけ `user` ではなく `claude-code`。
- `--tools A,B`: hook 側でも PostToolUse を tool 名でフィルタ（一次フィルタは
  settings.json の matcher）。
- 長大な tool 出力は payload 上で clip される（全文は transcript 側に残る）。

`install` のオプション:

- `--command CMD`: 書き込む hook コマンドを上書き（既定 `arctx claude-code hook`）。
  PATH の `arctx` が古い／無い環境では絶対パスを渡す（dev では
  `scripts/arctx claude-code hook`）。install は PATH 上のコマンドが
  `claude-code` subcommand を持つか best-effort で検査し、ダメなら警告を出す
  （hook 自体はフェイルセーフで無言 no-op になるため、ここで気づかせる）。
- 冪等判定はコマンド文字列中の `claude-code hook` マーカーで行うので、
  絶対パスに書き換えた後の再 install でも重複しない。

## Worktree attachment

- `arctx work-session start --worktree PATH`
- `arctx work-session env --new --worktree PATH`
- `arctx work-session spawn --worktree PATH -- <cmd>`

これらは解決済み worktree path を `WorkSession.metadata["worktree"]` に記録し、
`ARCTX_GIT_WORKTREE=PATH` を export する。

`ARCTX_GIT_WORKTREE` が set されている場合、git verbs（`arctx git commit`, `revert`,
`cherry-pick`, `merge`, `reset`, `verify`, post-rewrite hook）は shell cwd ではなく
`cwd=$ARCTX_GIT_WORKTREE` で git subprocess を実行する。`arctx git worktree add` と
組み合わせると、各 agent に独立 checkout を渡しつつ、1つの ARCTX run を共有できる。

## Export

`arctx export` は `dump` とは別物。`dump` は検査 / LLM context 用で、`export` は人に
渡す artifact を作る。

- `--format md|tex|html`（既定 `md`）
- `--exclude-cut`: cut 済み node / transition を落とす。
- `--include-local`: repo の `local_path` を含める。
- `--node` / `--depth` / `--full-payloads`: `dump` と同じ traversal options。
- `--output PATH` / `-o PATH`: stdout ではなくファイルへ書く。

repo が登録されている場合、export には Repos section が含まれる。

## Graph

- `arctx graph dump [--format outline|mermaid]`
- `arctx graph trace <node_id>`
- `arctx graph reachable <node_id>`

互換コマンドとして `arctx show`, `arctx dump`, `arctx trace`, `arctx reachable`,
`arctx outcomes` は残っている。新しい使い方では `node`, `transition`, `payload`,
`graph` namespace を優先する。

削除済みコマンド: `arctx plan`, `arctx predict`, `arctx observe`, `arctx note`。
