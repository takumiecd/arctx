# ARCTX

> **Git tracks what changed. ARCTX tracks why you changed it — and what you decided not to.**
>
> An append-only DAG for reasoning history, parallel agent collaboration, and abandoned branches that stay in the graph.

## Packages

This repository distributes three packages:

| Package | Install | Import | Purpose |
|---------|---------|--------|---------|
| `arctx` | `pip install arctx` | `import arctx` | Core API, storage, extensions (no CLI/TUI deps) |
| `arctx-cli` | `pip install arctx-cli` | `import arctx_cli` | `arctx` command, argparse CLI |
| `arctx-tui` | `pip install arctx-tui` | `import arctx_tui` | `arctx-tui` command, Textual TUI |

`arctx-cli` and `arctx-tui` both depend on `arctx` but not on each other. Install only what you need.

```python
import arctx

handle = arctx.init(arctx.Requirement(requirement_id="r", target_type="code", target_id="r"))
```

---

ARCTX is **not** an agent framework, planner, or executor.  
It is the graph layer underneath them.

![ARCTX CLI Demo](examples/demo_cli.gif)

*Two AI agents (Claude and Codex) working against the same run in parallel. Each gets an isolated `work-session`; both branches land as sibling transitions in the same `RunGraph` — no race, no overwrite.*

![ARCTX TUI Demo](examples/demo_tui.gif)

*Interactive 3-pane TUI walks the DAG: attempts, reverts, payload diffs, and full git history all in one view.*

> 0.2 beta — the core graph model is stabilizing. Storage and API changes may still happen, but they will be documented in release notes.

*日本語版は [README.ja.md](README.ja.md) を参照してください。*

---

## Why ARCTX?

Real work is not a straight line. You form a hypothesis, try it, observe what happened, drop one branch, take another, and later need to reconstruct *why* you ended up where you did.

- Git is **file history** — what bytes changed in which commit.
- ARCTX is **reasoning / action / decision history** — which hypothesis was tested, which result it produced, and which branches were cut.

ARCTX records all of it as one append-only DAG:

- **Parallel agents, no conflict.** Several agents or humans can drive the same run; each gets its own tracked work-session and their attempts become sibling transitions.
- **Reverts stay in the graph.** A failed rewrite isn't deleted, it's marked inactive via `CutPayload`. You can still see what was tried, and why.
- **Domain payloads, not just commits.** Attach benchmark results, predictions, intent — anything. The DAG knows what each transition was *for*.
- **Read-time activity.** Killed branches are filtered automatically; the graph stays clean without rewriting history.

ARCTX is *not* an executor, planner, or agent framework. It is the substrate for storing what they did and why.

---

## When does ARCTX fit?

- **Multi-agent software work** — Claude Code, Codex, custom agents and humans working on the same codebase. ARCTX keeps each attempt distinct and reviewable.
- **Research and design exploration** — branch hypotheses, capture results as payloads, keep the dropped branches around as evidence.
- **Debugging and investigation** — record hypotheses and observations as payloads; walk the trace backwards when you finally find the bug.
- **Benchmark-driven engineering** — every "try variant A, try variant B" lands as a transition with its measurement attached.
- **Kernel / numeric optimization** — one specific case of the above: tiled / vectorized / fused experiments as sibling transitions, with reverts and merges first-class.

---

### Example 1: Benchmark-driven optimization

You try variant A, it gets slower. You try variant B, it gets faster. Three months later you need to explain *why* variant A was abandoned.

```bash
# 1. Baseline
arctx init optimize --extension git --run-id bench
arctx git commit -m "baseline: naive loop"

# 2. Hypothesis A — add a cache layer
git checkout -b feat/cache
# ...edit...
git add . && arctx git commit -m "add cache (hypothesis A)"
arctx payload add --target transition:latest \
  --payload-type benchmark \
  --field elapsed_ms=1200 \
  --field note="slower than baseline"

# 3. Abandon A — it stays in the graph, just marked inactive
arctx cut transition $(arctx show --latest transition)

# 4. Hypothesis B — vectorize
git checkout main && git checkout -b feat/vectorize
# ...edit...
git add . && arctx git commit -m "vectorize (hypothesis B)"
arctx payload add --target transition:latest \
  --payload-type benchmark \
  --field elapsed_ms=180 \
  --field note="5x faster than baseline"
```

The resulting graph tells the whole story:

```text
n_root
└─ t_baseline ── n_1
   ├─ t_cache_hypothesis_A ── n_2 ✂
   │     payload: benchmark {elapsed_ms: 1200, note: "slower than baseline"}
   └─ t_vectorize_hypothesis_B ── n_3
         payload: benchmark {elapsed_ms: 180, note: "5x faster than baseline"}
```

No spreadsheet, no stale Confluence page — the *reasoning* lives next to the *code*.

---

### Example 2: Multi-agent parallel work

Claude and Codex drive the same run without stepping on each other.

```bash
# Terminal 1 — Claude
eval $(arctx work-session env --run demo --new --user claude)
git checkout -b claude/vec
# ...edits...
git add . && arctx git commit -m "Claude: vectorize inner loop"

# Terminal 2 — Codex (running at the same time)
eval $(arctx work-session env --run demo --new --user codex)
git checkout main && git checkout -b codex/map
# ...edits...
git add . && arctx git commit -m "Codex: parallel map"
```

Both land in the same `RunGraph` as sibling transitions:

```text
n_root
└─ t_baseline ── n_1
   ├─ t_claude_vectorize_inner_loop ── n_2
   │     work-session: claude / ws_xxx
   └─ t_codex_parallel_map ── n_3
         work-session: codex / ws_yyy
```

No merge conflicts in the graph. Both attempts stay reviewable forever.

---

### Example 3: Debugging trace

Record every hypothesis as you chase a bug; walk it backwards once you find the cause.

```bash
arctx init debug --extension git --run-id bug-42
arctx git commit -m "reproduction script"

# Hypothesis: race condition in cache
git checkout -b try/race-fix
# ...edit...
arctx git commit -m "fix: add lock around cache"
arctx payload add --target transition:latest \
  --payload-type observation \
  --field result="still flaky"

# Hypothesis: off-by-one in index
git checkout main && git checkout -b try/index-fix
# ...edit...
arctx git commit -m "fix: correct loop bound"
arctx payload add --target transition:latest \
  --payload-type observation \
  --field result="bug gone — 3 runs green"
```

```text
n_root
└─ t_reproduction_script ── n_1
   ├─ t_fix_add_lock_around_cache ── n_2
   │     payload: observation {result: "still flaky"}
   └─ t_fix_correct_loop_bound ── n_3
         payload: observation {result: "bug gone — 3 runs green"}
```

When your colleague asks *"how did you know it was the loop bound?"*, the graph answers for you.

---

## 30-second Quick Start

From inside a git repository:

```bash
pip install arctx-cli
pip install arctx-tui          # optional: adds standalone arctx-tui command

arctx init my_task --extension git --run-id demo
echo "def f(): pass" > work.py && git add work.py
arctx git commit -m "baseline"

arctx-tui                              # explore the DAG interactively (requires arctx-tui)
arctx graph dump --format outline      # or dump it as an LLM-friendly outline
```

`arctx dump` is kept as a compatibility shortcut for `arctx graph dump`.

Two agents on the same repo? Each gets an isolated work-session that doesn't touch the others' attribution:

```bash
# Claude's terminal
eval $(arctx work-session env --run demo --new --user claude)
git checkout -b claude/vec
# ...edits...
git add . && arctx git commit -m "Claude: vectorization"

# Codex's terminal (running in parallel)
eval $(arctx work-session env --run demo --new --user codex)
git checkout main && git checkout -b codex/map
# ...edits...
git add . && arctx git commit -m "Codex: parallel map"
```

Both branches land in the same `RunGraph` as sibling transitions. See `examples/demo_cli.tape` and `examples/demo_env.sh` for the runnable VHS recording of this scenario.

> **Note on isolation.** A ARCTX `work-session` isolates ARCTX run/session attribution (who did what, in which session). It does **not** isolate the Git working tree by itself — both terminals above share the same checkout unless you attach each session to its own `git worktree`. See the next section for the worktree-aware variant.

### Parallel agents in separate worktrees

`arctx` can pin each agent to a dedicated `git worktree` so two terminals
can edit, stage, and commit without trampling each other:

```bash
# Set up two worktrees on independent branches.
arctx git worktree add ../wt-claude claude/vec
arctx git worktree add ../wt-codex  codex/map

# Each agent attaches its work-session to one worktree.
# This exports ARCTX_RUN_ID / ARCTX_WORK_SESSION_ID / ARCTX_USER_ID *and*
# ARCTX_GIT_WORKTREE, so subsequent `arctx git commit` runs inside that
# worktree only.
eval $(arctx work-session env --run demo --new --user claude \
        --worktree ../wt-claude)
eval $(arctx work-session env --run demo --new --user codex \
        --worktree ../wt-codex)
```

Both agents still land their commits as sibling transitions in the same
`RunGraph`; the worktrees only separate the physical checkout.

---

## Concepts (one screen)

The center of ARCTX is **`RunGraph`** — an append-only DAG. Pure graph records carry no domain data; everything domain-specific lives on **Payload** records.

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
- `GitChangePayload` — attached by the `git` extension on every `arctx git commit`.

Activity ("is this node still in scope?") is computed at read time from `RunGraph` + cut payloads. The store is never rewritten.

---

## CLI Essentials

| Command | What it does |
| --- | --- |
| `arctx init <req-id>` | Start a new run. Add `--extension git` for git integration. |
| `arctx git commit -m ...` | Drive a real `git commit` and record a `Transition` with `GitChangePayload`. |
| `arctx work-session env --new --user <name>` | Print shell exports so a terminal or subprocess gets its own session. Add `--worktree PATH` to also pin git operations to a linked worktree. |
| `arctx git worktree add <path> [branch]` | Thin wrapper over `git worktree add`. Combine with `--worktree` on `work-session env` to give each agent an isolated checkout. |
| `arctx transition create` | Add a transition without git. |
| `arctx payload add` | Attach a payload to an existing Node / Transition. |
| `arctx graph dump --format outline` | LLM-friendly indented spanning-tree dump of the whole run. |
| `arctx graph dump --format mermaid` | Mermaid flowchart for humans / docs. |
| `arctx-tui` | Interactive 3-pane explorer (Runs / Flowchart / Detail). Standalone command from `pip install arctx-tui`. |
| `arctx cut node <id>` | Mark a Node (and descendants) inactive — append-only. |
| `arctx guide` | Discover concepts interactively. `--lang ja` for Japanese. |

`arctx dump ...` is retained as a compatibility shortcut for `arctx graph dump ...`.

Full reference: [docs/en/CLI.md](docs/en/CLI.md).

Mutating commands resolve the target run in this order: `--run` flag → `ARCTX_RUN_ID` env → nearest git repo's `.arctx-id`. User attribution: `--user` → `ARCTX_USER_ID` → `<ARCTX_HOME>/config.json` → `"user"`.

---

## Python API

```python
import arctx as arctx
from arctx import NodePayload, Requirement, TransitionPayload
from arctx.storage import JsonlRunStore

requirement = Requirement(
    requirement_id="req_demo",
    target_type="task",
    target_id="explore_idea",
)

run = arctx.init(requirement, run_id="demo")

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
PYTHONPATH=src python3 -m arctx_cli.main ...
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

`SqliteRunStore` stores the same data in a single per-run `run.db`. The default store directory is `<ARCTX_HOME>/runs`.

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
