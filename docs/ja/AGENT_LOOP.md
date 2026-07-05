# Agent Loop

## 推奨ループ

1. `arctx guide --context` で Run ID / Current Lane / Active Frontiers を安価に
   確認する（毎ターン呼んでよい）。詳しい使い方は `arctx log` や `arctx guide`
   （静的ガイド + Current Context）で読む。
2. `arctx add --from NODE_ID --type suggestion --field proposal="..."` で
   意図を append する。`--from` は省略可能で、その場合は現在の lane の
   active frontier（active かつ後続 step のない node）が唯一のときはそれを使う。
   run 開始直後で frontier が 0 個かつ run root がまだ未使用のときは run root
   を入力に使う（新規 run 最初の `add` が `--from` なしで成功する）。それ以外で
   frontier が 0 個または複数あるときは、候補一覧または探し方の案内を添えた
   エラーになる。
3. 外部作業を行う: 実装、実験、レビュー、デバッグ、リサーチなど。
4. `arctx add --from NODE_ID --type implementation --field result="..."` で
   結果を append する。
5. 間違った枝は record を削除せず `arctx cut NODE_ID` で cut する。
6. チェックポイントでは `arctx export --format md` で成果物を生成する。受け手に
   inactive な枝を見せたくない場合は `--exclude-cut` を付ける。

fan-out は、同じ入力 Node から複数の step を作ることで表現します。multi-input
join は `--from` を複数回渡します。

各 writer が新しい record だけを append する限り、並列プロセスが同じ run で
作業できます。マージは record 単位の append であり、既存履歴の変更ではありません。

## 並列実験の置き方

互いに独立して試せる方針は、1 つの lane で直列に試すのではなく、同じ baseline
node から fan-out します。方針ごとに lane を分け、コード変更を伴うなら git
worktree も分けるのが基本です。これは通常の git branch とは違います。ARCTX が
記録するのは code ref の移動だけではなく、「どの baseline からどの実験が分岐し、
あとでどう比較・合成されたか」という RunGraph 上の関係です。

各枝には仮説、結果、評価シグナルを残します。単体で弱い枝でもすぐ捨てないで
ください。単体では悪く見えた案が、別の枝と multi-input join したときに最良の
組み合わせになることがあります。独立実験が終わったら、有望な terminal node を
`--from` の繰り返しでまとめ、合成結果を 1 つの step として記録します。

active な解から外す枝は削除せず `cut` します。lane ごとの最終知見は
`arctx lane close --summary "..."` に入れて閉じます。

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
arctx add --from NODE_ID --type suggestion
```

子プロセスには `spawn` を使います。子は固有の `ARCTX_LANE_ID` を受け取り、
兄弟ターミナルや兄弟子プロセスは固定セッションを共有しません。`arctx add`
（`--from` 省略時の frontier 解決）と `arctx guide` / `arctx guide --context`
は、この `ARCTX_LANE_ID` 環境変数を repo pointer より優先して解決するため、
spawn された子プロセス内でもその子自身の lane が正しく見えます。

```bash
arctx lane spawn --run run_x --user codex -- codex
arctx lane spawn --run run_x --user claude-code -- claude
```

明示モードでは、変更系コマンドごとに `--run` と `--lane` の両方を渡します。

```bash
arctx add --run run_x --lane ws_xxx --from NODE_ID --type implementation
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
