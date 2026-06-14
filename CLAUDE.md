# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Commands

The packages are usually not installed during local development. Use `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src:packages/arctx-tui/src`.

This repo contains three packages:
- `arctx` (import name `arctx`) — core API, payloads, extensions. See `packages/arctx/`.
- `arctx-cli` (import name `arctx_cli`, provides the `arctx` command) — argparse CLI. See `packages/arctx-cli/`. Depends only on `arctx`.
- `arctx-tui` (import name `arctx_tui`, provides the `arctx-tui` command) — Textual TUI. See `packages/arctx-tui/`. Depends only on `arctx` and `textual`. Install separately: `pip install arctx-tui`.

- Run all tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/arctx/src:packages/arctx-cli/src:packages/arctx-tui/src python3 -m pytest packages/arctx/tests packages/arctx-cli/tests packages/arctx-tui/tests --import-mode=importlib -q`
- Run one test file: `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src python3 -m pytest packages/arctx/tests/core/test_run_api.py -q`
- CLI: `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src python3 -m arctx_cli.main <subcommand> ...`
- TUI (requires textual installed): `PYTHONPATH=packages/arctx/src:packages/arctx-tui/src python3 -m arctx_tui.main`
- Optional checks configured in `pyproject.toml`: `ruff check .`, `black .`, `mypy packages/arctx/src packages/arctx-cli/src packages/arctx-tui/src`

Docs are Japanese-first and should match the current implementation:

- `docs/ja/DIRECTION.md`
- `docs/ja/STATE_MODEL.md`
- `docs/ja/API.md`
- `docs/ja/CLI.md`
- `docs/ja/AGENT_LOOP.md`

## Version And Compatibility

This project is `0.3.0b1` beta. Breaking changes are acceptable and expected. Do not add compatibility shims for removed APIs unless explicitly requested. Old run storage schemas do not need migration support by default.

## Architecture

ARCTX records the process of optimization/problem-solving. It is not a planner, executor, benchmark runner, or general agent framework.

The current core model is **a single RunGraph plus attached payloads**. Pure graph records carry no domain data; everything domain-specific is on Payload records. Core is standalone; git integration is the standard extension in `packages/arctx/src/arctx/ext/git/`.

Pure graph records (`packages/arctx/src/arctx/core/schema/graph.py`):

- `Node`: pure DAG node
- `Transition`: connects many input nodes to exactly one output node (`input_node_ids: tuple[str, ...]`, `output_node_id: str`). Fan-out is represented as sibling Transitions sharing the same input nodes.

Container (`packages/arctx/src/arctx/core/run_graph.py`):

- `RunGraph`: holds all nodes / transitions / payloads, plus reverse-lookup indices

There is no `Edge` record, no `InputTransition`/`OutputTransition` split, and no `transition_kind()` method. Kind is expressed by the `type` field on the attached `TransitionPayload`.

Avoid reintroducing `Dag`, `StateNode`, `ExecutionPlan`, `PredictionPlan`, `ObservedTransition`, `PredictedTransition`, `ActionResult`, `DerivedRecord`, `InputTransition`, `OutputTransition`, `PlanPayload`, `PredictionPayload`, `ResultPayload`, or `NotePayload` as public symbols.

## Payloads

Two-tier design. Core payloads live under `packages/arctx/src/arctx/core/schema/payloads.py`; extension payloads live with their extension.

**Generic payloads** (use `type` string to distinguish purpose):
- `NodePayload(payload_id, target_id, type, content={}, metadata={})` — any node annotation
- `TransitionPayload(payload_id, target_id, type, content={}, metadata={})` — any transition annotation

**Core typed payloads**:
- `CutPayload(payload_id, target_id, target_kind, reason=None)` — append-only cut marker
- `JoinPayload(payload_id, target_id, joined_views)` — transition-targeting marker for a multi-input transition that joins independent histories with no common ancestor (extension-agnostic; `target_kind="transition"`)

**Git extension payloads** (`packages/arctx/src/arctx/ext/git/payloads.py`):
- `GitChangePayload(payload_id, target_id, branch, head_commit, diff_summary, commit_log=(), repo_id="")` — git record on a Transition
- `BranchPayload(..., repo_id="")`, `MergePayload`, `RevertPayload`, `CherryPickPayload`
- `RepoPayload(payload_id, target_id, repo_id, slug, remotes, canonical, local_path)` — run-scoped repo registry entry (the 対応表), attached to the run root node. `RemoteRef(kind, url)` holds each known remote URL form. git payloads reference a repo by `repo_id` only. `local_path` is environment-specific and is stripped on export/share (`RepoPayload.shareable()`). Registry/resolution helpers live in `packages/arctx/src/arctx/ext/git/registry.py` (`resolve_repo_id`, `list_repos`, `normalize_remote_url`). Branch tip events are keyed by `(repo_id, branch)`.

**User subclasses**: inherit `PayloadBase`, set `payload_type` as a class-level `field(default="...", init=False)`, register with `register_payload_class(MyClass)`.

**Deserialization**: `payload_from_dict(data)` dispatches by `payload_type`. Unknown types fall back to `NodePayload` or `TransitionPayload` (generic) — CLI never crashes on unregistered custom types.

Old payload types `PlanPayload`, `PredictionPayload`, `ResultPayload`, `NotePayload` are deleted. Use `TransitionPayload(type="...")` and `NodePayload(type="note", content={"text": "..."})` instead.

## RunHandle

`RunHandle` is defined in `packages/arctx/src/arctx/core/run/handle.py` and binds verb implementations from sibling modules.

Public verbs (each implemented in `packages/arctx/src/arctx/core/run/<verb>.py`):

- `transition(input_node_ids, payload, *, user_id=None, work_session_id=None) -> Transition` — create one Transition and one output Node from input nodes; `payload` must be transition-targeting
- `attach(node_id, payload, *, user_id=None, work_session_id=None) -> PayloadBase` — attach a node-targeting payload to a node
- `cut(target_id, *, target_kind, reason=None, user_id=None, work_session_id=None) -> CutPayload` — mark a Node or Transition inactive
- `anchor(from_node_id, label, ...)` — create a lightweight scope anchor node
- `trace(node_id, ...)` (alias: `history`) — walk history backwards
- `outcomes(transition_id)` — return output node info for a transition

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
- `add node` / `add step` — Phase 1 DAG core surface; externally call transitions "steps" while internal storage still uses `Transition`
- `attach <id>` — attach a generic payload to a Node or Step by resolving the record id
- `log` — user-facing DAG history command; wraps outline dump / trace behavior
- `transition create` — create one Transition and one output Node (`--from NODE --payload-type TYPE --field key=value`)
- `node` — inspect Nodes and their payloads
- `payload` — list payload types/schemas and attach payloads to Nodes or Transitions
- `cut` — cut a Node or Transition (`cut node NODE_ID` or `cut transition T_ID`)
- `claude-code` — Claude Code hooks adapter. `claude-code install` merges hook entries into `.claude/settings.json` (idempotent; `--command` overrides the hook command for non-PATH installs); `claude-code hook` consumes one hook event JSON from stdin and records it (session → WorkSession `ws_cc_<session_id>`, prompt/tool use → Transition, Stop/SessionEnd → NodePayload on the session tip). Fail-safe: exits 0 on any error unless `--strict`. Two layers: recording semantics live in the harness-neutral `arctx.ext.agents.SessionRecorder` (neutral `agent.*` payload types, harness name in payload metadata — the cross-harness data contract); `arctx/ext/claude_code/adapter.py` only translates hook JSON into recorder calls. New harness adapters should follow the same shape.
- `git` — canonical namespace for git extension commands (`git commit`, `git verify`, `git branch`, `git init`, `git repo add/list/show`, plus `git add/list/show`). `git init` registers the cwd repo into the run and installs hooks (wraps `git repo add`). `git repo add` is the multi-repo "join an existing run" verb — distinct from `git add`, which attaches commit hashes to a Transition.
- `show` — inspect a node / transition / payload as JSON
- `graph` — dump / trace / reachable graph queries
- `trace` / `outcomes` / `reachable` — compatibility derived queries
- `dump` — render the whole run as `outline` (LLM-friendly) or `mermaid` (visual)
- `export` — render the run as a shareable document: `md` (default) / `tex` / `html`. `--exclude-cut` drops cut records; `--include-local` keeps repo `local_path` (stripped by default). Renderer: `packages/arctx/src/arctx/core/run/export.py`.
- `anchor` — create a scope anchor node
- `migrate` — convert a jsonl run dir to sqlite

Deleted commands: `plan`, `predict`, `observe`, `note`, `guide`, `view`, `tui` (moved to standalone `arctx-tui` command).

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

- `--format outline` (default): LLM-optimized indented spanning tree. Each node and transition rendered exactly once. Multi-input transitions anchored under `input_node_ids[0]`; additional inputs shown inline as `(+n_X)`; non-primary parents show `▸ feeds t_X (@n_primary)`. Back-references use `↻n_X`. Cuts show `✂`. When ≥3 multi-input transitions exist, a top-level `joins:` index is emitted.
- `--format mermaid`: human/visual format. Renders a `flowchart TD` mermaid block. Each Transition becomes labeled edges from each input to the single output.

Useful flags: `--node`, `--depth`, `--full-payloads`.

Renderer code: `packages/arctx/src/arctx/core/run/dump.py`. Tests: `packages/arctx/tests/core/test_dump.py`.

## IDs

IDs are minted through `RunHandle._next_id(prefix)` (delegates to `opaque_id(prefix)`).

Current prefixes:

- `n` — Node
- `t` — Transition
- `pl` — Payload
- `run` — Run
- `we` — WorkEvent

IDs are opaque and collision-resistant (`n_<uuid>`, `t_<uuid>`, `pl_<uuid>`). Do not assume sequential IDs. The root node is opaque; use `run.root_node_id` or the `root_node_id` returned by `run_init_command`.

## Cut

Cut is append-only. It attaches a `CutPayload` to a Node or Transition; it does not delete records.

Activity is computed at read time in `packages/arctx/src/arctx/core/cuts.py`:

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
- `work_sessions.jsonl`
- `work_events.jsonl`

Old files `edges.jsonl`, `input_transitions.jsonl`, `output_transitions.jsonl`, `dags.jsonl`, `states.jsonl` do not exist in the current schema.

`SqliteRunStore` stores the same data in a per-run `run.db`.

Payload deserialization uses `payload_from_dict(data)` which dispatches by `payload_type`. Fallback: unknown types become generic `NodePayload` / `TransitionPayload`.
