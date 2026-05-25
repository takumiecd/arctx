# API

## 基本形

```python
import stag
from stag import Requirement, TransitionPayload, NodePayload

req = Requirement("req_1", "task", "my_task")
run = stag.init(req, run_id="my-run")

# Transition を作る（1 つの output node）
[t1] = run.transition(
    [run.root_node_id],
    TransitionPayload(payload_id="_", target_id="_", type="experiment",
                      content={"lr": 0.01}),
)
n1 = t1.output_node_id

# Node にメモを貼る
run.attach(n1, NodePayload(payload_id="_", target_id="_", type="note",
                            content={"text": "accuracy=87.2%"}))

# 複数の sibling（fan-out）
variants = run.transition(
    [n1],
    TransitionPayload(payload_id="_", target_id="_", type="suggestion"),
    max_outcomes=3,
)

# cut（append-only な無効化）
run.cut(variants[0].output_node_id, target_kind="node", reason="不採用")

# multi-input join
[join] = run.transition(
    [variants[1].output_node_id, variants[2].output_node_id],
    TransitionPayload(payload_id="_", target_id="_", type="synthesis"),
)
```

## 廃止 API

`run.plan()`, `run.predict()`, `run.observe()`, `run.note()` は削除済みです。
- plan/observe → `run.transition(..., max_outcomes=1, ...)`
- predict → `run.transition(..., max_outcomes=N, ...)`
- note → `run.attach(node_id, NodePayload(type="note", content={"text": "..."}))`

## Payload 登録

```python
from stag import register_payload_class, PayloadBase
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
