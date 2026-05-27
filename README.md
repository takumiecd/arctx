# STAG

## Packages

This repository distributes three packages:

| Package | Install | Import | Purpose |
|---------|---------|--------|---------|
| `stag-api` | `pip install stag-api` | `import stag_api` | Core API, storage, extensions (no CLI/TUI deps) |
| `stag-cli` | `pip install stag-cli` | `import stag_cli` | `stag` command, argparse CLI |
| `stag-tui` | `pip install stag-tui` | `import stag_tui` | `stag-tui` command, Textual TUI |

`stag-cli` and `stag-tui` both depend on `stag-api` but not on each other. Install only what you need.

```python
import stag_api as stag

handle = stag.init(stag.Requirement(requirement_id="r", target_type="code", target_id="r"))
```

---

**STAG is an append-only graph for thought, work context, and parallel exploration.**

Git tracks how files changed.
STAG tracks how work moved: what was tried, why it was tried, what happened, and which branches were later abandoned or merged.

It is not an agent framework, planner, or executor.
It is the graph layer underneath them.

![STAG CLI Demo](examples/demo_cli.gif)

*Two AI agents (Claude and Codex) working against the same run in parallel. Each gets an isolated `work-session`; both branches land as sibling transitions in the same `RunGraph` — no race, no overwrite.*

![STAG TUI Demo](examples/demo_tui.gif)

*Interactive 3-pane TUI walks the DAG: attempts, reverts, payload diffs, and full git history all in one view.*

> 0.2 beta — the core graph model is stabilizing. Storage and API changes may still happen, but they will be documented in release notes.

*日本語版は [README.ja.md](README.ja.md) を参照してください。*

---

## Why STAG?

Real work is not a straight line. You form a hypothesis, try it, observe what happened, drop one branch, take another, and later need to reconstruct *why* you ended up where you did.

- Git is **file history** — what bytes changed in which commit.
- STAG is **reasoning / action / decision history** — which hypothesis was tested, which result it produced, and which branches were cut.

STAG records all of it as one append-only DAG:

- **Parallel agents, no conflict.** Several agents or humans can drive the same run; each gets its own tracked work-session and their attempts become sibling transitions.
- **Reverts stay in the graph.** A failed rewrite isn't deleted, it's marked inactive via `CutPayload`. You can still see what was tried, and why.
- **Domain payloads, not just commits.** Attach benchmark results, predictions, intent — anything. The DAG knows what each transition was *for*.
- **Read-time activity.** Killed branches are filtered automatically; the graph stays clean without rewriting history.

STAG is *not* an executor, planner, or agent framework. It is the substrate for storing what they did and why.

---

## When does STAG fit?

- **Multi-agent software work** — Claude Code, Codex, custom agents and humans working on the same codebase. STAG keeps each attempt distinct and reviewable.
- **Research and design exploration** — branch hypotheses, capture results as payloads, keep the dropped branches around as evidence.
- **Debugging and investigation** — record hypotheses and observations as payloads; walk the trace backwards when you finally find the bug.
- **Benchmark-driven engineering** — every "try variant A, try variant B" lands as a transition with its measurement attached.
- **Kernel / numeric optimization** — one specific case of the above: tiled / vectorized / fused experiments as sibling transitions, with reverts and merges first-class.

---

## 30-second Quick Start

From inside a git repository:

```bash
pip install stag-cli
pip install stag-tui          # optional: adds standalone stag-tui command

stag init my_task --extension git --run-id demo
echo "def f(): pass" > work.py && git add work.py
stag git commit -m "baseline"

stag-tui                              # explore the DAG interactively (requires stag-tui)
stag graph dump --format outline      # or dump it as an LLM-friendly outline
```

`stag dump` is kept as a compatibility shortcut for `stag graph dump`.

Two agents on the same repo? Each gets an isolated work-session that doesn't touch the others' attribution:

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

> **Note on isolation.** A STAG `work-session` isolates STAG run/session attribution (who did what, in which session). It does **not** isolate the Git working tree by itself — both terminals above share the same checkout unless you attach each session to its own `git worktree`. See the next section for the worktree-aware variant.

### Parallel agents in separate worktrees

`stag` can pin each agent to a dedicated `git worktree` so two terminals
can edit, stage, and commit without trampling each other:

```bash
# Set up two worktrees on independent branches.
stag git worktree add ../wt-claude claude/vec
stag git worktree add ../wt-codex  codex/map

# Each agent attaches its work-session to one worktree.
# This exports STAG_RUN_ID / STAG_WORK_SESSION_ID / STAG_USER_ID *and*
# STAG_GIT_WORKTREE, so subsequent `stag git commit` runs inside that
# worktree only.
eval $(stag work-session env --run demo --new --user claude \
        --worktree ../wt-claude)
eval $(stag work-session env --run demo --new --user codex \
        --worktree ../wt-codex)
```

Both agents still land their commits as sibling transitions in the same
`RunGraph`; the worktrees only separate the physical checkout.

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

- Each **attempt / experiment / action is recorded as a transition**, producing an output node that represents the resulting state.
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
| `stag work-session env --new --user <name>` | Print shell exports so a terminal or subprocess gets its own session. Add `--worktree PATH` to also pin git operations to a linked worktree. |
| `stag git worktree add <path> [branch]` | Thin wrapper over `git worktree add`. Combine with `--worktree` on `work-session env` to give each agent an isolated checkout. |
| `stag transition create` | Add a transition without git. |
| `stag payload add` | Attach a payload to an existing Node / Transition. |
| `stag graph dump --format outline` | LLM-friendly indented spanning-tree dump of the whole run. |
| `stag graph dump --format mermaid` | Mermaid flowchart for humans / docs. |
| `stag-tui` | Interactive 3-pane explorer (Runs / Flowchart / Detail). Standalone command from `pip install stag-tui`. |
| `stag cut node <id>` | Mark a Node (and descendants) inactive — append-only. |
| `stag guide` | Discover concepts interactively. `--lang ja` for Japanese. |

`stag dump ...` is retained as a compatibility shortcut for `stag graph dump ...`.

Full reference: [docs/en/CLI.md](docs/en/CLI.md).

Mutating commands resolve the target run in this order: `--run` flag → `STAG_RUN_ID` env → nearest git repo's `.stag-id`. User attribution: `--user` → `STAG_USER_ID` → `<STAG_HOME>/config.json` → `"user"`.

---

## Python API

```python
import stag
from stag import NodePayload, Requirement, TransitionPayload
from stag.storage import JsonlRunStore

requirement = Requirement(
    requirement_id="req_demo",
    target_type="task",
    target_id="explore_idea",
)

run = stag.init(requirement, run_id="demo")

transition = run.transition(
    [run.root_node_id],
    TransitionPayload(
        payload_id="pending",
        target_id="pending",
        type="experiment",
        content={"intent": "try the first hypothesis"},
    ),
)

run.attach(
    transition.output_node_id,
    NodePayload(
        payload_id="pending",
        target_id="pending",
        type="result",
        content={"observation": "promising", "status": "completed"},
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

The 0.2.x storage format is maintained within the 0.2 series. Breaking changes will require an explicit migration note.

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
