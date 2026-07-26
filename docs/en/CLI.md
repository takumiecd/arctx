# CLI

## Quick Start

For a normal git-backed run in one repository:

```bash
cd ~/dev/my-repo
arctx init req_demo --run-id demo --extension git
arctx git init
arctx current
arctx git commit -m "implement first step"
arctx dump --format outline
```

What those setup commands do:

- `arctx init <req_id>` creates a run under `<repo_root>/.arctx/runs` (git-native
  storage: run data lives inside the repository and sharing is just git). It also
  writes `<repo_root>/.arctx/.gitattributes` (`* linguist-generated=true`,
  `*.jsonl merge=union`) and `.arctx/.gitignore` (derived files such as
  `run.cache.pkl` / `run.db`), idempotently. When `ARCTX_HOME` is set, or when run
  outside a git repo, `<ARCTX_HOME>/runs` is used instead.
- `arctx init ... --extension git` also enables the git extension for that run.
  When run inside a git repo, it writes this repo's `<gitdir>/arctx-id` and
  installs hooks unless `--no-hooks` / `--git-no-hooks` is used.
- `arctx git init` binds this checkout to the run (writes the repo pointer) and
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
- **Parallel agents:** prefer `arctx lane env` or
  `arctx lane spawn`, which pins both the run and the lane in
  process-local environment variables.

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
- `arctx lane create <name>`: create a lane without switching to it.
- `arctx lane switch <name-or-id>`: switch to an existing lane.
- `arctx lane summaries <name-or-id>`: list `SummaryPayload`s on active terminal
  nodes in the lane. Branched lanes can return multiple summaries.
- `arctx export [--format md|tex|html]`: render a run as a shareable document.

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
`arctx git ...`; shortcut aliases such as `arctx commit` are kept for daily use.

Extension command namespaces are loaded from the resolved current run. If
`arctx git ...` is not visible, first make sure the command can resolve a run
that was created with `--extension git`: pass `--run <id>`, set
`ARCTX_RUN_ID`, or run from a repo that has `<gitdir>/arctx-id`.

Setup commands:

- `arctx init <req_id> --extension git`: create a run and enable the git
  extension. Inside a git repo, this also writes `<gitdir>/arctx-id` and
  installs hooks.
- `arctx git init [--repo-path P] [--no-hooks]`: bind this checkout to the
  current run and install hooks.

Daily git verbs:

- `arctx git commit -m "message"` / `arctx commit -m "message"`
  - The input node is normally resolved from the lane / branch tip.
    Pass `--from NODE` to branch off a chosen node instead (repeat for a
    fan-in) — this is how experiments fan out as siblings from a shared
    baseline.
- `arctx git branch list` / `arctx branch list`
- `arctx git branch show <name>` / `arctx branch show <name>`
- `arctx git revert --sha SHA` / `arctx revert --sha SHA`
- `arctx git cherry-pick --sha SHA` / `arctx cherry-pick --sha SHA`
- `arctx git merge --other branch:<name>` / `arctx merge --other branch:<name>`
- `arctx git reset --node NODE --mode hard` / `arctx reset --node NODE --mode hard`
- `arctx git verify` / `arctx verify`
- `arctx git hook install` / `arctx hook install`

Commit attachment commands:

- `arctx git add --step T --commit SHA`: attach commit hashes to a step.
- `arctx git list --step T`
- `arctx git show --step T`

Worktree helpers:

- `arctx git worktree add <path> [branch] [--base REF] [--existing-branch]`:
  thin wrapper over `git worktree add`. Creates a new branch named after the
  path leaf when `branch` is omitted.
- `arctx git worktree list`: JSON-parsed `git worktree list --porcelain`.
- `arctx git worktree remove <path> [--force]`: wrapper over
  `git worktree remove`.

## Work Sessions

A work session is the attribution unit for parallel agents or terminals working
in the same run. Mutating CLI commands append under a lock, so concurrent
writers serialize their new records instead of overwriting existing history.

- `arctx lane start [--user U] [--lane WS]`: create a work
  session and print its id.
- `arctx lane env [--new] [--run R] [--user U]`: print shell exports
  for `ARCTX_RUN_ID`, `ARCTX_LANE_ID`, and `ARCTX_USER_ID`.
- `arctx lane spawn [--user U] -- <cmd>`: run a child command with a
  child-only work session.
- `arctx lane list` / `arctx lane show <ws_id>`: inspect work
  sessions.

Fixed-mode example:

```bash
eval "$(arctx lane env --run run_x --new --user codex)"
arctx add --from NODE_ID --type suggestion
```

Spawn example:

```bash
arctx lane spawn --run run_x --user codex -- codex
arctx lane spawn --run run_x --user claude-code -- claude
```

Attribution resolution:

- user: `--user` -> `ARCTX_USER_ID` -> `<ARCTX_HOME>/config.json` `user.id` -> `user`
- work session: `--lane` -> `ARCTX_LANE_ID` ->
  `<ARCTX_HOME>/config.json` `lane.id` -> `default`

## Worktree Attachment

- `arctx lane start --worktree PATH`
- `arctx lane env --new --worktree PATH`
- `arctx lane spawn --worktree PATH -- <cmd>`

These commands record the resolved worktree path on
`Lane.metadata["worktree"]` and export `ARCTX_GIT_WORKTREE=PATH`.

When `ARCTX_GIT_WORKTREE` is set, git verbs (`arctx git commit`, `revert`,
`cherry-pick`, `merge`, `reset`, `verify`, and the post-rewrite hook) run their
git subprocesses with `cwd=$ARCTX_GIT_WORKTREE` instead of the shell cwd. Use
this with `arctx git worktree add` to give each agent an isolated checkout
while sharing one ARCTX run.

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
