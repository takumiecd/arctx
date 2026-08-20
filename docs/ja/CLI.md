# CLI

## クイックスタート

1 つの repo での通常の git ベース run:

```bash
cd ~/dev/my-repo
arctx init req_demo --run-id demo --extension git
arctx git init
arctx current
arctx git commit -m "implement first step"
arctx dump --format outline
```

これらのセットアップコマンドの意味:

- `arctx init <req_id>` は `<repo_root>/.arctx/runs` 配下に run を作成します
  (git-native ストレージ: run データはリポジトリの中に置き、共有は git に委ねます)。
  同時に `<repo_root>/.arctx/.gitattributes`（`* linguist-generated=true` と
  `*.jsonl merge=union`）と `.arctx/.gitignore`（`run.cache.pkl` などの
  派生ファイルを除外）を冪等に書き込みます。除外してよいのは**消しても再生成できる
  ものだけ**です（書き込み先を除外すると、その記録が commit に入らなくなる）。
  `ARCTX_HOME` が設定されている場合、または git repo の外で実行した場合は
  従来どおり `<ARCTX_HOME>/runs` が使われます。`--store-dir` で明示指定も可能です。
- `arctx init ... --extension git` はその run の git extension も有効化します。
  git repo 内で実行すると、この repo の `<gitdir>/arctx-id` を書き込み、
  `--no-hooks` / `--git-no-hooks` を指定しない限り hook をインストールします。
- `arctx git init` はこの checkout を run に紐づける repo pointer を書き、
  hook をインストールします。
- `arctx use <run_id>` は `<gitdir>/arctx-id` を書き込み、現在の repo を既存の run に
  切り替えます。
- `eval "$(arctx use <run_id> --shell)"` は `ARCTX_RUN_ID` を export して現在の
  ターミナルだけを切り替えます。ファイルは書きません。

マシン全体でグローバルな current run はありません。

## Current Run の解決

ほとんどの参照/変更コマンドは `--run` を受け取ります。省略した場合、ARCTX は
対象 run を次の順で解決します:

```text
--run <id>            そのコマンドだけ（最優先）
ARCTX_RUN_ID          current shell / process tree
<gitdir>/arctx-id     この git checkout の永続デフォルト
```

モードを意図的に使い分けます:

- **単発コマンド:** `--run <id>` を渡す。
- **1 つの repo に留まる:** その repo で `arctx use <run_id>` を 1 回実行する。
- **1 つのターミナルで複数 repo を移動する:**
  `eval "$(arctx use <run_id> --shell)"` を実行する。環境変数が各 repo の pointer に
  優先します。
- **並列 agent:** run と lane の両方を process ローカルな環境変数に固定します。
  既存 lane には `eval "$(arctx lane switch <name> --shell)"` を使います。

`arctx current` は repo pointer (`<gitdir>/arctx-id`) を読み、その repo の永続
デフォルトを表示します。`ARCTX_RUN_ID` の上書きは報告しません。

## 基本のグラフフロー

```bash
arctx init req_demo --run-id demo
ROOT=$(arctx show --run demo | jq -r .root_node_id)
STEP=$(arctx add --run demo --from "$ROOT" --type experiment --field lr=0.01 | jq -r .id)
NODE=$(arctx show "$STEP" --run demo | jq -r .step.output_node_id)
arctx attach "$NODE" --run demo --type note --field text="observed result"
arctx cut "$NODE" --run demo --reason "discarded"
arctx log --run demo
```

コアコマンド:

- `arctx init <req_id>`: run を作成する。
- `arctx list`: run を一覧する。
- `arctx current`: repo スコープの current run pointer を表示する。
- `arctx use <run_id>`: repo スコープの current run pointer を書き込む。
- `arctx use <run_id> --shell`: shell ローカル固定用の `ARCTX_RUN_ID` export を
  出力する。
- `arctx lane create <name> [--purpose "なぜこの lane があるか"]`: run に lane を
  作成する。切替はしない。`--purpose` は lane record に記録され、
  `arctx explore <LANE>` と `arctx guide --context` が表示する。
- `arctx lane switch <name-or-id>`: 既存 lane に切り替え、repo スコープの
  current lane pointer を書き込む。存在しない名前はエラー。
- `arctx lane <name-or-id>`: `switch` の省略形。typo 防止のため自動作成しない。
- `arctx lane close <name-or-id> --summary "..." [--summary-format markdown|html|text]`: lane を閉じる。
  要約は必須で、lane の末端に付ける（leaf が 1 つならその leaf に刻む。複数なら
  1 つの収束 node にまとめる）ので、結論は別 step を作らず `--summary` に入れる。
  format は既定が markdown。必要なら sanitized HTML や plain text も指定できる。
  `--reason` で理由を記録、`--node` で対象 leaf を明示できる。
  `arctx dump` では、closed lane は通常この closing summary を持つ 1 行に折りたたまれる。
  閉じた lane への書き込みは拒否される。（`arctx lane join` は本コマンドの deprecated エイリアス。）
  `--summary` を省略すると、`arctx lane close <name-or-id> --summary "<your findings>"`
  という実行すべき正確なコマンドを添えたエラーになる。
- `arctx lane open <name-or-id>`: 閉じた lane を開き直して作業を再開する。`close` と対称。
- `arctx lane summarize <name-or-id> --summary "..." [--summary-format ...] [--node ID]`:
  lane を閉じずに **current summary を更新**する。`lane close` の作業途中版で、
  lane は open のまま書き込み可能。summary は append-only で、最新が勝つ。
- `arctx lane list` / `arctx lane show <name-or-id>`: lane を検査する。
- `arctx lane summaries <name-or-id>`: lane の active な末端 node に付いた
  `SummaryPayload` を列挙する。分岐した lane では複数返る。
- `arctx export [--format md|tex|html]`: run を共有可能なドキュメントとして描画する。

## arctx explore

lane はフラット（木ではない）なので、explore に「降りる」操作はありません。
取得系が答える 3 つの問いのうち 2 つを担当します。

- `arctx explore`: lane を 1 行ずつ列挙する（status マーカー / 名前 /
  current summary の 1 行折りたたみ、約 160 文字で切り詰め）。
  **open な lane を先に**（`started_at` 順）並べ、closed は
  `N closed lanes — use --all` の 1 行に畳む。`--all` で closed も表示する。
  `git branch` がノイズを隠すのと同じ発想。
- `arctx explore <LANE>`: その lane の overview。purpose / 完全な current summary /
  status / 直接所有する record 数 / active frontier。名前でも id でも引ける。
- `arctx explore --query "TERMS"`: **取得系の主役**。lane 名・lane の purpose・
  その lane が所有する全 payload を対象に、空白区切りの語を
  大文字小文字を無視した AND で検索する。ヒットごとに lane 名 + status、
  最初の語の周辺約 180 文字の抜粋、そして `arctx show` で飛べる
  record / payload id を出す。名前一致を先に並べる。
  **位置非依存**: current lane も降下も不要で、closed lane も等しく見つかる。
- `--json` は 3 モードすべてで使える。

抜粋には opaque id（`pl_` / `n_` / `t_`）を含めない。id を既に持っているなら
検索ではなく `arctx show <ID>` を使う。

current summary の意味論: lane が所有する `SummaryPayload` のうち、
`WorkEvent.created_records`（append-only 台帳）の順で**最後のものが勝つ**。
jsonl の行順ではなくイベント順を使うのは、union マージ後も順序が壊れないため。

## arctx guide

`arctx guide` の静的本文は「書き込みの 3 動詞」（lane を開く → `add` →
summary 付きで close）と「取得の 3 つの問い」に絞ってあります。ガイドの長さは
認知負荷の予算なので、削除済みサーフェス（lane 階層・独自 sync・コピー型 asset）
への言及は持ちません。

- `arctx guide`: 使い方の静的ガイドに加えて、動的な Current Context
  （Run ID / Run Purpose / Current Lane（status・purpose・current summary）/
  Active Frontiers in Lane / 有効な extension 名）を表示する。
  lane が木でなくなったので祖先チェーンは出さない。
  lane の解決順序は他の変更コマンドと同じ（`--lane` > `ARCTX_LANE_ID` > repo pointer）。
  context の解決に失敗しても exit code は常に 0 で、
  `## Current Context` の下に `(context unavailable: <例外型>: <メッセージ>)` という
  可視のメモを出す（黙って握りつぶさない）。
- `arctx guide --context`: 静的ガイド本文を省略し、動的な Current Context だけを表示する。
  agent が毎ターン安価に呼べるように設計されている。

## DAG Records

- `arctx add --from NODE --type TYPE --field key=value`: step とその出力 node を
  追加する。node は step の出力（または run root）としてのみ生まれる。
  `--from` は省略可能で、省略すると現在の lane の active frontier
  （lane 内で active かつ後続 step を持たない node）が唯一のときはそれを入力に使う。
  frontier が 0 個で、かつ run root がまだどの step からも参照されていない
  （run 開始直後の状態）ときは run root を入力に使う。それ以外で frontier が
  0 個または複数ある場合は、候補 node 一覧（複数のとき）または `arctx guide
  --context` / `arctx dump` で node を探す案内（0 個のとき）を添えてエラーに
  なる。
- `arctx attach <node-or-step-id> --type TYPE --field key=value`: payload を attach する。
- `arctx attach NODE --payload-type diagram --json '{"title":"retry loop","format":"mermaid","source":"flowchart TD\n  fetch --> retry\n  retry --> fetch"}'`: `diagram` extension が有効な run で、循環可能な図・モデル artifact を attach する。
- `arctx show <node-or-step-or-payload-id>`: 1 件の record を付随 payload とともに見る。

各 step はちょうど 1 つの出力 node を持ちます。同じ入力 node から `add` を
複数回実行すると fan-out になります。`--from` を繰り返し渡すと multi-input join に
なります。1 つの node は複数 step の出力になり得ますが、active なのは常に1つです
（下記 reparent を参照）。

`arctx attach` で要約（context snapshot）を付ける場合は `SummaryPayload` を使います:

- `arctx attach <node> --payload-type summary --field text="ここまでの要約"`: node に
  要約を attach する（記述的・単調で、下流の妥当性は変えない）。
- `arctx log --to <node> --from-summary`: 後ろ向き履歴を「直近の summary ＋それ以下」
  に切り詰める（LLM 引き継ぎ用の context 圧縮）。
- `arctx lane summaries <lane>`: lane の現在の結論候補として、lane 末端 node 上の
  summary を見る。

## Asset（git オブジェクト参照）

- `arctx asset attach <TARGET_ID> <PATH> [--commit REF] [--title TEXT]`
- `arctx asset show <PAYLOAD_ID>`

asset は**コピーではなく参照**です。`(commit, path)` の組だけを記録し、実体は git が
持ちます。`PATH` はリポジトリルート相対（cwd 相対・絶対パスも受理して正規化）で、
**ファイルでもディレクトリでも構いません**（git には tree があるため）。`--commit`
省略時は HEAD。repo 指定はありません — 対象は run データを包むリポジトリ自身です。

```bash
git add results/plot.png && git commit -m "add plot"   # 先に commit する
arctx asset attach "$NODE" results/plot.png            # HEAD:results/plot.png
arctx asset attach "$STEP" bench/out --commit v0.3.1   # ディレクトリ ＋ tag 指定
```

- 未 commit のパスや存在しない commit は attach 時に**拒否**されます
  （`git cat-file` で実在検証するため、壊れた参照は最初から作れません）
- commit がどの remote-tracking ref にも含まれない場合は stderr に `warning: ...` を
  出しますが**ブロックはしません**（push し忘れ・remote 無しの検知）
- `arctx asset show` は参照と、この clone で解決するか（`found` / `missing_commit` /
  `missing_path` / `no_repository`）を返すので、壊れた参照を診断できます
- 巨大バイナリは git-lfs を使ってください（arctx 側では扱いません）

## Trial テーブル（optimize 拡張）

スコア付き試行の記録と比較。`arctx ext enable optimize`（または
`arctx init --extension optimize`）で有効化します。

- `arctx trial add --table NAME [--table NAME ...] [--col K=V ...] --metric K=V [--metric K=V ...] [--from NODE] [--title TEXT]`
- `arctx trials` — run 内のテーブル一覧（名前・行数・列と型）
- `arctx trials NAME [--sort COL] [--desc] [--best [min:|max:]COL] [--json]`

trial は「試した config + 出てきた metrics」を持つ 1 Step です（`--from` 省略時は
`add` と同じく current lane の単一 active frontier）。**テーブルの record は存在しません**
— テーブルとは行たちが共有する名前で（lane 名や git の branch 名と同じ扱い）、
どんなテーブルがあるか・列・列の型・best はすべて読み取り時に行から導出します
（「jsonl は事実、見た目は導出」）。

- 初めての名前を `--table` に書くとテーブルが誕生し、新しいキーを書くと列が育ちます
  （どちらも `notice:` で通知）。事前のスキーマ宣言は不要です
- ただし**列の型（number / bool / str）は最初に書いた行が固定**します。以後の型違いは
  書き込み前にエラーで拒否されるので、表のソートや `--best` は壊れません
- 型を汚した行は `arctx cut step <id>` で inactive にすれば列の型が解放されます
  （append-only な消しゴム）
- 1 つの trial は複数テーブルに所属できます（`--table` を繰り返す）。所属は各行が
  自分で持つので、後から行を足しても他の record には触れません
- CLI を通らず書かれた不適合行は表示時に隔離されます（黙って列に混ぜません）

```
$ arctx trial add --table tile-sweep --col tile=32 --metric latency_ms=1.87
notice: new table "tile-sweep" (columns: tile, latency_ms)
$ arctx trials tile-sweep --best min:latency_ms
best (min latency_ms = 1.87): t_xxx  trial tile=32
```

## Topic（意味の束）

lane が「作業の束」、table が「数値の束」なら、topic は「**意味の束**」。任意の
node / step に topic 名を付けて、グラフ全体を横断する視点を導出します。record
は増えません（generic payload の `type="tag"` / `type="topic_summary"` のみ）。

- `arctx topic tag NAME ID [ID ...] [--note TEXT]` — record を topic に所属させる。
  **繋がっていない record 同士でも OK** — むしろそれを見つけるための機能
- `arctx topic summarize NAME --summary TEXT [--source ID ...]` — topic の現在の
  結論文（強いタグ）。同名は最新が勝ち、履歴は残る。`--source` は根拠 record
  （実在検証あり）。既定では current lane の frontier node に付く（`--on` で指定）
- `arctx topic NAME` — 現在サマリ + tag 済み record を**島**（active グラフ上の
  連結成分）ごとに表示。島が2つ以上 = 「同じ話なのに未結合」の合図で、繋ぐなら
  `arctx add --from A --from B`（判断は人間/エージェントに残す）
- `arctx topics` — 一覧（名前 / record 数 / 島数 / サマリ一行）
- `arctx guide --context` に上位 topic の現在サマリが出るので、エージェントは
  確定知識を積んだ状態で作業を開始できる

## Reparent（付け替え）

- `arctx reparent <node_id> --input NODE [--input NODE ...] --type TYPE [--reason ...]`

誤った入力から生成した node を、子孫を保持したまま正しい入力へ繋ぎ直します。
新しい producing step を append し、それまで active だった producer を cut するので、
node は常に active な producer を高々1つだけ持ちます。誤った lineage は削除されず
inactive として残ります。`--input` は付け替え先（`node_id` と同一 lane に置くこと）。

## Cut

- `arctx cut <node_id>`
- `arctx cut step <step_id>`

cut は inactive な枝を記録します。履歴は削除しません。

## Uncut（cut の取り消し）

- `arctx uncut <node_id>` / `arctx uncut step <step_id>`

cut を append-only に打ち消します（`UncutPayload` を追記、元の cut は削除しない）。
有効状態は「最後の cut/uncut が勝つ」で算出。step の uncut は output node に active
producer が2つできる場合は拒否されます（reparent で cut した旧 producer の復活防止）。

## Git 連携

Git 連携は標準 extension です。正準のコマンド名前空間は `arctx git ...` で、
`arctx commit` などのショートカット alias も日常利用のために残しています。

extension のコマンド名前空間は、解決された current run からロードされます。
`arctx git ...` が見えない場合は、まずコマンドが `--extension git` で作成された run を
解決できることを確認してください: `--run <id>` を渡す、`ARCTX_RUN_ID` を設定する、
または `<gitdir>/arctx-id` を持つ repo から実行します。

セットアップコマンド:

- `arctx init <req_id> --extension git`: run を作成し git extension を有効化する。
  git repo 内では `<gitdir>/arctx-id` も書き hook をインストールする。
- `arctx git init [--repo-path P] [--no-hooks]`: この checkout を現在の run に
  紐づけ、hook をインストールする。

日常の git verb:

- `arctx git commit -m "message"` / `arctx commit -m "message"`
  - 入力 node は通常 lane / branch tip から解決されます。代わりに選んだ node
    から分岐するには `--from NODE` を渡します（fan-in には繰り返す）。これが実験を
    共有ベースラインから兄弟として fan-out させる方法です。
- `arctx git branch list` / `arctx branch list`
- `arctx git branch show <name>` / `arctx branch show <name>`
- `arctx git revert --sha SHA` / `arctx revert --sha SHA`
- `arctx git cherry-pick --sha SHA` / `arctx cherry-pick --sha SHA`
- `arctx git merge --other branch:<name>` / `arctx merge --other branch:<name>`
- `arctx git reset --node NODE --mode hard` / `arctx reset --node NODE --mode hard`
- `arctx git verify` / `arctx verify`
- `arctx git hook install` / `arctx hook install`

commit 添付コマンド:

- `arctx git add --step T --commit SHA`: commit ハッシュを step に attach する。
- `arctx git list --step T`: attach 済み commit ハッシュを列挙する。
- `arctx git show --step T`: git_change record と、その `derived` ブロック
  （**閲覧時に git から導出**した subject / author / date / diff stat /
  変更ファイル一覧）を出す。

`GitChangePayload` が持つ事実は commit ハッシュ（`head_commit` と `commits`）と
`branch` だけです（「jsonl は事実、見た目は導出」）。diff テキスト・commit log は
記録せず、表示のたびに `arctx.ext.git.derive` が git から読み直します。
参照先 commit がこの clone に無い場合（shallow clone / push 忘れ）は失敗せず、
`available: false` と `(commit not available locally)` マーカーを返します。
導出する diff は `.arctx/**` を除外します（commit N の記録は commit N+1 に乗る
仕様なので、run データ自体は「レビュー対象の変更」ではないため）。

Worktree ヘルパー:

- `arctx git worktree add <path> [branch] [--base REF] [--existing-branch]`:
  `git worktree add` の薄いラッパー。`branch` を省略するとパス末尾の名前で新しい
  ブランチを作成する。
- `arctx git worktree list`: `git worktree list --porcelain` を JSON parse する。
- `arctx git worktree remove <path> [--force]`: `git worktree remove` のラッパー。

## arctx log

`arctx log`（プレーン実行）は run の**時系列**ビューです。`git log --oneline`
のように、work event（`WorkEvent`、`seq`/`created_at` を持つ append-only
チョノロジー記録）を古い順に 1 行ずつ並べます:

```text
[seq] <YYYY-MM-DD HH:MM> <lane名> <user> <step/payload のタイトルか summary>
```

- node/step/payload 自体には timestamp がありません（metadata は空）。
  時系列は `work_events.jsonl` の `seq`/`created_at` が担います。タイトルは
  `arctx dump` と同じソース（step/node の payload content の `title`/`text`、
  無ければ `type`）から取ります。
- `--lanes`: record 単位ではなく lane 単位のフェーズ年表を表示する。
  `started_at` 順に 1 lane 1 行（name, started_at, closed_at または `open`、
  close summary の先頭行）。run の「目次」として使う。
- `--outline`: 以前の spanning-tree outline 表示（`arctx dump --format outline`
  相当）にフォールバックする。`--node`/`--depth`/`--full-payloads` はこちらの
  モードでのみ効く。`--from NODE` / `--to NODE [--from-summary]` を渡した
  場合も自動的にこちらへ切り替わる（`--to` は引き続き `trace` の JSON 結果を返す）。
- work event が 1 件もない run（古いデータ、または `user_id`/`lane_id` を渡さず
  書き込まれた run）では、時系列の代わりに storage の挿入順にフォールバックし、
  その旨をヘッダ行に明記する。
- `--limit N`（デフォルト 200）と `--reverse`（新しい順）。

```bash
arctx log --run demo              # 時系列（古い順）
arctx log --lanes --run demo      # lane 年表（目次）
arctx log --outline --run demo    # 旧来の spanning-tree outline
```

## Dump

`arctx dump` は検査と LLM コンテキスト用に run 全体を軽量表示します。

- `--format outline|mermaid`（デフォルト `outline`）。
- `--node NODE` / `--depth N`: 表示する部分木を制限する。
- `--full-payloads`: payload 内容を通常より多く表示する。
- closed lane はデフォルトで `closed lane ...` の 1 行に折りたたまれ、`lane close`
  時の summary が表示される。内部の node/step まで見たい場合は
  `--expand-closed-lanes` を指定する。

## Work Sessions

work session は、同じ run で並列に作業する agent やターミナルの attribution 単位
です。変更系 CLI コマンドはロックの下で append するため、並行 writer は既存履歴を
上書きせず新しい record を直列化します。

- `arctx lane start [--user U] [--lane WS]`: work session を作成し
  その id を表示する。
- `arctx lane env [--new] [--run R] [--user U]`: `ARCTX_RUN_ID`,
  `ARCTX_LANE_ID`, `ARCTX_USER_ID` の shell export を出力する。
- `arctx lane spawn [--user U] -- <cmd>`: 子専用の work session で子コマンドを
  実行する。
- `arctx lane list` / `arctx lane show <ws_id>`: work session を検査する。

固定モードの例:

```bash
eval "$(arctx lane env --run run_x --new --user codex)"
arctx add --from NODE_ID --type suggestion
```

spawn の例:

```bash
arctx lane spawn --run run_x --user codex -- codex
arctx lane spawn --run run_x --user claude-code -- claude
```

attribution の解決:

- user: `--user` -> `ARCTX_USER_ID` -> `<ARCTX_HOME>/config.json` の `user.id` -> `user`
- work session: `--lane` -> `ARCTX_LANE_ID` ->
  `<ARCTX_HOME>/config.json` の `lane.id` -> `default`

## Worktree の Attach

- `arctx lane start --worktree PATH`
- `arctx lane env --new --worktree PATH`
- `arctx lane spawn --worktree PATH -- <cmd>`

これらのコマンドは解決済みの worktree パスを
`Lane.metadata["worktree"]` に記録し、`ARCTX_GIT_WORKTREE=PATH` を export
します。

`ARCTX_GIT_WORKTREE` が設定されていると、git verb (`arctx git commit`, `revert`,
`cherry-pick`, `merge`, `reset`, `verify`、および post-rewrite hook) は git
サブプロセスを shell cwd ではなく `cwd=$ARCTX_GIT_WORKTREE` で実行します。
`arctx git worktree add` と併用して、1 つの ARCTX run を共有しつつ各 agent に独立した
checkout を与えます。

## Export

`arctx export` は `dump` とは別物です: `dump` は検査と LLM コンテキスト用、`export` は
人に渡す成果物を生成します。

- `--format md|tex|html|json`（デフォルト `md`）。`md/tex/html` は人向けの spanning-tree
  アウトライン。`json` は GUI 向けの機械可読データ契約で、node/step/payload を全件
  そのまま出力する（GUI 側が DAG を自前描画できる）。cut の伝播は core 側で事前計算され、
  各 node/step に `inactive` フラグとして付与される。
- `--exclude-cut`: cut された node/step を除外する。
- `--node` / `--depth` / `--full-payloads`: `dump` と共通の走査オプション。
- `--output PATH` / `-o PATH`: stdout ではなくファイルに書く。

## Serve

`arctx serve` は 1 つの run を読み書きできるローカル HTTP API として公開します。
GUI の live モード用バックエンドです（共有用の静的 JSON とは別物）。標準ライブラリ
（`http.server`）のみで動き、追加インストール不要・CORS 対応です。

- `GET /run` — `export --format json` と同じデータ契約（全 node/step/payload、`lane_edge_summaries`）に加え、live API の現在 lane（`current_lane_id` / `current_lane_name`）を返す。
- `POST /step` — `{ "input_node_ids": [...], "type": ..., "content": {...} }` で Step を作成（出力 node も同時に生成）。
- `POST /attach` — `{ "target_id": ..., "target_kind": "node"|"step", "type": ..., "content": {...} }` で node/step に payload を付与（`target_kind` 省略時は id から自動判定。旧 `node_id` も受理）。
- `POST /cut` — `{ "target_id": ..., "target_kind": "node"|"step", "reason": ... }` で cut。
- `POST /uncut` — `{ "target_id": ..., "target_kind": "node"|"step", "reason": ... }` で cut を取り消す（append-only な反転）。
- `POST /reparent` — `{ "node_id": ..., "input_node_ids": [...], "type": ..., "reason": ... }` で node を新しい入力へ付け替え（新 step を append ＋旧 producer を cut）。新しい step を返す。
- `POST /lane` — `{ "name": ..., "metadata": {...} }` で lane を作成。
- `GET /health` — 死活確認。

Asset 読み出しはリクエスト時に git を叩いて解決します（いずれも `payload_id` 必須。
`path` は asset 自身の path からの相対で、ディレクトリ asset のブラウズに使う）:

- `GET /asset?payload_id=pl_x` — 参照 ＋ `resolution{status,kind,content_type}`。
- `GET /asset/entries?payload_id=pl_x[&path=sub]` — tree の直下エントリ一覧。
- `GET /asset/content?payload_id=pl_x[&path=sub]` — ファイル内容（`encoding` が
  `utf-8` か `base64`。バイナリ安全）。
- `GET /asset/raw?payload_id=pl_x[&path=sub]` — 生バイト（`<img src>` 用）。

解決できない参照は crash せず `{"error": ..., "code": ...}` を返します
（404: `missing_commit` / `missing_path` / `unknown_payload` / `no_repository`、
400: `not_a_blob` / `not_a_tree` / `not_an_asset` / `bad_path`）。

書き込み系は `arctx add` / `arctx cut` / `arctx reparent` と同じ verb・同じ永続化経路を
通るため、CLI と API が記録方法でズレることはありません。

- `--host`（デフォルト `127.0.0.1`）/ `--port`（デフォルト `8787`）
- `--cors-origin`（デフォルト `*`）: 別オリジンのフロント開発サーバから叩けるようにする。
- `--run` / `--store-dir` / `--user` / `--lane`: 他の変更系コマンドと共通。

## Graph

- `arctx graph dump [--format outline|mermaid]`
- `arctx graph trace <node_id>`
- `arctx graph reachable <node_id>`

`arctx dump` が正準の run 全体レンダラーで、`arctx graph dump` は `graph`
名前空間下の同等物です。
トップレベルの `trace`, `reachable`, `outcomes` は未登録です。`arctx log --to`,
`arctx graph trace`, `arctx graph reachable`, `arctx show` を使ってください。

削除されたコマンド: `arctx plan`, `arctx predict`, `arctx observe`, `arctx note`。
未登録の旧 plumbing コマンド: `arctx node`, `arctx step`, `arctx payload`,
`arctx trace`, `arctx reachable`, `arctx outcomes`。
