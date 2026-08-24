# CLI

## Quick Start

For a normal git-backed run in one repository:

```bash
cd ~/dev/my-repo
arctx init req_demo --run-id demo --extension git
arctx current
git commit -m "implement first step"
arctx add --title "implement first step" --type commit --commit HEAD
arctx dump --format outline
```

What those setup commands do:

- `arctx init <req_id>` creates a run under `<repo_root>/.arctx/runs` (git-native
  storage: run data lives inside the repository and sharing is just git). It also
  writes `<repo_root>/.arctx/.gitattributes` (`* linguist-generated=true`,
  `*.jsonl merge=union`) and `.arctx/.gitignore` (derived files such as
  `run.cache.pkl`), idempotently. Only files that can be regenerated may be
  excluded — excluding something a write goes to keeps that record out of every
  commit. When `ARCTX_HOME` is set, or when run outside a git repo,
  `<ARCTX_HOME>/runs` is used instead.
- `arctx init ... --extension git` also enables the git extension for that run.
  When run inside a git repo, it writes this repo's `<gitdir>/arctx-id` and
  installs hooks unless `--no-hooks` / `--git-no-hooks` is used.
- `arctx init --extension git` binds this checkout to the run (writes the repo pointer) and
  installs hooks.
- `arctx use <run_id>` switches the current repo to an existing run by writing
  `<gitdir>/arctx-id`.
- `eval "$(arctx use <run_id> --shell)"` switches only the current terminal by
  exporting `ARCTX_RUN_ID`; it writes no files.

There is no global per-machine current run.

## Current Run Resolution

Most read and write commands accept `--run`. If it is omitted, ARCTX resolves
the target run in this order:

```text
--run <id>            one command only (highest priority)
ARCTX_RUN_ID          current shell / process tree
<gitdir>/arctx-id     persistent default for this git checkout
```

Use the modes deliberately:

- **One-off command:** pass `--run <id>`.
- **Stay in one repo:** run `arctx use <run_id>` once in that repo.
- **Move across several repos in one terminal:** run
  `eval "$(arctx use <run_id> --shell)"`; the environment variable wins over
  each repo's pointer.
- **Parallel agents:** pin both the run and the lane in process-local
  environment variables — `eval "$(arctx use <run_id> --shell)"` and
  `eval "$(arctx lane switch <name> --shell)"`.

`arctx current` reads the repo pointer (`<gitdir>/arctx-id`) and prints that
repo's persistent default. It does not report an `ARCTX_RUN_ID` override.

## Basic Graph Flow

```bash
arctx init req_demo --run-id demo
ROOT=$(arctx show --run demo | jq -r .root_node_id)
STEP=$(arctx add --run demo --from "$ROOT" --type experiment --field lr=0.01 | jq -r .id)
NODE=$(arctx show "$STEP" --run demo | jq -r .step.output_node_id)
arctx attach "$NODE" --run demo --type note --field text="observed result"
arctx cut "$NODE" --run demo --reason "discarded"
arctx log --run demo
```

Core commands:

- `arctx init <req_id>`: create a run.
- `arctx list`: list runs.
- `arctx current`: show the repo-scoped current run pointer.
- `arctx use <run_id>`: write the repo-scoped current run pointer.
- `arctx use <run_id> --shell`: print an `ARCTX_RUN_ID` export for shell-local
  pinning.
- `arctx lane create <name> [--purpose TEXT]`: create a lane without switching
  to it. `--purpose` is recorded on the lane and shown by `arctx explore` and
  `arctx guide --context`.
- `arctx lane switch <name-or-id>`: switch to an existing lane.
- `arctx lane summarize <name-or-id> --summary "..."`: refresh the lane's
  current summary *without* closing it — the mid-work counterpart of
  `lane close`. Summaries are append-only; the latest wins.
- `arctx lane summaries <name-or-id>`: list `SummaryPayload`s on active terminal
  nodes in the lane. Branched lanes can return multiple summaries.
- `arctx export [--format md|tex|html]`: render a run as a shareable document.

## arctx explore

Lanes are flat, so there is nothing to descend. `explore` answers two of the
three retrieval questions (`guide --context` answers the first).

- `arctx explore`: one line per lane — status marker, name, and the current
  summary collapsed to its first line (truncated to ~160 chars). Open lanes come
  first (by `started_at`); closed lanes fold into `N closed lanes — use --all`,
  the way `git branch` hides noise. `--all` shows them.
- `arctx explore <LANE>`: that lane's overview — purpose, full current summary,
  status, direct record counts, and active frontiers. Name or id.
- `arctx explore --query "TERMS"`: **the primary retrieval path**. Whitespace
  separated terms match case-insensitively with AND semantics across lane names,
  lane purposes, and every payload a lane owns. Each hit prints the lane name and
  status, a ~180-char snippet around the first term, and the record/payload ids
  to jump to with `arctx show`. Name matches rank first. Position-independent:
  no current lane, no descent, and closed lanes are equally findable.
- `--json` works in all three modes.

Snippets exclude opaque ids (`pl_`/`n_`/`t_`) — if you already have an id, use
`arctx show <ID>` rather than search. A lane's *current summary* is the latest
`SummaryPayload` it owns, ordered by the append-only work-event ledger rather
than jsonl line order (which a union merge may reorder).

## arctx guide

- `arctx guide`: the static usage guide plus the dynamic Current Context. The
  static text covers exactly the three write verbs (open a lane → `add` → close
  with a summary, plus `reparent` and `lane summarize`) and the three retrieval
  questions; its length is a cognitive-load budget.
- `arctx guide --context`: only the dynamic block — Run ID, run purpose, current
  lane (status, purpose, current summary), active frontiers, enabled extensions.
  No ancestor chain: there is no lane tree. Cheap enough to call every turn.

## DAG Records

- `arctx add --from NODE --type TYPE --field key=value`: add a step and its output node. A node is born only as a step's output (or the run root).
- `arctx attach <node-or-step-id> --type TYPE --field key=value`: attach a payload.
- `arctx attach NODE --payload-type diagram --json '{"title":"retry loop","format":"mermaid","source":"flowchart TD\n  fetch --> retry\n  retry --> fetch"}'`: attach a cyclic-capable diagram/model artifact when the `diagram` extension is enabled.
- `arctx show <node-or-step-or-payload-id>`: inspect one record with attached payloads.

Each step has exactly one output node. Create fan-out by running `add`
multiple times from the same input node. Create a multi-input join by passing
repeated `--from` flags.

## Cut

- `arctx cut <node_id>`
- `arctx cut step <step_id>`

Cutting records an inactive branch. It does not delete history.

## Git Integration

Git integration is a standard extension. The canonical command namespace is
`arctx git ...`; `arctx verify` is the only shortcut alias left.

**arctx does not run git and does not install hooks.** You make the commit,
then record its sha. `git commit` / `revert` / `merge` / `cherry-pick` /
`reset` / `branch` / `init` / `hook` / `worktree` were removed: arctx's own git
subprocesses tripped arctx's own hooks and double-recorded, and hook-driven
adoption guessed a graph position `arctx add` already tracks.

Extension command namespaces are loaded from the resolved current run. If
`arctx git ...` is not visible, first make sure the command can resolve a run
that was created with `--extension git`: pass `--run <id>`, set
`ARCTX_RUN_ID`, or run from a repo that has `<gitdir>/arctx-id`.

Setup commands:

- `arctx init <req_id> --extension git`: create a run and enable the git
  extension. Inside a git repo, this also writes `<gitdir>/arctx-id` and
  installs hooks.
- `arctx init <req_id> --extension git`: create the run, enable the git
  extension, and (inside a repo) write `<gitdir>/arctx-id`. No hooks.

Recording day to day:

- `git commit -m "message"` then
  `arctx add --title "message" --type commit --commit HEAD`
  - One command records both the Step and the commit it stands for. Exactly
    one mechanism tracks lane position — `arctx add`'s — so nothing can drift.
  - Input nodes resolve from the lane frontier; pass `--from NODE` (repeatable
    for fan-in) to branch off a chosen node instead.
- `arctx git verify` / `arctx verify`: descendant constraint over all steps.

Commit attachment commands:

- `arctx git add --step T --commit SHA`: attach commit hashes to a step.
- `arctx git list --step T`: list the attached commit hashes.
- `arctx git show --step T`: print each git_change record plus a `derived` block
  — subject, author, date, diff stat, and changed files, **read from git at
  display time**.

A `GitChangePayload` stores facts only: the commit hashes (`head_commit` and
`commits`) and the `branch`. Diff text and commit metadata are never recorded;
`arctx.ext.git.derive` reads them back out of the repository on every display.
If the commit is not in this clone (shallow clone, never pushed), derivation
does not fail — it returns `available: false` with an explicit
`(commit not available locally)` marker. Derived diffs exclude `.arctx/**`,
since recording commit N necessarily lands in commit N+1 and the run data is not
the change under review.

Worktree helpers:


## Parallel attribution

A lane is the attribution unit for parallel agents or terminals working in the
same run. Mutating CLI commands append under a lock, so concurrent writers
serialize their new records instead of overwriting existing history.

Pinning is done with environment variables; there are no dedicated session
commands (`lane start` / `lane env` / `lane spawn` were removed — the lane verbs
are `create` / `switch` / `close` / `open` / `list` / `show` / `summaries` /
`validate`).

```bash
eval "$(arctx use run_x --shell)"            # export ARCTX_RUN_ID=run_x
arctx lane create codex --purpose "..." --user codex
eval "$(arctx lane switch codex --shell)"    # export ARCTX_LANE_ID=lane_...
export ARCTX_USER_ID=codex

arctx add --from NODE_ID --type suggestion
```

Without `--shell`, `arctx lane switch` writes the repo-wide pointer
(`<gitdir>/arctx-lane`). With it, nothing is written — so several terminals
sharing one checkout can hold different lanes.

To hand a child process its own lane, pass the variables when launching it:

```bash
ARCTX_LANE_ID=$(arctx lane show codex --json | jq -r .lane.lane_id) \
ARCTX_USER_ID=codex codex
```

Attribution resolution:

- user: `--user` -> `ARCTX_USER_ID` -> `<ARCTX_HOME>/config.json` `user.id` -> `user`
- work session: `--lane` -> `ARCTX_LANE_ID` ->
  `<ARCTX_HOME>/config.json` `lane.id` -> `default`

## Worktree Attachment

Attaching a worktree is exporting one variable; there is no dedicated command
(`lane start` / `lane env` / `lane spawn` were removed).

```bash
git worktree add ../wt-claude -b claude/vec

eval "$(arctx use demo --shell)"             # this terminal's run
arctx lane create claude --purpose "vectorization" --user claude
eval "$(arctx lane switch claude --shell)"   # this terminal's lane
export ARCTX_USER_ID=claude
cd ../wt-claude       # this terminal's checkout
```

arctx never runs git, so there is nothing to point at a worktree: commit in it
and run `arctx add --commit HEAD` there. One ARCTX run is shared across the
worktrees; their lifecycle stays entirely in git.

## Export

`arctx export` is distinct from `dump`: `dump` is for inspection and LLM
context, while `export` produces an artifact to hand to people.

- `--format md|tex|html` (default `md`)
- `--exclude-cut`: drop cut nodes/steps.
- `--node` / `--depth` / `--full-payloads`: traversal options shared with
  `dump`.
- `--output PATH` / `-o PATH`: write to a file instead of stdout.

## Graph

- `arctx graph dump [--format outline|mermaid]`
- `arctx graph trace <node_id>`
- `arctx graph reachable <node_id>`

`arctx dump` is the canonical whole-run renderer; `arctx graph dump` is the
same thing under the `graph` namespace.
Top-level `trace`, `reachable`, and `outcomes` are unregistered; use
`arctx log --to`, `arctx graph trace`, `arctx graph reachable`, and `arctx show`.

Removed commands: `arctx plan`, `arctx predict`, `arctx observe`, and
`arctx note`. Unregistered legacy plumbing commands include `arctx node`,
`arctx step`, `arctx payload`, `arctx trace`, `arctx reachable`, and
`arctx outcomes`.
