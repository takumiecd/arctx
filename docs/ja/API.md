# API

v0.3.0b1 の Phase 1 では、CLI と docs は `Step` に寄せていますが、Python API の内部名にはまだ `Step` が残ります。

つまり、現時点では以下の対応です。

```text
CLI / docs: Step
Python API: Step
```

内部APIの全面的な `Step` 化は Phase 2 で扱います。

## 基本形

```python
import arctx as arctx
from arctx import NodePayload, Requirement, StepPayload

req = Requirement("req_1", "task", "my_task")
run = arctx.init(req, run_id="my-run")

# 依存を持たない Node を作る。
baseline = run.add_node()

# Step を作る。Python API ではまだ step() を使う。
# 常に 1 つの output node も作られる。
step = run.add_step(
    [baseline.node_id],
    StepPayload(
        payload_id="_",
        target_id="_",
        type="experiment",
        content={"title": "try cache"},
    ),
)
result_node_id = step.output_node_id

# Node に Payload を付ける。
run.attach(
    result_node_id,
    NodePayload(
        payload_id="_",
        target_id="_",
        type="note",
        content={"text": "accuracy=87.2%"},
    ),
)

# fan-out は同じ input Node から複数の Step を作る。
v1 = run.add_step(
    [result_node_id],
    StepPayload(payload_id="_", target_id="_", type="experiment"),
)
v2 = run.add_step(
    [result_node_id],
    StepPayload(payload_id="_", target_id="_", type="experiment"),
)

# cut は append-only な Payload。
run.cut(v1.output_node_id, target_kind="node", reason="不採用")

# multi-input join は input Node を複数渡す。
join = run.add_step(
    [v1.output_node_id, v2.output_node_id],
    StepPayload(payload_id="_", target_id="_", type="synthesis"),
)
```

## Phase 1 の注意

Phase 1 では以下が残ります。

- `Step`
- `StepPayload`
- `run.add_step(...)`
- `target_kind="step"`

CLI ではこれらを Step として見せます。

## 廃止済み API

`run.plan()`, `run.predict()`, `run.observe()`, `run.note()` は削除済みです。

- plan / observe / predict は Step で表現します。
- Python API では当面 `run.add_step(...)` を使います。
- note は `run.attach(node_id, NodePayload(type="note", content={"text": "..."}))` で表現します。

## Git Extension API

git 連携の verb は標準 `git` extension の namespace にあります。

```python
step = run.git.commit(message="run baseline benchmark")
run.git.revert(target_sha="<sha>")
run.git.cherry_pick(source_sha="<sha>")
run.git.reset(to_node_id="<node_id>", mode="hard")
violations = run.git.verify()
```

v0.3 の中心は Git commit ではなく DAG core の Node / Step / Payload です。

Phase 1 では git extension の戻り値や内部 payload target にはまだ `Step` が残ります。

## Payload 登録

現時点で Step に付く Payload は、内部的には `target_kind="step"` を使います。

```python
from arctx import PayloadBase, register_payload_class
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class MyStepPayload(PayloadBase):
    payload_id: str
    target_id: str
    score: float = 0.0
    target_kind: Literal["step"] = field(default="step", init=False)
    payload_type: str = field(default="my_step_payload", init=False)

    def to_dict(self): ...


register_payload_class(MyStepPayload)
```

Phase 2 で `target_kind="step"` へ移行するかを検討します。
