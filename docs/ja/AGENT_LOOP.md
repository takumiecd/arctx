# Agent Loop

## 推奨ループ

1. `arctx log` でコンテキストを読む。
2. `arctx add step --from NODE_ID --type suggestion --field proposal="..."` で
   意図を append する。
3. 外部作業を行う: 実装、実験、レビュー、デバッグ、リサーチなど。
4. `arctx add step --from NODE_ID --type implementation --field result="..."` で
   結果を append する。
5. 間違った枝は record を削除せず `arctx cut NODE_ID` で cut する。
6. チェックポイントでは `arctx export --format md` で成果物を生成する。受け手に
   inactive な枝を見せたくない場合は `--exclude-cut` を付ける。

fan-out は、同じ入力 Node から複数の step を作ることで表現します。multi-input
join は `--from` を複数回渡します。

各 writer が新しい record だけを append する限り、並列プロセスが同じ run で
作業できます。マージは record 単位の append であり、既存履歴の変更ではありません。

## セットアップのメンタルモデル

ARCTX には独立した 3 つの状態があります:

- **Run:** `<ARCTX_HOME>/runs/<run_id>` 配下のグラフ。
- **Repo pointer:** `<gitdir>/arctx-id`。`arctx init`, `arctx use`,
  `arctx git init`, `arctx git repo add` が書き込む。
- **Shell pointer:** `ARCTX_RUN_ID`。通常は
  `eval "$(arctx use <run_id> --shell)"` または `arctx lane env` で設定する。

解決順:

```text
--run <id>
ARCTX_RUN_ID
<gitdir>/arctx-id
```

「この checkout は通常この run に属する」には repo pointer を使います。1 つの
ターミナルが repo を移動しながら 1 つの run を追う場合や、子プロセスを他の
ターミナルから隔離したい場合は shell pointer を使います。

## Git ありの単一 Repo

```bash
cd ~/dev/my-repo
arctx init "feature X" --run-id run_x --extension git
arctx git init
arctx git commit -m "first change"
```

`arctx init --extension git` は run を作成し git 連携を有効化します。
`arctx git init` はその run に repo を明示的に登録し、repo マーカーを書き、hook を
インストールします。その後は通常の `arctx git ...` コマンドが repo pointer から
run を解決できます。

## 複数 Repo にまたがる 1 つの Run

run は git の上位に位置し、複数の repo にまたがれます。各 repo を registry に
登録すれば、どの repo の commit も同じ run の履歴に入ります。

```bash
cd ~/dev/frontend
arctx init "feature X" --run-id run_x --extension git
arctx git init

cd ~/dev/backend
arctx git repo add --run run_x
```

- commit tip の一貫性は `(repo_id, branch)` をキーにするため、異なる repo の
  同名ブランチ（2 つの `main` など）は衝突しません。
- 1 つのターミナルで repo を移動しながら `run_x` を追うには、各 repo の pointer に
  頼らずターミナルを固定します: `eval "$(arctx use run_x --shell)"`。
- `arctx export` は登録済み repo を Repos セクションに列挙します。`local_path` は
  マシン固有のパス漏洩を避けるためデフォルトで除去されます。ローカル診断には
  `--include-local` を使います。

## Work Session 固定モード

並列 agent は共有 repo pointer だけに頼るべきではありません。各プロセスの環境で
run と work session を固定します。

```bash
eval "$(arctx lane env --run run_x --new --user codex)"
arctx add step --from NODE_ID --type suggestion
```

子プロセスには `spawn` を使います。子は固有の `ARCTX_LANE_ID` を受け取り、
兄弟ターミナルや兄弟子プロセスは固定セッションを共有しません。

```bash
arctx lane spawn --run run_x --user codex -- codex
arctx lane spawn --run run_x --user claude-code -- claude
```

明示モードでは、変更系コマンドごとに `--run` と `--lane` の両方を渡します。

```bash
arctx add step --run run_x --lane ws_xxx --from NODE_ID --type implementation
```

デフォルトの attribution は `user=user`, `lane=default` です。誰がどの
record を書いたか区別したい場合は、agent ごとに `--user` または `ARCTX_USER_ID` を
設定します。

この固定モードのワークフローは同一マシン上の複数プロセスを前提とします。1 つの
run ディレクトリを NFS やクラウド同期フォルダ経由で複数マシン間で直接共有しないで
ください。公開 sync CLI は、remote/sharing モデルが固まるまで意図的に保留しています。

## Agent ごとの Worktree

並列 coding agent では、work session と git worktree を組み合わせます:

```bash
arctx git worktree add ../my-repo-codex codex/run-x --base main
arctx lane spawn --run run_x --user codex --worktree ../my-repo-codex -- codex
```

work session は worktree パスを記録し、子に `ARCTX_GIT_WORKTREE=PATH` を export
します。git verb は、shell の cwd が別の場所でも、その worktree 内で実行されます。
