# ARCTX

[![CI](https://github.com/takumiecd/arctx/actions/workflows/ci.yml/badge.svg)](https://github.com/takumiecd/arctx/actions/workflows/ci.yml)

> **Git tracks what changed. ARCTX tracks why you changed it — and what you decided not to.**
>
> An append-only DAG for reasoning history, parallel agent collaboration, and abandoned branches that stay in the graph.

**See it in 30 seconds** — one command spins up a throwaway repo where two agents
try the same task two ways, one dead end gets cut *with its reason*, and the whole
story exports as a shareable document:

```bash
git clone https://github.com/takumiecd/arctx && cd arctx
./examples/quickstart_demo.sh      # prints the graph + writes a shareable HTML
```

## Packages

The primary surface is two packages — **`arctx` (core) and `arctx-cli`**. A third package, `arctx-tui`, is experimental and not a focus of the current beta.

| Package | Install | Import | Purpose |
|---------|---------|--------|---------|
| `arctx` | `pip install arctx` | `import arctx` | Core API, storage, extensions (no CLI/TUI deps) |
| `arctx-cli` | `pip install arctx-cli` | `import arctx_cli` | `arctx` command, argparse CLI |
| `arctx-tui` | `pip install arctx-tui` | `import arctx_tui` | _Experimental_ `arctx-tui` command (Textual TUI) — secondary; a GUI is the intended direction |

`arctx-cli` and `arctx-tui` both depend on `arctx` but not on each other. For normal use, install `arctx-cli` (it pulls in `arctx`).

```python
import arctx

handle = arctx.init(arctx.Requirement(requirement_id="r", target_type="code", target_id="r"))
```

---

ARCTX is **not** an agent framework, planner, or executor.  
It is the graph layer underneath them.

![ARCTX CLI Demo](examples/demo_cli.gif)

*Two AI agents (Claude and Codex) working against the same run in parallel. Each gets an isolated `work-session`; both branches land as sibling steps in the same `RunGraph` — no race, no overwrite.*

![ARCTX TUI Demo](examples/demo_tui.gif)

*Experimental TUI walking the DAG. The TUI is secondary; the intended interactive direction is a GUI.*

> 0.3 beta — the DAG core (Node / Step / Payload) is stabilizing. Storage and API changes may still happen, but they will be documented in release notes.

*日本語版は [README.ja.md](README.ja.md) を参照してください。*

---

## Why ARCTX?

Real work is not a straight line. You form a hypothesis, try it, observe what happened, drop one branch, take another, and later need to reconstruct *why* you ended up where you did.

- Git is **file history** — what bytes changed in which commit.
- ARCTX is **reasoning / action / decision history** — which hypothesis was tested, which result it produced, and which branches were cut.

ARCTX records all of it as one append-only DAG:

- **Parallel agents, no conflict.** Several agents or humans can drive the same run; each gets its own tracked work-session and their attempts become sibling steps.
- **Reverts stay in the graph.** A failed rewrite isn't deleted, it's marked inactive via `CutPayload`. You can still see what was tried, and why.
- **Domain payloads, not just commits.** Attach benchmark results, predictions, intent — anything. The DAG knows what each step was *for*.
- **Read-time activity.** Killed branches are filtered automatically; the graph stays clean without rewriting history.

ARCTX is *not* an executor, planner, or agent framework. It is the substrate for storing what they did and why.

---

## When does ARCTX fit?

- **Multi-agent software work** — Claude Code, Codex, custom agents and humans working on the same codebase. ARCTX keeps each attempt distinct and reviewable.
- **Research and design exploration** — branch hypotheses, capture results as payloads, keep the dropped branches around as evidence.
- **Debugging and investigation** — record hypotheses and observations as payloads; walk the trace backwards when you finally find the bug.
- **Benchmark-driven engineering** — every "try variant A, try variant B" lands as a step with its measurement attached.
- **Kernel / numeric optimization** — one specific case of the above: tiled / vectorized / fused experiments as sibling steps, with reverts and merges first-class.

---

### Example 1: Benchmark-driven optimization

You try variant A, it gets slower. You try variant B, it gets faster. Three months later you need to explain *why* variant A was abandoned.

```bash
# 1. Baseline. Capture its node id so the experiments can branch off it.
arctx init optimize --extension git --run-id bench
echo "def f(): pass" > work.py && git add work.py
BASE=$(arctx git commit -m "baseline: naive loop" | jq -r .output_node_id)

# 2. Hypothesis A — add a cache layer, branched off the baseline node.
git checkout -b feat/cache
# ...edit...
git add .
A=$(arctx git commit -m "add cache (hypothesis A)" --from "$BASE" | jq -r .output_node_id)
arctx attach "$A" --type benchmark \
  --json '{"elapsed_ms": 1200, "note": "slower than baseline"}'

# 3. Abandon A — it stays in the graph, just marked inactive, with a reason.
arctx cut "$A" --reason "slower than baseline"

# 4. Hypothesis B — vectorize, also branched off the same baseline node.
git checkout main && git checkout -b feat/vectorize
# ...edit...
git add .
B=$(arctx git commit -m "vectorize (hypothesis B)" --from "$BASE" | jq -r .output_node_id)
arctx attach "$B" --type benchmark \
  --json '{"elapsed_ms": 180, "note": "5x faster than baseline"}'
```

`--from "$BASE"` anchors both experiments to the baseline node, so they fan out as
true siblings (instead of chaining, where cutting A would also kill B). The
resulting graph tells the whole story — run `arctx export --format md --full-payloads`:

```text
n_root
└─ baseline ── n_baseline
   ├─ add cache (hypothesis A) ── n_A ✂
   │     benchmark {"elapsed_ms": 1200, "note": "slower than baseline"} · cut: slower than baseline
   └─ vectorize (hypothesis B) ── n_B
         benchmark {"elapsed_ms": 180, "note": "5x faster than baseline"}
```

No spreadsheet, no stale Confluence page — the *reasoning* lives next to the *code*.

---

### Example 2: Multi-agent parallel work

Claude and Codex drive the same run without stepping on each other.

```bash
# Shared baseline. Both agents branch their work off this node id.
BASE=$(arctx git commit -m "baseline" --run demo | jq -r .output_node_id)

# Terminal 1 — Claude
eval $(arctx work-session env --run demo --new --user claude)
git checkout -b claude/vec
# ...edits...
git add . && arctx git commit -m "Claude: vectorize inner loop" --from "$BASE"

# Terminal 2 — Codex (running at the same time)
eval $(arctx work-session env --run demo --new --user codex)
git checkout main && git checkout -b codex/map
# ...edits...
git add . && arctx git commit -m "Codex: parallel map" --from "$BASE"
```

Both land in the same `RunGraph` as sibling steps off the baseline. Each
agent has its own work-session, and `--from "$BASE"` keeps them independent —
no fast-forward conflict, no overwrite:

```text
n_root
└─ baseline ── n_baseline
   ├─ Claude: vectorize inner loop ── n_2   (work-session: claude / ws_xxx)
   └─ Codex: parallel map           ── n_3   (work-session: codex / ws_yyy)
```

No merge conflicts in the graph. Both attempts stay reviewable forever.

---

### Example 3: Debugging trace

Record every hypothesis as you chase a bug; walk it backwards once you find the cause.

```bash
arctx init debug --extension git --run-id bug-42
echo "# repro" > repro.py && git add repro.py
REPRO=$(arctx git commit -m "reproduction script" | jq -r .output_node_id)

# Hypothesis: race condition in cache
git checkout -b try/race-fix
# ...edit...
git add .
R=$(arctx git commit -m "fix: add lock around cache" --from "$REPRO" | jq -r .output_node_id)
arctx attach "$R" --type observation --json '{"result": "still flaky"}'

# Hypothesis: off-by-one in index
git checkout main && git checkout -b try/index-fix
# ...edit...
git add .
I=$(arctx git commit -m "fix: correct loop bound" --from "$REPRO" | jq -r .output_node_id)
arctx attach "$I" --type observation --json '{"result": "bug gone - 3 runs green"}'
```

Both hypotheses branch off the reproduction node, so they stay independent and comparable:

```text
n_root
└─ reproduction script ── n_repro
   ├─ fix: add lock around cache ── n_2
   │     observation {"result": "still flaky"}
   └─ fix: correct loop bound    ── n_3
         observation {"result": "bug gone — 3 runs green"}
```

When your colleague asks *"how did you know it was the loop bound?"*, the graph answers for you.

---

## 30-second Quick Start

From inside a git repository:

```bash
pip install arctx-cli

arctx init my_task --extension git --run-id demo
echo "def f(): pass" > work.py && git add work.py
BASE=$(arctx git commit -m "baseline" | jq -r .output_node_id)

arctx log                              # walk the DAG
arctx dump --format outline            # or dump it as an LLM-friendly outline
arctx dump --format mermaid            # or a visual mermaid flowchart
```

`arctx dump` is kept as a compatibility shortcut for `arctx graph dump`.

Two agents on the same repo? Each gets an isolated work-session that doesn't touch the others' attribution:

```bash
# Claude's terminal
eval $(arctx work-session env --run demo --new --user claude)
git checkout -b claude/vec
# ...edits...
git add . && arctx git commit -m "Claude: vectorization" --from "$BASE"

# Codex's terminal (running in parallel)
eval $(arctx work-session env --run demo --new --user codex)
git checkout main && git checkout -b codex/map
# ...edits...
git add . && arctx git commit -m "Codex: parallel map" --from "$BASE"
```

Both branches land in the same `RunGraph` as sibling steps off `$BASE`. See `examples/demo_cli.tape` and `examples/demo_env.sh` for the runnable VHS recording of this scenario.

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

Both agents still land their commits as sibling steps in the same
`RunGraph`; the worktrees only separate the physical checkout.

---

## Concepts (one screen)

The center of ARCTX is **`RunGraph`** — an append-only DAG. Pure graph records carry no domain data; everything domain-specific lives on **Payload** records.

```text
RunGraph
  ├── Node         ← pure DAG node
  ├── Step         ← N input nodes → 1 output node
  └── Payload      ← annotation attached to a Node or Step
```

- Each **attempt / experiment / action is recorded as a step**, producing an output node that represents the resulting state.
- `NodePayload` / `StepPayload` — generic annotations, distinguished by a `type` string. The current internal model still stores steps as `Step` records while the public surface moves to `Step`.
- `CutPayload` — append-only invalidation. The target isn't deleted; it's filtered out at read time.
- `GitChangePayload` — attached by the `git` extension on every `arctx git commit`.

Activity ("is this node still in scope?") is computed at read time from `RunGraph` + cut payloads. The store is never rewritten.

---

## CLI Essentials

| Command | What it does |
| --- | --- |
| `arctx init <req-id>` | Start a new run. Add `--extension git` for git integration. |
| `arctx add node` | Add an independent DAG node. |
| `arctx add step --from <node> --title ...` | Add a DAG step and its output node. |
| `arctx attach <node-or-step> --title ...` | Attach a payload to an existing node or step. |
| `arctx cut <node-or-step>` | Mark a node or step inactive via append-only payload. |
| `arctx show [id]` | Show the current run or a single node/step/payload. |
| `arctx log` | Show the DAG as an ordered event stream. |
| `arctx git commit -m ...` | Drive a real `git commit` and record a `Step` with `GitChangePayload`. |
| `arctx work-session env --new --user <name>` | Print shell exports so a terminal or subprocess gets its own session. Add `--worktree PATH` to also pin git operations to a linked worktree. |
| `arctx git worktree add <path> [branch]` | Thin wrapper over `git worktree add`. Combine with `--worktree` on `work-session env` to give each agent an isolated checkout. |
| `arctx graph dump --format outline` | LLM-friendly indented spanning-tree dump of the whole run. |
| `arctx graph dump --format mermaid` | Mermaid flowchart for humans / docs. |
| `arctx-tui` | _Experimental_ interactive explorer (separate `pip install arctx-tui`). Secondary surface; a GUI is the intended direction. |

`arctx dump ...` is retained as a compatibility shortcut for `arctx graph dump ...`.

Full reference: [docs/en/CLI.md](docs/en/CLI.md).

Mutating commands resolve the target run in this order: `--run` flag → `ARCTX_RUN_ID` env → nearest git repo's `.arctx-id`. User attribution: `--user` → `ARCTX_USER_ID` → `<ARCTX_HOME>/config.json` → `"user"`.

---

## Python API

```python
import arctx as arctx
from arctx import NodePayload, Requirement, StepPayload
from arctx.storage import JsonlRunStore

requirement = Requirement(
    requirement_id="req_demo",
    target_type="task",
    target_id="explore_idea",
)

run = arctx.init(requirement, run_id="demo")

step = run.add_step(
    [run.root_node_id],
    StepPayload(
        payload_id="pending",
        target_id="pending",
        type="experiment",
        content={"intent": "try the first hypothesis"},
    ),
)

run.attach(
    step.output_node_id,
    NodePayload(
        payload_id="pending",
        target_id="pending",
        type="result",
        content={"observation": "promising", "status": "completed"},
    ),
)

history = run.trace(step.output_node_id)

store = JsonlRunStore("runs")
run.save(store)
loaded = store.load_run("demo")
```

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
  steps.jsonl
  payloads.jsonl
  work_sessions.jsonl
  work_events.jsonl
```

`SqliteRunStore` stores the same data in a single per-run `run.db`. The default store directory is `<ARCTX_HOME>/runs`.

`GraphView` / `views.jsonl` were removed during the 0.3 beta redesign. Old view records are ignored by the new core graph model.

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
uv run --package arctx --extra dev pytest packages/arctx/tests -q
uv run --package arctx-cli --extra dev pytest packages/arctx-cli/tests -q
uv run --package arctx-tui --extra dev pytest packages/arctx-tui/tests -q
```

## Release

Maintainer release steps are documented in [CONTRIBUTING.md](CONTRIBUTING.md#release-process).

## License

MIT
