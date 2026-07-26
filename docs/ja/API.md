# API

コア API の形:

```python
from arctx import Requirement, StepPayload, NodePayload, init
from arctx.ext.diagram.payloads import DiagramPayload

run = init(Requirement("req_1", "task", "my_task"), run_id="my-run")

step = run.add_step(
    [run.root_node_id],
    StepPayload(
        payload_id="_",
        target_id="_",
        type="experiment",
        content={"lr": 0.01},
    ),
)
node_id = step.output_node_id

run.attach(
    node_id,
    NodePayload(
        payload_id="_",
        target_id="_",
        type="note",
        content={"text": "accuracy=87.2%"},
    ),
)

run.attach(
    node_id,
    DiagramPayload(
        payload_id="_",
        target_id="_",
        target_kind="node",
        title="retry loop",
        format="mermaid",
        source="flowchart TD\n  fetch --> retry\n  retry --> fetch",
    ),
)
```

`run.add_step(...)` は `Step` を 1 つと出力 `Node` を 1 つだけ生成します。
同じ入力 Node ID で `run.add_step(...)` を複数回呼ぶと、兄弟となる代替を作れます。

`cut(target_kind="node" | "step")` は `CutPayload` を append します。
`diagram` extension は図・モデル用の `DiagramPayload` を提供します。中に持つ edge
は ARCTX の `RunGraph` の edge ではないため、循環していても構いません。

削除された API `plan`, `predict`, `observe`, `note` は `step(...)` と
`attach(...)` で表現します。

## Asset（git オブジェクト参照）

`attach_asset(...)` は `(commit, path)` の参照を Node / Step に付けます。実体は
コピーせず、閲覧時に git から解決します。

```python
result = run.attach_asset(node_id, "bench/plot.png")          # commit 省略 = HEAD
result = run.attach_asset(step.step_id, "bench/out", commit="v0.3.1")  # ディレクトリも可

result.payload   # AssetPayload(commit=<40桁 SHA>, path="bench/out", title=None)
result.kind      # "blob" | "tree"
result.warning   # push 済みでない場合の警告文（None なら remote に到達可能）
```

- `path` はリポジトリルート相対（cwd 相対・絶対パスも受理し正規化）。ファイルでも
  ディレクトリでも構いません
- attach 時に `<commit>:<path>` の実在を検証し、解決しなければ `MissingCommit` /
  `MissingPath`（いずれも `GitRefError`）を送出します
- repo 引数はありません。対象は run データを包むリポジトリ自身（absent = self）
- `warning` は**レコードに保存しません**。push 状態は環境ローカルで時間とともに
  変わるため、jsonl には事実（commit と path）だけを残します
- 解決ヘルパは `arctx.core.gitref`（`resolve_commit` / `object_kind` / `read_blob` /
  `list_tree` / `unpushed_warning`）にあります

## Git Extension API

Git の verb は標準の `git` extension 名前空間にあります:

```python
step = run.git.commit(message="run baseline benchmark")
run.git.revert(target_sha="<sha>")
run.git.cherry_pick(source_sha="<sha>")
run.git.reset(to_node_id="<node_id>", mode="hard")
violations = run.git.verify()
```

`run.commit(...)`, `run.revert(...)`, `run.verify(...)` などの旧トップレベル
メソッドは削除されました。コアの `RunHandle` は git 非依存のままで、git の
payload・event・verb は `arctx.ext.git` が提供します。
