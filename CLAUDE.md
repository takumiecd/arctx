# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Commands

The package is usually not installed during local development. Use `PYTHONPATH=src`.

- Run all tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q`
- Run one test file: `PYTHONPATH=src python3 -m pytest tests/core/test_run_api.py -q`
- CLI: `PYTHONPATH=src python3 -m optagent.cli.main <subcommand> ...`
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

optagent records the process of optimization/problem-solving. It is not a planner, executor, benchmark runner, or general agent framework.

The current core model is **a single RunGraph plus attached payloads**. Pure graph records carry no domain data; everything domain-specific is on Payload records.

Pure graph records (`src/optagent/core/schema/graph.py`):

- `Node`: pure graph node
- `InputTransition`: entry point of an operation, with `input_node_ids: tuple[str, ...]` (multi-input allowed)
- `OutputTransition`: result edge from one InputTransition to one output node

Container (`src/optagent/core/run_graph.py`):

- `RunGraph`: holds all nodes / input_transitions / output_transitions / payloads / views, plus traversal indices
- `GraphView`: lightweight named label anchored to a root node; contents derived at read time via reachability

Observed vs predicted is a property of the **OutputTransition's attached payload**, not a separate record family:

- A `ResultPayload` on an OT → that OT is observed
- A `PredictionPayload` on an OT → that OT is predicted
- `RunGraph.output_kind(ot_id)` returns `"result" | "prediction" | "unknown"`

Avoid reintroducing `Dag` (singular per role), `StateNode`, `ExecutionPlan`, `PredictionPlan`, `ObservedTransition`, `PredictedTransition`, `ActionResult`, or `DerivedRecord` as public compatibility aliases unless the task explicitly asks for that.

## Payloads

Payload types live under `src/optagent/core/schema/payloads.py`.

- `NotePayload`: lightweight memo on a node
- `PlanPayload`: operation intent attached to an InputTransition
- `PredictionPayload`: predicted outcome attached to an OutputTransition
- `ResultPayload`: actual execution result attached to an OutputTransition
- `CutPayload`: append-only rewind marker on an InputTransition or OutputTransition

`PredictionPayload` and `ResultPayload` are mutually exclusive on the same OT; `RunGraph.attach_payload` enforces this.

There is no separate `SnapshotPayload` / `DerivedPayload` / `MatchPayload` in the current schema. Match information lives in `ResultPayload.matched_prediction_output_id`.

## RunHandle

`RunHandle` is defined in `src/optagent/core/run/handle.py` and binds verb implementations from sibling modules.

Public verbs (each implemented in `src/optagent/core/run/<verb>.py`):

- `plan(input_node_ids, plan_payload, *, user_id=None)`
- `observe(input_transition_id, result_payload, *, user_id=None)` (alias: `result`)
- `predict(input_transition_id, *, payloads=None, max_outcomes=None, user_id=None)`
- `note(node_id, text, *, tags=(), user_id=None)`
- `rewind(target_id, *, target_kind, reason=None, user_id=None)`
- `trace(node_id, ...)` (alias: `history`)
- `outcomes(...)`
- `view_create(name, *, root_node_id)`
- `view_list()`
- `view_show(name)`

When adding a new RunHandle method, implement it in a focused `src/optagent/core/run/<verb>.py` module and bind it in `handle.py`.

## CLI

`src/optagent/cli/main.py` dispatches to `src/optagent/cli/commands/<name>.py`.

Current commands:

- `current` / `use` — manage the active run pointer
- `init` / `list` — create / list runs
- `plan` / `predict` / `observe` / `note` / `rewind` — mutate the run
- `show` — inspect a node / IT / OT / payload as JSON
- `trace` / `outcomes` / `reachable` — derived queries
- `view` — manage `GraphView`s
- `dump` — render the whole run as `outline` (LLM-friendly) or `mermaid` (visual)
- `guide` — print usage hints

Commands resolve the target run in this order:

1. `--run`
2. `OPTAGENT_RUN_ID`
3. `<store-dir>/../current.json`

Mutating commands resolve user attribution in this order:

1. `--user`
2. `OPTAGENT_USER_ID`
3. `<store-dir>/../config.json` `user.id`
4. `"user"`

The `workflows/`, `domains/`, `execution/`, and `search/` packages are scaffolding unless the task explicitly wires them.

## `optagent dump` — render the run

`optagent dump` is the single command for getting the whole run structure in one shot. Two formats:

- `--format outline` (default): LLM-optimized indented spanning tree. Each node and each transition is rendered exactly once. Multi-input transitions are anchored under `input_node_ids[0]` (primary parent); additional inputs appear inline as `(+n_X)`; non-primary parents get a one-line `▸ feeds it_X (@n_primary)` pointer. Back-references use `↻n_X`. Predicted OTs use `⇢`, observed `→`, cuts `✂`. When ≥3 multi-input transitions exist, a top-level `joins:` index is emitted.
- `--format mermaid`: human/visual format. Renders a `flowchart TD` mermaid block. Single-input/single-output transitions become labeled edges; multi-input or multi-output transitions become diamond intermediate nodes. Class styles separate observed / predicted / cut / root.

Useful flags: `--node`, `--depth`, `--observed-only`, `--predicted-only`, `--full-payloads`.

Renderer code: `src/optagent/core/run/dump.py`. Tests: `tests/core/test_dump.py`.

## IDs

IDs are minted through `RunHandle._next_id(prefix)`.

Current prefixes include:

- `n` — Node
- `it` — InputTransition
- `ot` — OutputTransition
- `pl` — Payload
- `run` — Run

Do not hand-format new IDs except for seed roots created during `init` (the root node is always `n_0000`).

## Rewind

Rewind is append-only. It attaches a `CutPayload` to an InputTransition or OutputTransition; it does not delete nodes, transitions, plans, or payloads.

Activity is computed at read time in `src/optagent/core/cuts.py`:

- A `CutPayload` on an InputTransition makes the IT and all its OTs and downstream nodes inactive (cascading forward).
- A `CutPayload` on an OutputTransition makes that OT and its `to_node` (and descendants) inactive.

Writers that extend observed history must reject cut nodes via `_ensure_active_node(node_id)`.

## Storage

`JsonlRunStore` writes the current schema only. A run directory contains:

- `run.json`
- `graph.json` (RunGraph metadata + counters)
- `nodes.jsonl`
- `input_transitions.jsonl`
- `output_transitions.jsonl`
- `payloads.jsonl`
- `views.jsonl`

Do not preserve old `dags.jsonl` / `states.jsonl` / `plans.jsonl` / `transitions.jsonl` / `selections.jsonl` / `execution_plans.jsonl` compatibility unless requested.
