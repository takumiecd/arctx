# API

Core API shape:

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

`run.add_step(...)` creates exactly one `Step` and one output `Node`.
Create sibling alternatives by calling `run.add_step(...)` multiple times with
the same input node IDs.

`cut(target_kind="node" | "step")` appends a `CutPayload`.

The removed APIs `plan`, `predict`, `observe`, and `note` are represented by
`step(...)` and `attach(...)`.

## Git Extension API

Git verbs live under the standard `git` extension namespace:

```python
step = run.git.commit(message="run baseline benchmark")
run.git.revert(target_sha="<sha>")
run.git.cherry_pick(source_sha="<sha>")
run.git.reset(to_node_id="<node_id>", mode="hard")
violations = run.git.verify()
```

The old top-level methods such as `run.commit(...)`, `run.revert(...)`, and
`run.verify(...)` are removed. Core `RunHandle` stays git-agnostic; git payloads,
events, and verbs are provided by `arctx.ext.git`.
