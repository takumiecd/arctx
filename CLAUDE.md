# CLAUDE.md

This file provides guidance to Claude Code when working in this repository.

## Commands

The packages are usually not installed during local development. Use `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src`.

This repo contains two Python packages plus one web frontend. The must-ship surface is **`arctx` (core) + `arctx-cli`**; the web GUI is a secondary surface and the intended interactive direction. Focus releases, tests, and docs on core + CLI.

The web frontend lives in **`web/`** (React + React Flow + Vite, import-free of the Python packages). It consumes the `arctx export --format json` document and, in live mode, the `arctx serve` HTTP API. The data contract is `arctx.core.run.export.json_document`, mirrored in `web/src/types.ts` — keep the two in sync. See `web/README.md`.
- `arctx` (import name `arctx`) — core API, payloads, extensions. See `packages/arctx/`. **Primary.**
- `arctx-cli` (import name `arctx_cli`, provides the `arctx` command) — argparse CLI. See `packages/arctx-cli/`. Depends only on `arctx`. **Primary.** Also hosts `arctx serve` (the dependency-free JSON API primitive every GUI frontend shares).
- The web GUI server is **`arctx.web` inside core** (there is no separate `arctx-web` package): `arctx web` serves the built `web/` frontend + the run API and opens a browser. Static assets resolve in this order: `ARCTX_WEB_STATIC` env override → sibling source build `web/dist` (source checkouts) → the packaged bundle written by `python -m arctx.web.bundle` (git-ignored). **Secondary — the batteries-included GUI surface.**

- Run all tests: `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=packages/arctx/src:packages/arctx-cli/src python3 -m pytest packages/arctx/tests packages/arctx-cli/tests --import-mode=importlib -q` (use python3.13; the system python3 is 3.9 and fails collection)
- Run one test file: `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src python3 -m pytest packages/arctx/tests/core/test_run_api.py -q`
- CLI: `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src python3 -m arctx_cli.main <subcommand> ...`
- GUI (requires a built frontend — `npm --prefix web run build` first): `PYTHONPATH=packages/arctx/src:packages/arctx-cli/src python3 -m arctx_cli.main web --run <run> --no-browser`
- Web frontend tests: `npm --prefix web test` (vitest; `src/layout.test.ts` pins the graph layout's invariants) and `npm --prefix web run typecheck`
- Optional checks configured in `pyproject.toml`: `ruff check .`, `black .`, `mypy packages/arctx/src packages/arctx-cli/src`

Docs are Japanese-first and should match the current implementation:

- `docs/ja/DIRECTION.md`
- `docs/ja/STATE_MODEL.md`
- `docs/ja/API.md`
- `docs/ja/CLI.md`
- `docs/ja/AGENT_LOOP.md`

## Version And Compatibility

This project is `0.4.9b1` beta. Breaking changes are acceptable and expected. Do not add compatibility shims for removed APIs unless explicitly requested. Old run storage schemas do not need migration support by default.

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
- `AssetPayload(payload_id, target_id, target_kind, commit, path, title=None)` — a **reference to a git object**, never a copy. `path` is repo-root-relative and may name a file *or a directory* (git has trees). Per "absent = self" there is no repo field: the repository is the one enclosing the run data. Nothing derivable is stored — no size, mime type, or bytes; those come from git at read time. Attach via `handle.attach_asset(...)` or `arctx asset attach`, which validates that `<commit>:<path>` resolves and warns (without blocking) when the commit is on no remote-tracking ref. The payload record itself is git-import-free; resolution plumbing lives in `packages/arctx/src/arctx/core/gitref.py` (every revision reaching a git argv is resolved to a full sha first — an unresolved value in a revision position is read by git as an option, and `--output=<path>` truncates that path) and the serve read path in `packages/arctx/src/arctx/serve/assets.py`.

**Git extension payloads** (`packages/arctx/src/arctx/ext/git/payloads.py`):
- `GitChangePayload(payload_id, target_id, branch, head_commit, commits=())` — git commit reference on a Step, recorded explicitly by `arctx git add --commit <sha>` (arctx never makes the commit itself). The record stores **facts only**: commit hashes and a branch. Diff stats, commit subjects, file lists, and patch text are derived at read time by `arctx.ext.git.derive.derive_git_change` / `derive_patch` over `arctx.core.gitref` plumbing ("jsonl は事実、見た目は導出"). Derivation never raises: a commit missing from the clone comes back with `available=False` and the explicit `(commit not available locally)` marker. Derived diffs exclude `.arctx/**`. Do not reintroduce `diff_summary`, `commit_log`, `CommitEntry`, `DiffSummary`, or baked `<run_dir>/artifacts/git/*.patch` files.
- `BranchPayload(...)`, `MergePayload`, `RevertPayload`, `CherryPickPayload`

**Optimize extension payloads** (`packages/arctx/src/arctx/ext/optimize/payloads.py`):
- `TrialPayload(payload_id, target_id, tables, config, metrics, title=None)` — one scored trial on a Step. A trial is a payload, not a graph record: a Step carries as many rows as you attach to it, so a sweep is one Step with N rows, not N Steps. `tables` are plain shared names (like lane names); **there is no table record** — which tables exist, their columns, column kinds, and best rows are all derived from the rows at read time in `arctx/ext/optimize/tables.py`. Write-time validation (`validate_trial`): a new column grows a table with a notice, but a column's value kind (number/bool/str) is fixed by the first active row — type conflicts are rejected before writing. Cutting a step frees a mistyped column (append-only eraser). Do not add a table-definition record or a member-list payload.
There is no repo registry and no `repo_id`. A run lives inside exactly one repository, so a git record with no repo qualifier means "the repo carrying this data" ("absent = self"). Branch tip events are keyed by branch alone.

**User subclasses**: inherit `PayloadBase`, set `payload_type` as a class-level `field(default="...", init=False)`, register with `register_payload_class(MyClass)`.

**Deserialization**: `payload_from_dict(data)` dispatches by `payload_type`. Unknown types fall back to `NodePayload` or `StepPayload` (generic) — CLI never crashes on unregistered custom types.

Old payload types `PlanPayload`, `PredictionPayload`, `ResultPayload`, `NotePayload` are deleted. Use `StepPayload(type="...")` and `NodePayload(type="note", content={"text": "..."})` instead.

## RunHandle

`RunHandle` is defined in `packages/arctx/src/arctx/core/run/handle.py` and binds verb implementations from sibling modules.

Public verbs (each implemented in `packages/arctx/src/arctx/core/run/<verb>.py`):

- `add_step(input_node_ids, payload, *, user_id=None, lane_id=None) -> Step` — create one Step and one output Node from input nodes; `payload` must be step-targeting
- `attach(target_id, payload, *, user_id=None, lane_id=None) -> PayloadBase` — attach a payload to an existing Node or Step; the payload's own `target_kind` picks which. Attaching never creates a Step or a Node, so one record can carry any number of payloads (a sweep is one Step with N trial rows)
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

- `lane` — manage lanes (flat, git-branch-like). `lane create NAME [--purpose TEXT]`, `lane switch`, `lane summarize NAME --summary TEXT` (refresh the current summary mid-work, lane stays open), `lane close NAME --summary TEXT`, `lane open`. Close always works: a lane with no active frontier stamps its chronologically last output node, and an *empty* lane closes with the summary riding the `lane_closed` event (`lane_overview` falls back to it). `lane validate`'s `default_lane_membership` warning only fires once the run has
a named lane: until then everything living in `default` is simply where it
starts, and warning about it made a new user's first `arctx add` complain about
the step it had just written. `lane create` warns on stderr about open lanes
with no writes for 7+ days (`arctx.core.lanes.stale_open_lanes`), and `guide --context` lists them — the "close your lanes" nudge. A lane's *current summary* is the latest `SummaryPayload` it owns, ordered by `record_event_rank` (the append-only work-event ledger, not jsonl line order).
- `current` / `use` — manage the active run pointer. `use <run> --shell` prints
  `export ARCTX_RUN_ID=<run>` for `eval` (terminal-scoped) instead of writing the
  repo pointer.
- `init` / `list` — create / list runs
- `add` — DAG core surface. Adds one `Step` from one or more input nodes and creates its output node. Both the public CLI and internal storage use `Step` (the `Transition` rename is complete). Nodes are not created standalone; a Node is born only as a Step's output (or the run root). There is no `add node` / `add step` command, no `RunHandle.add_node` verb, and no `POST /node` endpoint.
- `attach <id>` — attach a generic payload to a Node or Step by resolving the record id. A **payload id** resolves to the record it annotates (same as `trial add --to`), so an id copied out of `show` / `trials` always works. Attaching to a cut (or downstream-of-cut) record is allowed but prints a `notice:` on stderr; stdout stays pure JSON
- `asset` — git-object assets. `asset attach <TARGET_ID> <PATH> [--commit REF] [--title TEXT]` records a `(commit, path)` reference on a Node or Step (target kind auto-resolved like `attach`/`cut`); the file must already be committed. `asset show <PAYLOAD_ID>` prints the reference and whether it resolves in this clone (`found` / `missing_commit` / `missing_path` / `no_repository`).
- `explore` — flat, summary-first retrieval over lanes. No args: one line per lane (open first; closed folded into a count unless `--all`). `explore <LANE>`: that lane's purpose / full current summary / status / record counts / active frontiers. `explore --query "TERMS"`: case-insensitive AND search across lane names, purposes, and every payload a lane owns — the **primary** retrieval path, position-independent (no current lane, no descent), each hit carrying a snippet plus ids to jump to with `show`. `--json` in all modes. Core helpers live in `arctx.core.lanes` (`search_lanes`, `lane_overview`, `list_lane_overviews`, `lane_current_summary`, `record_event_rank`). Lanes are flat — never add breadcrumbs, ancestors, children, or stale detection.
- `guide` — print the agent-facing usage guide and current run/lane context. The static text is deliberately short (it is a cognitive-load budget): three write verbs (open a lane → `add` → close with a summary, plus `reparent` and `lane summarize`) and three retrieval questions (`guide --context` / `explore --query` / `dump`+`show`). `--context` prints Run ID, run purpose, current lane (status/purpose/current summary), active frontiers, and enabled extensions — no ancestor chain, since there is no lane tree.
- `log` — user-facing DAG history command; wraps outline dump / trace behavior
- Internal compatibility helpers remain in `commands.step`, `commands.node`, and `commands.payload`, but the public DAG core surface should use `add`, `show`, and `attach`.
- `cut` — cut a Node or Step (`cut node NODE_ID` or `cut step T_ID`)
- There is **no** `claude-code` command. The Claude Code hooks adapter was removed; `arctx.ext.agents.SessionRecorder` remains as the harness-neutral recording vocabulary (neutral `agent.*` payload types, harness name in payload metadata) that a future adapter would write through, and `arctx/ext/claude_code/` + `arctx/ext/codex/` remain unregistered with no in-tree consumer. Do not document a CLI surface for them until one is registered in `arctx.ext.__init__`.
- `git` — canonical namespace for git extension commands: `git add` (record commit hashes on a Step), `git list` / `git show` (read them back; `show` adds the diff git reports for them right now), and `git verify` (descendant constraint over all steps). **arctx does not run git and does not listen to git.** The write verbs (`git commit` / `revert` / `merge` / `cherry-pick` / `reset` / `branch`), the `post-commit` / `post-merge` / `post-rewrite` hooks and their installation, `git init`, and `git worktree` were all removed: arctx's own git subprocesses tripped arctx's own hooks and double-recorded, hook-driven adoption guessed a graph position `arctx add` tracks by other means, and `arctx git commit` desynchronized from `arctx add`. Do not reintroduce them. Recording a commit is explicit: `arctx add` makes the Step, `arctx git add --commit <sha>` names the commit on it.
- `topic` / `topics` — flat, name-keyed bundles of meaning (core; derived views in `arctx.core.topics`, no topic record). `topic tag NAME ID...` marks any nodes/steps as belonging to a subject — connectivity is NOT required and is never validated; the view groups tagged records into islands by *lineage* (two records share an island when one derives from the other over the active graph, transitively through tagged records — sibling branches are separate islands), and 2+ islands is a join *candidate*, not an error. `topic summarize NAME --summary TEXT [--source ID]` is the subject's current statement (generic payload `type="topic_summary"`; latest by record_event_rank wins, append-order tie-break). `guide --context` prints the top current statements and the topics that are split. `topic log NAME` walks the statement history (oldest belief to current). Tags/summaries are plain generic payloads (`type="tag"`) so old readers degrade gracefully.
  A split subject has exactly four resolutions, and each is a verb; the nudge prints all four as runnable commands on stderr (exit 0, never a prompt — agents drive this CLI too) from `topic tag` (only when the tag *increased* the island count), `topic summarize`, `topic NAME`, and `guide --context`.
  - `topic join NAME --summary TEXT` — both lineages are right under different conditions. One Step from every island tip (`island_tips`), the new output node tagged with the topic, then the statement attached to that node. **The tag on the output node is what merges the islands** — islands are computed over *tagged* records, so a bare `add --from A --from B` leaves them split; that is why the wrapper exists. A join has no "correct side": inputs are a set, and the verdict is the node that comes after, which is why `--summary` is required (same discipline as `lane close`).
  - `topic split NAME --island N --into NEW --summary TEXT` — it was two subjects; untag the island, tag it with the new name, give the new topic its statement. Both topics end with one island.
  - `arctx cut ID` — that island was a dead end.
  - `topic join NAME` with no `--summary` reuses the current statement when it already cites two or more islands (`island_statements`): the subject was settled in prose and only the graph lagged behind.
  - `topic summarize` **refuses** to write a statement anchored to one island when the current statement is anchored to another (`--force` overrides). "Latest wins" is right for one line of reasoning and wrong across unjoined lineages — it would drop a live conclusion from every view. Which island each statement speaks for is derived from its `sources` plus the node it was written on (`statement_islands`): one island means it speaks for that lineage alone, two or more means it reconciles them.
  - `topic untag NAME ID...` — the tag was a mistake. Append-only supersession on the `(topic, record)` pair (generic payload `type="untag"`; last marker wins by record_event_rank, so `tag → untag → tag` restores it), and unlike `cut` the record itself stays active. Never use `cut` for a mis-tag, or `untag` for a dead end.
- `trial` / `trials` — optimize extension (enable with `arctx ext enable optimize`). `trial add --table NAME --col k=v --metric k=v` records one scored Step (defaults `--from` to the current lane frontier like `add`; repeatable `--table` for multi-membership). Rows are payloads, so a sweep does not have to grow the graph: `trial add --to TARGET_ID ...` appends a row to an existing Step (step id / its output node id / another row's payload id), and `trial add --rows PATH|-` writes a whole JSONL/JSON-array batch onto one Step (the batch is validated against itself before anything is written). A row's identity is its payload id — that is the first column of `arctx trials NAME`, with a `step` column only when rows share a Step. `notice:` lines go to stderr so stdout stays pure JSON. `trials` lists every table with columns and kinds; `trials NAME [--sort COL] [--best min:COL] [--json]` prints the derived comparison table.
- `doctor` — check a run's files and report every unreadable line, plus the one
graph state where a read would answer untruthfully (`multiple_active_producers`);
the wider lane-hygiene rules stay in `arctx lane validate`, since legitimate
runs break them by design and history is append-only so they can never be
cleared with its file and line number (`--json` for machine output, exit 1 when unhealthy). One unparsable line stops every reader, so `--repair` moves those lines to `<file>.broken` and rewrites the file without them; nothing is deleted, and `run.json` / `graph.json` are reported but never rewritten. Scanner lives in `packages/arctx/src/arctx/storage/doctor.py`.
- `show` — inspect a node / step / payload as JSON
- `graph` — dump / trace / reachable graph queries
- `dump` — render the whole run as `outline` (LLM-friendly) or `mermaid` (visual)
- `export` — render the run as a shareable document: `md` (default) / `tex` / `html` / `json`. `md/tex/html` emit the human-facing spanning-tree outline; `json` emits the machine-readable data contract for GUI surfaces (all nodes/steps/payloads in full, with a precomputed `inactive` flag per node/step). `--exclude-cut` drops cut records. Renderer: `packages/arctx/src/arctx/core/run/export.py`.
- `serve` — local read/write HTTP API for one run (live-mode backend for GUIs). `GET /run` returns the same JSON document as `export --format json`; `POST /step` / `POST /attach` (node or step) / `POST /cut` write through the same verbs as `add` / `attach` / `cut`; `GET /health` for liveness. Asset reads resolve git objects at request time: `GET /asset` (reference + resolution status), `GET /asset/entries` (directory listing), `GET /asset/content` (utf-8 or base64), and `GET /asset/raw` (raw bytes; the one binary route, served by the HTTP shell over the same pure resolver in `arctx/serve/assets.py`) — all take `payload_id` plus an optional `path` relative to the asset's own path. Stdlib-only (`http.server`), default bind `127.0.0.1:8787`. A browser can reach a loopback port from any page, so every request is checked by `arctx/serve/guard.py` before it is served: a non-loopback `Origin` or `Host` is refused with 403 (Origin stops cross-site writes — a `text/plain` POST needs no preflight, so withholding CORS headers would not; Host stops DNS rebinding). `--cors-origin` names extra allowed origins and is no longer `*` by default. Two layers: harness-neutral pure dispatcher `arctx/serve/api.py` (`dispatch(...)`, socket-free and unit-tested) + thin `http.server` shell `arctx/serve/server.py`. The JSON shapes are the contract a future FastAPI port would expose unchanged.

Deleted or unregistered commands: `plan`, `predict`, `observe`, `note`, `view`, `sync`, `anchor`, `node`, `step`, `payload`, `trace`, `reachable`, `outcomes`, `migrate` (the sqlite backend it converted to is gone), `tui` (the Textual TUI was removed from the repo entirely — see `arctx web`),
and the git write surface: `git commit`, `git revert`, `git merge`,
`git cherry-pick`, `git reset`, `git branch`, `git hook`, `git init`,
`git worktree`. Removed with them: the shortcut aliases `arctx commit`, `arctx revert`, `arctx branch`, `arctx reset`, `arctx hook`.

`arctx verify` is an alias-layer shortcut resolving to `arctx git verify`; it
is the only git shortcut left. Register new git CLI surface under the canonical
`git` namespace first.

Aliases come from extension defaults and from `~/.config/arctx/aliases.toml`
only. There is deliberately **no** run-local alias tier: a run travels with its
repository, so `<run_dir>/aliases.toml` was attacker-controlled data read at the
highest priority, and an alias like `show = "cut node"` turned a read command
into a write on a received run. Do not reintroduce it.

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

`JsonlRunStore` writes the current schema only. The load cache is **not** in the run directory — it is a pickle, and unpickling is executing, so it lives under a machine-local cache root (`ARCTX_CACHE_DIR` → `$XDG_CACHE_HOME/arctx` → `~/.cache/arctx`) keyed by the run directory's absolute path; a legacy `run.cache.pkl` found inside a run directory is deleted on sight, never read. A run directory contains:

- `run.json`
- `graph.json` (RunGraph metadata)
- `nodes.jsonl`
- `steps.jsonl` — each row has `step_id`, `input_node_ids`, `output_node_id`, `metadata`
- `payloads.jsonl` — dispatched by `payload_type` on load
- `lanes.jsonl`
- `lane_events.jsonl`

Old files `edges.jsonl`, `input_transitions.jsonl`, `output_transitions.jsonl`, `dags.jsonl`, `states.jsonl` do not exist in the current schema.

`append_batch` re-checks the batch **inside the run lock, against a fresh read**
and raises `ConcurrentWriteRejected` if applying it would leave a node with two
active producing steps, or if the batch's lane was closed in the meantime
(`--force` sets `AppendBatch.force` and is honoured, as it is at the CLI gate —
the gate itself runs before the lock, so it could not see a lane closed after
the writer's snapshot). The lock only ever covered the append, not the decision
that produced it, so two writers that loaded the same state both concluded they
were the only one retiring a node's producer, and both appended — silently.
The check is deliberately narrow: only the invariant a stale snapshot can break,
computed without lane membership so it stays cheap on a path every write takes.
Pre-existing breakage does not block an unrelated write. `ConcurrentWriteRejected.retryable` says whether trying again can help — a
stale decision can be redone, a lane that closed cannot. The closed-lane
recheck is opt-in (`AppendBatch.require_lane_open`), set only by the commands
that run the CLI gate — `cut` / `uncut` / `reparent` never did and have no
`--force`, so cutting a mistaken record inside a lane you just closed stays
legal. `arctx reparent` wraps its whole load-decide-write cycle in
`arctx_cli.write_retry.with_write_retry` (jittered backoff; without it
contending writers reload in lockstep and the same ones keep losing),
so a losing writer redoes the decision against the current state and lands the
sequential outcome instead of reporting an error the user did not cause.
Retrying only the append would resubmit the same stale decision, which is why
the retry is around the cycle. `validate=False` skips the check and exists for
callers that have already done the equivalent.

`JsonlRunStore` is the only store. Do not reintroduce a second backend: storage
is git-native, so a store git cannot carry is not an alternative canon — the
removed `SqliteRunStore` wrote to a gitignored `run.db`, which meant selecting it
silently froze the committed jsonl. `resolve_store` refuses any backend other
than `jsonl` with an error that says so.

Payload deserialization uses `payload_from_dict(data)` which dispatches by `payload_type`. Fallback: unknown types become generic `NodePayload` / `StepPayload`.
