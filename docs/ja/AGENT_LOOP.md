# Agent Loop

## 文脈取得の 3 つの問い

エージェントが必要とする問いは 3 つだけで、それぞれに 1 コマンドが対応します。
lane はフラットなので、階層を歩く操作はどこにもありません。

| 問い | コマンド |
| --- | --- |
| いま何が起きているか | `arctx guide --context` |
| X について何が試されたか | `arctx explore --query "TERMS"` |
| ここで何が起きたか | `arctx dump` / `arctx log` / `arctx show <ID>` |

**検索が主役**です。`explore --query` は位置非依存で、current lane も降下も
不要、closed lane も等しく見つかります。ヒットには飛べる id が付くので、
`arctx show <ID>` で詳細に降りられます。lane 一覧が見たいだけなら
`arctx explore`（closed は畳まれる。`--all` で展開）。

## 推奨ループ

1. `arctx guide --context` で Run ID / Run Purpose / Current Lane
   （status・purpose・current summary）/ Active Frontiers を安価に確認する
   （毎ターン呼んでよい）。過去の試行を探すときは `arctx explore --query "..."`。
   詳しい使い方は `arctx guide`（静的ガイド + Current Context）で読む。
   `arctx log`（プレーン実行）は work event を古い順に並べた時系列ビュー
   （`git log --oneline` 相当）で、これまでの経緯を素早く読み返すのに向く。
   lane 単位の目次が欲しいときは `arctx log --lanes` を使う。
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

active な解から外す枝は削除せず `cut` します。node を別の入力に繋ぎ直すときは
`arctx reparent NODE --from NEW_INPUT`（新しい producer step を足し、旧
producer を cut する）を使います。lane ごとの最終知見は
`arctx lane close --summary "..."` に入れて閉じます。

lane が長く続くときは、途中で `arctx lane summarize <LANE> --summary "..."` を
呼んで current summary を更新してください。この summary が
`arctx explore` の 1 行表示と `explore --query` の検索対象になるので、
更新しておくほど後から見つけやすくなります。lane を作るときに
`--purpose` を付けておくのも同じ理由で効きます。

## セットアップのメンタルモデル

ARCTX には独立した 3 つの状態があります:

- **Run:** `<repo_root>/.arctx/runs/<run_id>` 配下のグラフ
  （`ARCTX_HOME` 指定時と git repo 外では `<ARCTX_HOME>/runs/<run_id>`）。
- **Repo pointer:** `<gitdir>/arctx-id`。`arctx init`, `arctx use`,
  `arctx git init` が書き込む。
- **Shell pointer:** `ARCTX_RUN_ID`。`eval "$(arctx use <run_id> --shell)"` で
  設定する（この端末だけに効き、repo pointer は書かない）。

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
`arctx git init` はこの checkout を run に紐づけ（repo pointer）、hook を
インストールします。その後は通常の `arctx git ...` コマンドが repo pointer から
run を解決できます。

## 1 Run = 1 Repo

run は 1 つのリポジトリの中に存在します。データはその repo の `.arctx/` にあり、
すべての git レコードは修飾子なしでその repo 自身を指します（「absent = self」）。
repo registry も `repo_id` もありません。

- 1 つのターミナルで checkout を移動しながら `run_x` を追うには、各 repo の pointer に
  頼らずターミナルを固定します: `eval "$(arctx use run_x --shell)"`。

## 端末ごとの固定モード

並列 agent は共有 repo pointer だけに頼るべきではありません。各プロセスの環境で
run と lane を固定します。

```bash
eval "$(arctx use run_x --shell)"            # export ARCTX_RUN_ID=run_x
arctx lane create codex --purpose "..." --user codex
eval "$(arctx lane switch codex --shell)"    # export ARCTX_LANE_ID=lane_...
export ARCTX_USER_ID=codex

arctx add --from NODE_ID --type suggestion
```

`--shell` は repo pointer を書かないので、同じ checkout の別ターミナルは別の lane を
持てます。子プロセスに別の lane を渡したいときは、環境変数を渡して起動するだけです:

```bash
ARCTX_LANE_ID=$(arctx lane show codex --json | jq -r .lane.lane_id) \
ARCTX_USER_ID=codex codex
```

`arctx add`（`--from` 省略時の frontier 解決）と `arctx guide` /
`arctx guide --context` は `ARCTX_LANE_ID` を repo pointer より優先して解決するため、
子プロセス内でもその子自身の lane が正しく見えます。

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
export ARCTX_GIT_WORKTREE=../my-repo-codex
```

`ARCTX_GIT_WORKTREE` が設定されていると、git verb は shell の cwd が別の場所でも
その worktree 内で実行されます。
