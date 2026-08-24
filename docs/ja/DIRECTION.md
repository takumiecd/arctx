# Direction

正準のグラフモデルは現在次の通りです:

```text
Node -> Step -> Node -> Step -> Node
```

専用の step record 型はありません。Payload が素の `Step` に意味を付与します。

コアは standalone で git に依存しません。Git 連携は `arctx.ext.git` 配下の
標準 extension で、正準 CLI は `arctx git <verb>`、一般的なワークフロー向けに
`arctx verify` のデフォルト alias があります。

ARCTX の本体は記録です。CLI は LLM agent 向けの記録プロトコル、Web は
記録を読み返すための補助的なレビュー面として役割を分けます。Web の入口は
DAG そのものではなく、current lane の現在サマリと直近の work event を一望
する Overview とします。lane に active frontier が複数あれば単一の現在地を
捏造せず、候補を並べます。DAG は詳細な経緯を調べる Graph ビューとして残し、
focus した node / step の payload 詳細のみを表示します。

ARCTX は plan や完了条件を所有しないため、根拠のない進捗率は表示しません。
現在位置は root からの path depth、直近 summary からの step 数、frontier か
history 上か、lane の active frontier 数という構造的な事実で表します。

Overview と Graph の両方で Explorer を常設します。検索意味論は CLI の
`arctx explore --query` と同じく、lane 名 / purpose / payload 内容に対する
位置非依存の AND 検索です。記録は後から引き出せて初めて価値になるため、
検索は Web でも第一級の入口です。

Web 独自の状態モデルは作りません。Overview、検索、比較、判断 UI はすべて
`arctx export --format json` の同じ RunGraph / Payload / Lane データから導出し、
書き込みは core の `add` / `attach` / `cut` / lane 操作に変換します。

## Git worktree との併用

arctx は git を実行しないので、worktree を arctx に教える設定はありません
(`ARCTX_GIT_WORKTREE` と `arctx git worktree` は削除済み)。各 agent に独立した
checkout を与えるには、`git worktree add` でツリーを作り、その中でコミットし、
そこで `arctx add --commit HEAD` を実行します。1 つの ARCTX run を共有しつつ、
git 側のライフサイクルは git に残ります。
