# API

## 基本形

```python
import arctx as arctx
from arctx import Requirement, TransitionPayload, NodePayload

req = Requirement("req_1", "task", "my_task")
run = arctx.init(req, run_id="my-run")

# Transition を作る。常に 1 つの output node も作られる。
t1 = run.transition(
    [run.root_node_id],
    TransitionPayload(
        payload_id="_",
        target_id="_",
        type="experiment",
        content={"lr": 0.01},
    ),
)
n1 = t1.output_node_id

# Node に payload を貼る。
run.attach(
    n1,
    NodePayload(
        payload_id="_",
        target_id="_",
        type="note",
        content={"text": "accuracy=87.2%"},
    ),
)

# 複数の sibling を作る場合は transition を複数回作る。
v1 = run.transition([n1], TransitionPayload(payload_id="_", target_id="_", type="suggestion"))
v2 = run.transition([n1], TransitionPayload(payload_id="_", target_id="_", type="suggestion"))

# cut（append-only な無効化）
run.cut(v1.output_node_id, target_kind="node", reason="不採用")

# multi-input join
join = run.transition(
    [v1.output_node_id, v2.output_node_id],
    TransitionPayload(payload_id="_", target_id="_", type="synthesis"),
)
```

## 廃止 API

`run.plan()`, `run.predict()`, `run.observe()`, `run.note()` は削除済みです。

- plan / observe / predict は `run.transition(...)` で表現します。
- 複数案は同じ input node から `run.transition(...)` を複数回呼びます。
- note は `run.attach(node_id, NodePayload(type="note", content={"text": "..."}))` で表現します。

## Git Extension API

git 連携の verb は標準 `git` extension の namespace にあります。

```python
transition = run.git.commit(message="run baseline benchmark")
run.git.revert(target_sha="<sha>")
run.git.cherry_pick(source_sha="<sha>")
run.git.reset(to_node_id="<node_id>", mode="hard")
violations = run.git.verify()
```

旧 `run.commit(...)`, `run.revert(...)`, `run.verify(...)` のような top-level
method は削除済みです。core の `RunHandle` は git を知らず、git payload / event /
verb は `arctx.ext.git` が提供します。

## Payload 登録

```python
from arctx import register_payload_class, PayloadBase
from dataclasses import dataclass, field
from typing import Literal

@dataclass(frozen=True)
class MyPayload(PayloadBase):
    payload_id: str
    target_id: str
    score: float = 0.0
    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="my_payload", init=False)

    def to_dict(self): ...

register_payload_class(MyPayload)
```
