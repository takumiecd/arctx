# STAG

**An append-only graph for parallel optimization work.** Multiple AI agents, humans, and benchmark runners branch, revert, and merge against the same run — without losing a single attempt.

![STAG CLI Demo](examples/demo_cli.gif)

*Two AI agents (Claude and Codex) committing to the same repo in parallel. Each gets an isolated `work-session`; both branches land as sibling transitions in the same `RunGraph` — no race, no overwrite.*

![STAG TUI Demo](examples/demo_tui.gif)

*Interactive 3-pane TUI walks the DAG: experiments, reverts, payload diffs, and full git history all in one view.*

> 0.1 alpha — breaking changes expected. The model is being refined; old run storage formats are not migrated.

*日本語版は [README.ja.md](README.ja.md) を参照してください。*

---

## Why STAG?

Real optimization work is messy. You try vectorization, hit a wall, try multithreading, deadlock, revert, try something else. Today these branches live in your head, your scratch notes, and a `git log --oneline` that doesn't say *why* anything was tried.

STAG records all of it as one append-only DAG:

- **Parallel agents, no conflict.** Claude and Codex can both `stag git commit` against the same run; each gets its own tracked work-session.
- **Reverts stay in the graph.** A failed Rust rewrite isn't deleted, it's marked inactive via `CutPayload`. You can still see what was tried, and why.
- **Domain payloads, not just commits.** Attach benchmark results, predictions, intent — anything. The DAG knows what each transition was *for*.
- **Read-time activity.** Killed branches are filtered automatically; the graph stays clean without rewriting history.

STAG is *not* an executor, planner, or agent framework. It is the substrate for storing what they did.

---

## When does STAG fit?

- **Parallel AI agent orchestration** — Claude Code, Codex, custom agents all working on the same codebase. STAG keeps each attempt distinct and reviewable.
- **Kernel / numeric optimization** — every "try tiled, try vectorized, try fused" experiment becomes a node. Reverts and merges are first-class.
- **Investigation / debugging** — record hypotheses and observations as payloads; walk the trace backwards when you finally find the bug.

---

## 30-second Quick Start

```bash
pip install -e .

stag init my_task --extension git --run-id demo
echo "def f(): pass" > work.py && git add work.py
stag git commit -m "baseline"

stag tui          # explore the DAG interactively
stag dump         # or dump it as an LLM-friendly outline
```

Two AI agents on the same repo? Each gets an isolated work-session that doesn't touch the others' state:

```bash
# Claude's terminal
eval $(stag work-session env --run demo --new --user claude)
git checkout -b claude/vec
# ...edits...
git add . && stag git commit -m "Claude: vectorization"

# Codex's terminal (running in parallel)
eval $(stag work-session env --run demo --new --user codex)
git checkout main && git checkout -b codex/map
# ...edits...
git add . && stag git commit -m "Codex: parallel map"
```

Both branches land in the same `RunGraph` as sibling transitions. See `examples/demo_cli.tape` and `examples/demo_env.sh` for the runnable VHS recording of this scenario.

---

## Concepts (one screen)

The center of STAG is **`RunGraph`** — an append-only DAG. Pure graph records carry no domain data; everything domain-specific lives on **Payload** records.

```text
RunGraph
  ├── Node         ← pure DAG node
  ├── Transition   ← N input nodes → 1 output node
  ├── Payload      ← annotation attached to a Node or Transition
  └── GraphView    ← lightweight named scope (just a root_node_id)
```

- `NodePayload` / `TransitionPayload` — generic annotations, distinguished by a `type` string.
- `CutPayload` — append-only invalidation. The target isn't deleted; it's filtered out at read time.
- `GitChangePayload` — attached by the `git` extension on every `stag git commit`.

Activity ("is this node still in scope?") is computed at read time from `RunGraph` + cut payloads. The store is never rewritten.

---

## CLI Essentials

| Command | What it does |
| --- | --- |
| `stag init <req-id>` | Start a new run. Add `--extension git` for git integration. |
| `stag git commit -m ...` | Drive a real `git commit` and record a `Transition` with `GitChangePayload`. |
| `stag work-session env --new --user <name>` | Print shell exports so a terminal or subprocess gets its own session. |
| `stag transition create` | Add a transition without git. |
| `stag payload add` | Attach a payload to an existing Node / Transition. |
| `stag dump --format outline` | LLM-friendly indented spanning-tree dump of the whole run. |
| `stag dump --format mermaid` | Mermaid flowchart for humans / docs. |
| `stag tui` | Interactive 3-pane explorer (Runs / Flowchart / Detail). |
| `stag cut node <id>` | Mark a Node (and descendants) inactive — append-only. |
| `stag guide` | Discover concepts interactively. `--lang ja` for Japanese. |

Full reference: [docs/en/CLI.md](docs/en/CLI.md).

Mutating commands resolve the target run in this order: `--run` flag → `STAG_RUN_ID` env → nearest git repo's `.stag-id`. User attribution: `--user` → `STAG_USER_ID` → `<STAG_HOME>/config.json` → `"user"`.

---

## Python API

```python
import stag
from stag import NodePayload, Requirement, TransitionPayload
from stag.storage import JsonlRunStore

requirement = Requirement(
    requirement_id="req_kernel",
    target_type="kernel",
    target_id="csc_linear",
)

run = stag.init(requirement, run_id="demo")

transition = run.transition(
    [run.root_node_id],
    TransitionPayload(
        payload_id="pending",
        target_id="pending",
        type="experiment",
        content={"intent": "run baseline benchmark"},
    ),
)

run.attach(
    transition.output_node_id,
    NodePayload(
        payload_id="pending",
        target_id="pending",
        type="result",
        content={"latency_ms": 1.5, "status": "completed"},
    ),
)

history = run.trace(transition.output_node_id)

store = JsonlRunStore("runs")
run.save(store)
loaded = store.load_run("demo")
```

For isolated exploration, a `GraphView` holds only a `root_node_id`; its contents are derived at read time via `RunGraph.reachable_from(root_node_id)`.

---

## Install

Python 3.10+ required.

```bash
python3 -m pip install -e .            # editable install
python3 -m pip install -e ".[dev]"     # + dev dependencies

# Or run without installing, from the repo root:
PYTHONPATH=src python3 -m stag.cli.main ...
```

---

## Storage Layout

`JsonlRunStore` persists each run as a directory:

```text
<store-dir>/<run-id>/
  run.json
  graph.json
  nodes.jsonl
  transitions.jsonl
  payloads.jsonl
  views.jsonl
  work_sessions.jsonl
  work_events.jsonl
```

`SqliteRunStore` stores the same data in a single per-run `run.db`. The default store directory is `<STAG_HOME>/runs`.

0.1 alpha schema may change in breaking ways; no migration from older formats.

---

## Documentation

- [Concept](docs/en/CONCEPT.md)
- [Project Direction](docs/en/DIRECTION.md)
- [State Model](docs/en/STATE_MODEL.md)
- [API](docs/en/API.md)
- [CLI](docs/en/CLI.md)
- [Problem-Solving Loop](docs/en/AGENT_LOOP.md)

日本語ドキュメントは [docs/ja/](docs/ja/) にあります。

---

## Development

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q
```

## License

MIT
