# Direction

正準グラフモデル:

```text
Node -> Transition -> Node -> Transition -> Node
```

`Transition` は必ず 1 つの output Node を持ちます（single-output）。
fan-out は sibling Transitions（同じ input から複数の Transition）で表現します。

Transition の種類・意味は attached payload の `type` フィールドで区別します。
`transition_kind()` メソッドも専用の record type も持ちません。

core は standalone で、git には依存しません。git 連携は標準 extension
`arctx.ext.git` が提供します。正式 CLI は `arctx git <verb>` で、`arctx commit`
などの日常用 command は default alias として解決されます。

今後の UI は DAG を図として表示し、選択した node / transition の
payload だけを詳細表示する方針です。

## git worktree-aware な workflow

Git extension は worktree-aware になっています。`WorkSession` を特定の
`git worktree` に紐付けると、その session 内で動く git verb はリンクされた
working tree に対して実行されます:

- `ARCTX_GIT_WORKTREE` がセットされていると、すべての git verb
  (`arctx git commit / revert / cherry-pick / merge / reset / verify`)
  の cwd がその worktree に切り替わります。
- `arctx work-session start / env / spawn --worktree PATH` は解決済みの
  絶対パス・current branch・`git --git-common-dir` を
  `WorkSession.metadata["worktree"]` に記録し、子プロセス向けに
  `ARCTX_GIT_WORKTREE` を export します。
- `arctx git worktree {add,list,remove}` は `git worktree` の薄いラッパです。
  ライフサイクル管理は git 側に寄せているため、ARCTX の外で作成した
  worktree もそのまま attach できます。

今後の検討事項:

- `arctx work-session list` / TUI に worktree path を表示する。
- 1 session 内で worktree を跨いだ場合、transition ごとに workspace path
  を記録する。
- `work-session env --new --worktree PATH` が存在しないディレクトリを
  指したとき、自動で worktree を作成する。
