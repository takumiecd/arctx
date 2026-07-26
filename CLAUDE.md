# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Commands

The packages are usually not installed during local development. Use `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src:packages/arctx-tui/src`.

This repo contains four Python packages plus one web frontend. The primary, must-ship surface is **`arctx` (core) + `arctx-cli`**; `arctx-tui` and `arctx-web` are de-prioritized secondary surfaces. The web GUI is the intended interactive direction (the TUI is experimental/legacy). Focus releases, tests, and docs on core + CLI.

The web frontend lives in **`web/`** (React + React Flow + Vite, import-free of the Python packages). It consumes the `arctx export --format json` document and, in live mode, the `arctx serve` HTTP API. The data contract is `arctx.core.run.export.json_document`, mirrored in `web/src/types.ts` — keep the two in sync. See `web/README.md`.
- `arctx` (import name `arctx`) — core API, payloads, extensions. See `packages/arctx/`. **Primary.**
- `arctx-cli` (import name `arctx_cli`, provides the `arctx` command) — argparse CLI. See `packages/arctx-cli/`. Depends only on `arctx`. **Primary.** Also hosts `arctx serve` (the dependency-free JSON API primitive every GUI frontend shares).
- `arctx-tui` (import name `arctx_tui`, provides the `arctx-tui` command) — Textual TUI. See `packages/arctx-tui/`. Depends only on `arctx` and `textual`. Install separately: `pip install arctx-tui`. **Experimental / secondary — not a release blocker; may lag behind core+CLI.**
- `arctx-web` (import name `arctx_web`, provides the `arctx-web` command) — serves the built `web/` frontend + the run API + opens a browser. See `packages/arctx-web/`. Depends on `arctx` and `arctx-cli` (reuses `arctx_cli.serve.api.dispatch`, so the API contract has one source of truth). Bundles built frontend assets via `python -m arctx_web.bundle` (git-ignored; falls back to `web/dist` in a source checkout). Install separately: `pip install arctx-web`. **Secondary — the batteries-included GUI surface.**

- Run all tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/arctx/src:packages/arctx-cli/src:packages/arctx-tui/src:packages/arctx-web/src python3 -m pytest packages/arctx/tests packages/arctx-cli/tests packages/arctx-tui/tests packages/arctx-web/tests --import-mode=importlib -q`
- Run one test file: `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src python3 -m pytest packages/arctx/tests/core/test_run_api.py -q`
- CLI: `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src python3 -m arctx_cli.main <subcommand> ...`
- TUI (requires textual installed): `PYTHONPATH=packages/arctx/src:packages/arctx-tui/src python3 -m arctx_tui.main`
- GUI (requires a built frontend — `npm --prefix web run build` first): `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src:packages/arctx-web/src python3 -m arctx_web.main --run <run> --no-browser`
- Optional checks configured in `pyproject.toml`: `ruff check .`, `black .`, `mypy packages/arctx/src packages/arctx-cli/src packages/arctx-tui/src`

Docs are Japanese-first and should match the current implementation:

- `docs/ja/DIRECTION.md`
- `docs/ja/STATE_MODEL.md`
- `docs/ja/API.md`
- `docs/ja/CLI.md`
- `docs/ja/AGENT_LOOP.md`

## Version And Compatibility

This project is `0.3.1b4` beta. Breaking changes are acceptable and expected. Do not add compatibility shims for removed APIs unless explicitly requested. Old run storage schemas do not need migration support by default.

## Architecture

ARCTX records the process of optimization/problem-solving. It is not a planner, executor, benchmark runner, or general agent framework.

The current core model is **a single RunGraph plus attached payloads**. Pure graph records carry no domain data; everything domain-specific is on Payload records. Core is standalone; git integration is the standard extension in `packages/arctx/src/arctx/ext/git/`.

Pure graph records (`packages/arctx/src/arctx/core/schema/graph.py`):

- `Node`: pure DAG node
- `Step`: connects many input nodes to exactly one output node (`input_node_ids: tuple[str, ...]`, `output_node_id: str`). Fan-out is represented as sibling Steps sharing the same input nodes.

Container (`packages/arctx/src/arctx/core/run_graph.py`):

- `RunGraph`: holds all nodes / steps / payloads, plus reverse-lookup indices

There is no `Edge` record, no `InputTransition`/`OutputTransition` split, and no `step_kind()` method. Kind is expressed by the `type` field on the attached `StepPayload`.

Avoid reintroducing `Dag`, `StateNode`, `ExecutionPlan`, `PredictionPlan`, `ObservedTransition`, `PredictedTransition`, `ActionResult`, `DerivedRecord`, `InputTransition`, `OutputTransition`, `PlanPayload`, `PredictionPayload`, `ResultPayload`, or `NotePayload` as public symbols.

## Payloads

Two-tier design. Core payloads live under `packages/arctx/src/arctx/core/schema/payloads.py`; extension payloads live with their extension.

**Generic payloads** (use `type` string to distinguish purpose):
- `NodePayload(payload_id, target_id, type, content={}, metadata={})` — any node annotation
- `StepPayload(payload_id, target_id, type, content={}, metadata={})` — any step annotation

**Core typed payloads**:
- `CutPayload(payload_id, target_id, target_kind, reason=None)` — append-only cut marker
- `UncutPayload(payload_id, target_id, target_kind, reason=None)` — append-only reversal of a cut on the same target. Effective cut state is "last cut/uncut marker wins" (supersession), computed in `packages/arctx/src/arctx/core/cuts.py`. Cuts are never deleted.
- `SummaryPayload(payload_id, target_id, text, metadata={})` — node-targeting context snapshot for history truncation / hand-off. Descriptive and monotonic (never changes node/descendant validity). `trace(..., stop_at_summary=True)` prunes the backward walk at the nearest summary.
- `JoinPayload(payload_id, target_id, joined_views)` — step-targeting marker for a multi-input step that joins independent histories with no common ancestor (extension-agnostic; `target_kind="step"`)
- `AssetPayload(payload_id, target_id, target_kind, commit, path, title=None)` — a **reference to a git object**, never a copy. `path` is repo-root-relative and may name a file *or a directory* (git has trees). Per "absent = self" there is no repo field: the repository is the one enclosing the run data. Nothing derivable is stored — no size, mime type, or bytes; those come from git at read time. Attach via `handle.attach_asset(...)` or `arctx asset attach`, which validates that `<commit>:<path>` resolves and warns (without blocking) when the commit is on no remote-tracking ref. The payload record itself is git-import-free; resolution plumbing lives in `packages/arctx/src/arctx/core/gitref.py` and the serve read path in `packages/arctx/src/arctx/serve/assets.py`.

**Git extension payloads** (`packages/arctx/src/arctx/ext/git/payloads.py`):
- `GitChangePayload(payload_id, target_id, branch, head_commit, diff_summary, commit_log=())` — git record on a Step
- `BranchPayload(...)`, `MergePayload`, `RevertPayload`, `CherryPickPayload`
There is no repo registry and no `repo_id`. A run lives inside exactly one repository, so a git record with no repo qualifier means "the repo carrying this data" ("absent = self"). Branch tip events are keyed by branch alone.

**User subclasses**: inherit `PayloadBase`, set `payload_type` as a class-level `field(default="...", init=False)`, register with `register_payload_class(MyClass)`.

**Deserialization**: `payload_from_dict(data)` dispatches by `payload_type`. Unknown types fall back to `NodePayload` or `StepPayload` (generic) — CLI never crashes on unregistered custom types.

Old payload types `PlanPayload`, `PredictionPayload`, `ResultPayload`, `NotePayload` are deleted. Use `StepPayload(type="...")` and `NodePayload(type="note", content={"text": "..."})` instead.

## RunHandle

`RunHandle` is defined in `packages/arctx/src/arctx/core/run/handle.py` and binds verb implementations from sibling modules.

Public verbs (each implemented in `packages/arctx/src/arctx/core/run/<verb>.py`):

- `add_step(input_node_ids, payload, *, user_id=None, lane_id=None) -> Step` — create one Step and one output Node from input nodes; `payload` must be step-targeting
- `attach(node_id, payload, *, user_id=None, lane_id=None) -> PayloadBase` — attach a node-targeting payload to a node
- `attach_asset(target_id, path, *, commit=None, target_kind=None, title=None, repo_root=None, user_id=None, lane_id=None) -> AssetAttachment` — reference a git object (`commit` defaults to the enclosing repo's HEAD; `path` may be a file or a directory). Validates the reference against git and returns `AssetAttachment(payload, warning, kind)`; `warning` carries the non-blocking "commit is not pushed" notice and is deliberately not stored on the record
- `cut(target_id, *, target_kind, reason=None, user_id=None, lane_id=None) -> CutPayload` — mark a Node or Step inactive
- `uncut(target_id, *, target_kind, reason=None, user_id=None, lane_id=None) -> UncutPayload` — append-only reversal of a cut (supersession). Step uncut is guarded so a node never gets a second active producer.
- `reparent(node_id, new_input_node_ids, payload, *, reason=None, user_id=None, lane_id=None) -> Step` — append a new producing Step (new inputs → `node_id`) and cut the previously-active producer, re-parenting a node while preserving its descendants. A node may have multiple producing Steps but at most one active (the active subgraph stays a tree); `payload` must be step-targeting.
- `trace(node_id, ..., stop_at_summary=False)` (alias: `history`) — walk history backwards; `stop_at_summary` prunes at the nearest `SummaryPayload`
- `outcomes(step_id)` — return output node info for a step

Deleted verbs: `plan`, `predict`, `observe`, `note`.

Git verbs are extension verbs under `handle.git`: `handle.git.commit(...)`,
`handle.git.revert(...)`, `handle.git.cherry_pick(...)`,
`handle.git.reset(...)`, `handle.git.merge(...)`, and `handle.git.verify(...)`.
Do not add top-level `handle.commit` / `handle.verify` compatibility shims.

When adding a new RunHandle method, implement it in a focused `packages/arctx/src/arctx/core/run/<verb>.py` module and bind it in `handle.py`.

## CLI

`packages/arctx-cli/src/arctx_cli/main.py` dispatches to `packages/arctx-cli/src/arctx_cli/commands/<name>.py`.

Current commands:

- `current` / `use` — manage the active run pointer. `use <run> --shell` prints
  `export ARCTX_RUN_ID=<run>` for `eval` (terminal-scoped) instead of writing the
  repo pointer.
- `init` / `list` — create / list runs
- `add` — DAG core surface. Adds one `Step` from one or more input nodes and creates its output node. Both the public CLI and internal storage use `Step` (the `Transition` rename is complete). Nodes are not created standalone; a Node is born only as a Step's output (or the run root). There is no `add node` / `add step` command, no `RunHandle.add_node` verb, and no `POST /node` endpoint.
- `attach <id>` — attach a generic payload to a Node or Step by resolving the record id
- `asset` — git-object assets. `asset attach <TARGET_ID> <PATH> [--commit REF] [--title TEXT]` records a `(commit, path)` reference on a Node or Step (target kind auto-resolved like `attach`/`cut`); the file must already be committed. `asset show <PAYLOAD_ID>` prints the reference and whether it resolves in this clone (`found` / `missing_commit` / `missing_path` / `no_repository`).
- `guide` — print the agent-facing usage guide and current run/lane context
- `log` — user-facing DAG history command; wraps outline dump / trace behavior
- Internal compatibility helpers remain in `commands.step`, `commands.node`, and `commands.payload`, but the public DAG core surface should use `add`, `show`, and `attach`.
- `cut` — cut a Node or Step (`cut node NODE_ID` or `cut step T_ID`)
- `claude-code` — Claude Code hooks adapter. `claude-code install` merges hook entries into `.claude/settings.json` (idempotent; `--command` overrides the hook command for non-PATH installs); `claude-code hook` consumes one hook event JSON from stdin and records it (session → Lane `ws_cc_<session_id>`, prompt/tool use → Step, Stop/SessionEnd → NodePayload on the session tip). Fail-safe: exits 0 on any error unless `--strict`. Two layers: recording semantics live in the harness-neutral `arctx.ext.agents.SessionRecorder` (neutral `agent.*` payload types, harness name in payload metadata — the cross-harness data contract); `arctx/ext/claude_code/adapter.py` only translates hook JSON into recorder calls. New harness adapters should follow the same shape.
- `git` — canonical namespace for git extension commands (`git commit`, `git verify`, `git branch`, `git init`, plus `git add/list/show`). `git init` points this checkout at the run (`.arctx-id`) and installs hooks. `git add` attaches commit hashes to a Step.
- `show` — inspect a node / step / payload as JSON
- `graph` — dump / trace / reachable graph queries
- `dump` — render the whole run as `outline` (LLM-friendly) or `mermaid` (visual)
- `export` — render the run as a shareable document: `md` (default) / `tex` / `html` / `json`. `md/tex/html` emit the human-facing spanning-tree outline; `json` emits the machine-readable data contract for GUI surfaces (all nodes/steps/payloads in full, with a precomputed `inactive` flag per node/step). `--exclude-cut` drops cut records. Renderer: `packages/arctx/src/arctx/core/run/export.py`.
- `serve` — local read/write HTTP API for one run (live-mode backend for GUIs). `GET /run` returns the same JSON document as `export --format json`; `POST /step` / `POST /attach` (node or step) / `POST /cut` write through the same verbs as `add` / `attach` / `cut`; `GET /health` for liveness. Asset reads resolve git objects at request time: `GET /asset` (reference + resolution status), `GET /asset/entries` (directory listing), `GET /asset/content` (utf-8 or base64), and `GET /asset/raw` (raw bytes; the one binary route, served by the HTTP shell over the same pure resolver in `arctx/serve/assets.py`) — all take `payload_id` plus an optional `path` relative to the asset's own path. Stdlib-only (`http.server`), CORS-enabled (`--cors-origin`), default bind `127.0.0.1:8787`. Two layers: harness-neutral pure dispatcher `arctx/serve/api.py` (`dispatch(...)`, socket-free and unit-tested) + thin `http.server` shell `arctx/serve/server.py`. The JSON shapes are the contract a future FastAPI port would expose unchanged.
- `migrate` — convert a jsonl run dir to sqlite

Deleted or unregistered commands: `plan`, `predict`, `observe`, `note`, `view`, `sync`, `anchor`, `node`, `step`, `payload`, `trace`, `reachable`, `outcomes`, `tui` (moved to standalone `arctx-tui` command).

Git shortcut commands such as `arctx commit`, `arctx verify`, `arctx branch`,
`arctx reset`, and `arctx hook` are alias-layer shortcuts that resolve to
`arctx git ...`. Register new git CLI surface under the canonical `git`
namespace first.

Commands resolve the target run in this order:

1. `--run`
2. `ARCTX_RUN_ID`
3. nearest git repo `.arctx-id`

Mutating commands resolve user attribution in this order:

1. `--user`
2. `ARCTX_USER_ID`
3. `<ARCTX_HOME>/config.json` `user.id`
4. `"user"`

The `workflows/`, `domains/`, `execution/`, and `search/` packages are scaffolding unless the task explicitly wires them.

## `arctx dump` — render the run

`arctx dump` is the single command for getting the whole run structure in one shot. Two formats:

- `--format outline` (default): LLM-optimized indented spanning tree. Each node and step rendered exactly once. Multi-input steps anchored under `input_node_ids[0]`; additional inputs shown inline as `(+n_X)`; non-primary parents show `▸ feeds t_X (@n_primary)`. Back-references use `↻n_X`. Cuts show `✂`. When ≥3 multi-input steps exist, a top-level `joins:` index is emitted.
- `--format mermaid`: human/visual format. Renders a `flowchart TD` mermaid block. Each Step becomes labeled edges from each input to the single output.

Useful flags: `--node`, `--depth`, `--full-payloads`.

Renderer code: `packages/arctx/src/arctx/core/run/dump.py`. Tests: `packages/arctx/tests/core/test_dump.py`.

## IDs

IDs are minted through `RunHandle._next_id(prefix)` (delegates to `opaque_id(prefix)`).

Current prefixes:

- `n` — Node
- `t` — Step
- `pl` — Payload
- `run` — Run
- `we` — WorkEvent

IDs are opaque and collision-resistant (`n_<uuid>`, `t_<uuid>`, `pl_<uuid>`). Do not assume sequential IDs. The root node is opaque; use `run.root_node_id` or the `root_node_id` returned by `run_init_command`.

## Cut

Cut is append-only. It attaches a `CutPayload` to a Node or Step; it does not delete records.

Activity is computed at read time in `packages/arctx/src/arctx/core/cuts.py`:

- A `CutPayload` on a Node makes that node and all downstream Steps and Nodes inactive.
- A `CutPayload` on a Step makes that Step and its output Node (and descendants) inactive.

Writers that extend observed history must reject cut nodes via `_ensure_active_node(node_id)`.

## Lanes

A lane is a **flat**, git-branch-like unit of work: name / purpose / status
(open, closed) / a required summary on close. There is no declared parent-child
relation between lanes — branching is already recorded by the DAG (a lane's
first Step takes its input from another lane's node). There is no `lane link`
/ `unlink` / `adopt`, no `parent_lane_id`, and no hierarchy validation.
Membership is structural: a Step belongs to the lane current at creation time
and its output Node inherits the Step's lane. Verbs: `lane create` / `switch` /
`close --summary` / `open` / `list` / `show` / `summaries` / `validate`.

## Storage

`JsonlRunStore` writes the current schema only. A run directory contains:

- `run.json`
- `graph.json` (RunGraph metadata)
- `nodes.jsonl`
- `steps.jsonl` — each row has `step_id`, `input_node_ids`, `output_node_id`, `metadata`
- `payloads.jsonl` — dispatched by `payload_type` on load
- `lanes.jsonl`
- `lane_events.jsonl`

Old files `edges.jsonl`, `input_transitions.jsonl`, `output_transitions.jsonl`, `dags.jsonl`, `states.jsonl` do not exist in the current schema.

`SqliteRunStore` stores the same data in a per-run `run.db`.

Payload deserialization uses `payload_from_dict(data)` which dispatches by `payload_type`. Fallback: unknown types become generic `NodePayload` / `StepPayload`.
