# API

コア API の形:

```python
from arctx import Requirement, StepPayload, NodePayload, init

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
```

`run.add_step(...)` は `Step` を 1 つと出力 `Node` を 1 つだけ生成します。
同じ入力 Node ID で `run.add_step(...)` を複数回呼ぶと、兄弟となる代替を作れます。

`cut(target_kind="node" | "step")` は `CutPayload` を append します。

削除された API `plan`, `predict`, `observe`, `note` は `step(...)` と
`attach(...)` で表現します。

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
