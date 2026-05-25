# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Commands

The package is usually not installed during local development. Use `PYTHONPATH=src`.

- Run all tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q`
- Run one test file: `PYTHONPATH=src python3 -m pytest tests/core/test_run_api.py -q`
- CLI: `PYTHONPATH=src python3 -m stag.cli.main <subcommand> ...`
- Optional checks configured in `pyproject.toml`: `ruff check .`, `black .`, `mypy src`

Docs are Japanese-first and should match the current implementation:

- `docs/ja/DIRECTION.md`
- `docs/ja/STATE_MODEL.md`
- `docs/ja/API.md`
- `docs/ja/CLI.md`
- `docs/ja/AGENT_LOOP.md`

## Version And Compatibility

This project is `0.1.0` alpha. Breaking changes are acceptable and expected. Do not add compatibility shims for removed APIs unless explicitly requested. Old run storage schemas do not need migration support by default.

## Architecture

STAG records the process of optimization/problem-solving. It is not a planner, executor, benchmark runner, or general agent framework.

The current core model is **a single RunGraph plus attached payloads**. Pure graph records carry no domain data; everything domain-specific is on Payload records.

Pure graph records (`src/stag/core/schema/graph.py`):

- `Node`: pure DAG node
- `Transition`: connects many input nodes to exactly one output node (`input_node_ids: tuple[str, ...]`, `output_node_id: str`). Fan-out is represented as sibling Transitions sharing the same input nodes.

Container (`src/stag/core/run_graph.py`):

- `RunGraph`: holds all nodes / transitions / payloads / views, plus reverse-lookup indices
- `GraphView`: lightweight named label anchored to a root node; contents derived at read time via reachability

There is no `Edge` record, no `InputTransition`/`OutputTransition` split, and no `transition_kind()` method. Kind is expressed by the `type` field on the attached `TransitionPayload`.

Avoid reintroducing `Dag`, `StateNode`, `ExecutionPlan`, `PredictionPlan`, `ObservedTransition`, `PredictedTransition`, `ActionResult`, `DerivedRecord`, `InputTransition`, `OutputTransition`, `PlanPayload`, `PredictionPayload`, `ResultPayload`, or `NotePayload` as public symbols.

## Payloads

Two-tier design. All payloads live under `src/stag/core/schema/payloads.py`.

**Generic payloads** (use `type` string to distinguish purpose):
- `NodePayload(payload_id, target_id, type, content={}, metadata={})` — any node annotation
- `TransitionPayload(payload_id, target_id, type, content={}, metadata={})` — any transition annotation

**Built-in typed payloads** (special semantics known to core):
- `CutPayload(payload_id, target_id, target_kind, reason=None)` — append-only cut marker
- `GitChangePayload(payload_id, target_id, branch, head_commit, diff_summary, commit_log=())` — git record on a Transition

**User subclasses**: inherit `PayloadBase`, set `payload_type` as a class-level `field(default="...", init=False)`, register with `register_payload_class(MyClass)`.

**Deserialization**: `payload_from_dict(data)` dispatches by `payload_type`. Unknown types fall back to `NodePayload` or `TransitionPayload` (generic) — CLI never crashes on unregistered custom types.

Old payload types `PlanPayload`, `PredictionPayload`, `ResultPayload`, `NotePayload` are deleted. Use `TransitionPayload(type="...")` and `NodePayload(type="note", content={"text": "..."})` instead.

## RunHandle

`RunHandle` is defined in `src/stag/core/run/handle.py` and binds verb implementations from sibling modules.

Public verbs (each implemented in `src/stag/core/run/<verb>.py`):

- `transition(input_node_ids, payload, *, max_outcomes=1, user_id=None, work_session_id=None) -> list[Transition]` — create N sibling Transitions from input nodes; `payload` must be transition-targeting
- `attach(node_id, payload, *, user_id=None, work_session_id=None) -> PayloadBase` — attach a node-targeting payload to a node
- `cut(target_id, *, target_kind, reason=None, user_id=None, work_session_id=None) -> CutPayload` — mark a Node or Transition inactive
- `anchor(from_node_id, label, ...)` — create a lightweight scope anchor node
- `trace(node_id, ...)` (alias: `history`) — walk history backwards
- `outcomes(transition_id)` — return output node info for a transition
- `view_create(name, *, root_node_id)`
- `view_list()`
- `view_show(name)`

Deleted verbs: `plan`, `predict`, `observe`, `note`.

When adding a new RunHandle method, implement it in a focused `src/stag/core/run/<verb>.py` module and bind it in `handle.py`.

## CLI

`src/stag/cli/main.py` dispatches to `src/stag/cli/commands/<name>.py`.

Current commands:

- `current` / `use` — manage the active run pointer
- `init` / `list` — create / list runs
- `transition` — create a Transition (`--inputs NODE --type TYPE --content JSON [--max-outcomes N]`)
- `cut` — cut a Node or Transition (`--node NODE_ID` or `--transition T_ID`)
- `show` — inspect a node / transition / payload as JSON
- `trace` / `outcomes` / `reachable` — derived queries
- `view` — manage `GraphView`s
- `dump` — render the whole run as `outline` (LLM-friendly) or `mermaid` (visual)
- `anchor` — create a scope anchor node
- `guide` — print usage hints
- `migrate` — convert a jsonl run dir to sqlite
- `git` — git integration helpers
- `sync` — sync helpers

Deleted commands: `plan`, `predict`, `observe`, `note`.

Commands resolve the target run in this order:

1. `--run`
2. `STAG_RUN_ID`
3. `<store-dir>/../current.json`

Mutating commands resolve user attribution in this order:

1. `--user`
2. `STAG_USER_ID`
3. `<store-dir>/../config.json` `user.id`
4. `"user"`

The `workflows/`, `domains/`, `execution/`, and `search/` packages are scaffolding unless the task explicitly wires them.

## `stag dump` — render the run

`stag dump` is the single command for getting the whole run structure in one shot. Two formats:

- `--format outline` (default): LLM-optimized indented spanning tree. Each node and transition rendered exactly once. Multi-input transitions anchored under `input_node_ids[0]`; additional inputs shown inline as `(+n_X)`; non-primary parents show `▸ feeds t_X (@n_primary)`. Back-references use `↻n_X`. Cuts show `✂`. When ≥3 multi-input transitions exist, a top-level `joins:` index is emitted.
- `--format mermaid`: human/visual format. Renders a `flowchart TD` mermaid block. Each Transition becomes labeled edges from each input to the single output.

Useful flags: `--node`, `--depth`, `--full-payloads`.

Renderer code: `src/stag/core/run/dump.py`. Tests: `tests/core/test_dump.py`.

## IDs

IDs are minted through `RunHandle._next_id(prefix)` (delegates to `opaque_id(prefix)`).

Current prefixes:

- `n` — Node
- `t` — Transition
- `pl` — Payload
- `run` — Run
- `we` — WorkEvent
- `view` — GraphView

IDs are opaque and collision-resistant (`n_<uuid>`, `t_<uuid>`, `pl_<uuid>`). Do not assume sequential IDs. The root node is opaque; use `run.root_node_id` or the `root_node_id` returned by `run_init_command`.

## Cut

Cut is append-only. It attaches a `CutPayload` to a Node or Transition; it does not delete records.

Activity is computed at read time in `src/stag/core/cuts.py`:

- A `CutPayload` on a Node makes that node and all downstream Transitions and Nodes inactive.
- A `CutPayload` on a Transition makes that Transition and its output Node (and descendants) inactive.

Writers that extend observed history must reject cut nodes via `_ensure_active_node(node_id)`.

## Storage

`JsonlRunStore` writes the current schema only. A run directory contains:

- `run.json`
- `graph.json` (RunGraph metadata)
- `nodes.jsonl`
- `transitions.jsonl` — each row has `transition_id`, `input_node_ids`, `output_node_id`, `metadata`
- `payloads.jsonl` — dispatched by `payload_type` on load
- `views.jsonl`
- `work_sessions.jsonl`
- `work_events.jsonl`

Old files `edges.jsonl`, `input_transitions.jsonl`, `output_transitions.jsonl`, `dags.jsonl`, `states.jsonl` do not exist in the current schema.

`SqliteRunStore` stores the same data in a per-run `run.db`.

Payload deserialization uses `payload_from_dict(data)` which dispatches by `payload_type`. Fallback: unknown types become generic `NodePayload` / `TransitionPayload`.
