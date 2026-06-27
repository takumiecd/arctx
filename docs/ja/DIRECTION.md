# Direction

正準のグラフモデルは現在次の通りです:

```text
Node -> Step -> Node -> Step -> Node
```

専用の step record 型はありません。Payload が素の `Step` に意味を付与します。

コアは standalone で git に依存しません。Git 連携は `arctx.ext.git` 配下の
標準 extension で、正準 CLI は `arctx git <verb>`、一般的なワークフロー向けに
`arctx commit` などのデフォルト alias があります。

将来の UI 作業では DAG を視覚的に描画し、focus した node / step の payload
詳細のみを表示すべきです。

## Git worktree 対応ワークフロー

Git extension は worktree 対応です。`Lane` を特定の `git worktree` に
attach でき、そのセッション内の ARCTX コマンドは git サブプロセスを紐づいた
working tree の中で実行します:

- `ARCTX_GIT_WORKTREE` はすべての git verb
  (`arctx git commit / revert / cherry-pick / merge / reset / verify`) の cwd を
  上書きします。
- `arctx lane start / env / spawn --worktree PATH` は解決済みのパス
  （加えて現在のブランチと `git --git-common-dir`）を
  `Lane.metadata["worktree"]` に記録し、下流プロセス向けに
  `ARCTX_GIT_WORKTREE` を export します。
- `arctx git worktree {add,list,remove}` は上流の `git worktree` plumbing の
  薄いラッパーです。ライフサイクルは git 側に残るため、ARCTX の外で作成された
  worktree も attach できます。

考えられるフォローアップ:

- worktree パスを `arctx lane list` / TUI ビューで表示する。
- agent が単一セッション中に worktree を移動した際、step ごとの workspace
  パスを記録する。
- `lane env --new --worktree PATH` が存在しないディレクトリを指す場合に
  worktree を自動生成する。
