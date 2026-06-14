# CLI

## Quick Start

For a normal git-backed run in one repository:

```bash
cd ~/dev/my-repo
arctx init req_demo --run-id demo --extension git
arctx git init
arctx current
arctx git commit -m "implement first step"
arctx graph dump --format outline
```

What those setup commands do:

- `arctx init <req_id>` creates a run under `<ARCTX_HOME>/runs`.
- `arctx init ... --extension git` also enables the git extension for that run.
  When run inside a git repo, it writes this repo's `<gitdir>/arctx-id` and
  installs hooks unless `--no-hooks` / `--git-no-hooks` is used.
- `arctx git init` registers the current repo in the run's repo registry,
  writes the repo pointer, writes the `.arctx-repo` marker, and installs hooks.
  Run it once per repo you want to bind explicitly to the current run.
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
- **Parallel agents:** prefer `arctx work-session env` or
  `arctx work-session spawn`, which pins both the run and the work-session in
  process-local environment variables.

`arctx current` reads the repo pointer (`<gitdir>/arctx-id`) and prints that
repo's persistent default. It does not report an `ARCTX_RUN_ID` override.

## Basic Graph Flow

```bash
arctx init req_demo --run-id demo
ROOT=$(arctx show --run demo | jq -r .root_node_id)
STEP=$(arctx add step --run demo --from "$ROOT" --type experiment --field lr=0.01 | jq -r .id)
NODE=$(arctx show "$STEP" --run demo | jq -r .step.output_node_id)
arctx attach "$NODE" --run demo --type note --field text="observed result"
arctx cut "$NODE" --run demo --reason "discarded"
arctx log --run demo --format outline
```

Core commands:

- `arctx init <req_id>`: create a run.
- `arctx list`: list runs.
- `arctx current`: show the repo-scoped current run pointer.
- `arctx use <run_id>`: write the repo-scoped current run pointer.
- `arctx use <run_id> --shell`: print an `ARCTX_RUN_ID` export for shell-local
  pinning.
- `arctx export [--format md|tex|html]`: render a run as a shareable document.

## DAG Records

- `arctx add node`: add a standalone node.
- `arctx add step --from NODE --type TYPE --field key=value`: add a step and its output node.
- `arctx attach <node-or-step-id> --type TYPE --field key=value`: attach a payload.
- `arctx show <node-or-step-or-payload-id>`: inspect one record with attached payloads.

Each step has exactly one output node. Create fan-out by running `add step`
multiple times from the same input node. Create a multi-input join by passing
repeated `--from` flags.

## Cut

- `arctx cut <node_id>`
- `arctx cut transition <transition_id>`

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
  installs hooks, but use `arctx git init` when you want to explicitly register
  the repo in the run registry.
- `arctx git init [--repo-path P] [--slug USER/REPO] [--no-hooks]`: register a
  repo into the current run and install hooks. This is the preferred "bind this
  checkout to this run" command.
- `arctx git repo add [--repo-path P] [--slug USER/REPO] [--no-hooks]`: same
  registration primitive, useful when joining another repo to an existing run.
- `arctx git repo list`: list registered repos as JSON.
- `arctx git repo show [--repo-id ID | --repo-path P]`: show one registry entry.

Daily git verbs:

- `arctx git commit -m "message"` / `arctx commit -m "message"`
  - The input node is normally resolved from the work-session / branch tip.
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

- `arctx git add --transition T --commit SHA`: attach commit hashes to a
  transition. This is different from `arctx git repo add`.
- `arctx git list --transition T`
- `arctx git show --transition T`

Worktree helpers:

- `arctx git worktree add <path> [branch] [--base REF] [--existing-branch]`:
  thin wrapper over `git worktree add`. Creates a new branch named after the
  path leaf when `branch` is omitted.
- `arctx git worktree list`: JSON-parsed `git worktree list --porcelain`.
- `arctx git worktree remove <path> [--force]`: wrapper over
  `git worktree remove`.

## Multiple Repos

One ARCTX run can span several git repos. The run stores a repo registry
(`RepoPayload`), and git payloads reference repos by `repo_id`. Core graph
records remain repo-agnostic.

Typical flow:

```bash
cd ~/dev/frontend
arctx init "feature X" --run-id run_x --extension git
arctx git init

cd ~/dev/backend
arctx git repo add --run run_x
```

After that, commits from either repo land in the same run. Branch tips are
keyed by `(repo_id, branch)`, so `frontend/main` and `backend/main` do not
collide.

Registry entry fields:

- `repo_id`: opaque primary key stored in the run.
- `slug`: display name such as `USER/REPO`.
- `remotes`: every discovered remote URL form.
- `canonical`: normalized remote key, matching SSH and HTTPS forms.
- `local_path`: this machine's checkout path.

`local_path` is environment-specific. `arctx export` strips it by default;
`arctx git repo list` and `arctx git repo show` keep it because they are local
inspection commands.

## Work Sessions

A work session is the attribution unit for parallel agents or terminals working
in the same run. Mutating CLI commands append under a lock, so concurrent
writers serialize their new records instead of overwriting existing history.

- `arctx work-session start [--user U] [--work-session WS]`: create a work
  session and print its id.
- `arctx work-session env [--new] [--run R] [--user U]`: print shell exports
  for `ARCTX_RUN_ID`, `ARCTX_WORK_SESSION_ID`, and `ARCTX_USER_ID`.
- `arctx work-session spawn [--user U] -- <cmd>`: run a child command with a
  child-only work session.
- `arctx work-session list` / `arctx work-session show <ws_id>`: inspect work
  sessions.

Fixed-mode example:

```bash
eval "$(arctx work-session env --run run_x --new --user codex)"
arctx add step --from NODE_ID --type suggestion
```

Spawn example:

```bash
arctx work-session spawn --run run_x --user codex -- codex
arctx work-session spawn --run run_x --user claude-code -- claude
```

Attribution resolution:

- user: `--user` -> `ARCTX_USER_ID` -> `<ARCTX_HOME>/config.json` `user.id` -> `user`
- work session: `--work-session` -> `ARCTX_WORK_SESSION_ID` ->
  `<ARCTX_HOME>/config.json` `work_session.id` -> `default`

## Worktree Attachment

- `arctx work-session start --worktree PATH`
- `arctx work-session env --new --worktree PATH`
- `arctx work-session spawn --worktree PATH -- <cmd>`

These commands record the resolved worktree path on
`WorkSession.metadata["worktree"]` and export `ARCTX_GIT_WORKTREE=PATH`.

When `ARCTX_GIT_WORKTREE` is set, git verbs (`arctx git commit`, `revert`,
`cherry-pick`, `merge`, `reset`, `verify`, and the post-rewrite hook) run their
git subprocesses with `cwd=$ARCTX_GIT_WORKTREE` instead of the shell cwd. Use
this with `arctx git worktree add` to give each agent an isolated checkout
while sharing one ARCTX run.

## Export

`arctx export` is distinct from `dump`: `dump` is for inspection and LLM
context, while `export` produces an artifact to hand to people.

- `--format md|tex|html` (default `md`)
- `--exclude-cut`: drop cut nodes/transitions.
- `--include-local`: include repo `local_path` values.
- `--node` / `--depth` / `--full-payloads`: traversal options shared with
  `dump`.
- `--output PATH` / `-o PATH`: write to a file instead of stdout.

When repos are registered, export includes a Repos section.

## Graph

- `arctx graph dump [--format outline|mermaid]`
- `arctx graph trace <node_id>`
- `arctx graph reachable <node_id>`

`arctx dump` remains as a compatibility shortcut for `arctx graph dump`.
Top-level `trace`, `reachable`, and `outcomes` are unregistered; use
`arctx log --to`, `arctx graph trace`, `arctx graph reachable`, and `arctx show`.

Removed commands: `arctx plan`, `arctx predict`, `arctx observe`, and
`arctx note`. Unregistered legacy plumbing commands include `arctx node`,
`arctx transition`, `arctx payload`, `arctx trace`, `arctx reachable`, and
`arctx outcomes`.
