# CLI

Basic flow:

```bash
arctx init req_demo --run-id demo
arctx transition create --run demo --from <root_node_id> --payload-type transition_payload --field type=experiment --field lr=0.01
arctx payload add --run demo --node <node_id> --payload-type node_payload --field type=note --field text="observed result"
arctx cut node <node_id> --run demo --reason "discarded"
arctx graph dump --run demo --format outline
```

Core commands:

- `arctx init <req_id>`: create a run
- `arctx list`: list runs
- `arctx use <run_id>` / `arctx current`: manage the active run pointer
- `arctx export [--format md|tex|html]`: render the run as a shareable document

Resolving the current run:

Mutating/read commands pick the target run in this order:

```
--run <id>            one-off (highest priority)
ARCTX_RUN_ID          per terminal (shell)
<gitdir>/arctx-id     persistent per-repo default
```

- `arctx use <run_id>`: writes `<gitdir>/arctx-id` (**repo-scoped, persistent**;
  every terminal entering that repo sees it).
- `arctx use <run_id> --shell`: writes nothing and prints
  `export ARCTX_RUN_ID=<run>`. Use `eval "$(arctx use <run_id> --shell)"` to pin
  the run for the **current terminal only** — handy when following one run that
  spans several repos (env beats the repo pointer).

There is no global (per-PC) current pointer.

Node:

- `arctx node show <node_id>`
- `arctx node payloads <node_id>`

Transition:

- `arctx transition create --from NODE --payload-type TYPE --field key=value`
- `arctx transition show <transition_id>`
- `arctx transition output <transition_id>`
- `arctx transition inputs <transition_id>`
- `arctx transition payloads <transition_id>`

Each transition has exactly one output node. Create multiple sibling transitions by running `transition create` multiple times from the same input node.

Payload:

- `arctx payload types`
- `arctx payload schema <payload_type>`
- `arctx payload add --node NODE --payload-type TYPE --field key=value`
- `arctx payload add --transition TRANSITION --payload-type TYPE --field key=value`
- `arctx payload list --node NODE` / `arctx payload list --transition TRANSITION`
- `arctx payload show <payload_id>`

Cut / Git:

- `arctx cut node <node_id>` / `arctx cut transition <transition_id>`

Git integration is a standard extension. The canonical command namespace is
`arctx git ...`; shortcut aliases such as `arctx commit` are kept for daily use.

- `arctx init <req_id> --extension git`: enable the git extension for a run
- `arctx git init`: register the cwd repo into the current run's registry and
  install hooks (wraps `git repo add`; the entry point for binding the first
  repo to an existing run)
- `arctx git commit -m "message"` / `arctx commit -m "message"`
- `arctx git branch list` / `arctx branch list`
- `arctx git branch show <name>` / `arctx branch show <name>`
- `arctx git revert --sha SHA` / `arctx revert --sha SHA`
- `arctx git cherry-pick --sha SHA` / `arctx cherry-pick --sha SHA`
- `arctx git merge --other branch:<name>` / `arctx merge --other branch:<name>`
- `arctx git reset --node NODE --mode hard` / `arctx reset --node NODE --mode hard`
- `arctx git verify` / `arctx verify`
- `arctx git hook install` / `arctx hook install`
- `arctx git add --transition T --commit SHA` — attach commit hashes to a
  Transition (distinct from `git repo add`)
- `arctx git list --transition T`
- `arctx git show --transition T`
- `arctx git worktree add <path> [branch] [--base REF] [--existing-branch]` — thin wrapper over `git worktree add`. Creates a new branch named after the path leaf when `branch` is omitted.
- `arctx git worktree list` — JSON-parsed `git worktree list --porcelain` output.
- `arctx git worktree remove <path> [--force]` — wrapper over `git worktree remove`.

Multiple repos (the repo registry):

One run can span several git repos. The run holds a **registry** of repos
(`RepoPayload`); git payloads reference a repo by `repo_id` only. Core stays
repo-agnostic.

- `arctx git repo add [--repo-path P] [--slug USER/REPO] [--no-hooks]` — register
  a repo into the current run (the "join an existing run" verb). Adds a
  `RepoPayload`, writes that repo's `.arctx-id` pointing at the current run, and
  writes a `.arctx-repo` marker. Idempotent.
- `arctx git repo list` — list the registry as JSON.
- `arctx git repo show [--repo-id ID | --repo-path P]` — show one entry;
  resolves via the cwd `.arctx-repo` marker when `--repo-id` is omitted.

Registry entry: `repo_id` (opaque primary key) / `slug` (USER/REPO display name)
/ `remotes` (every URL form, ssh + https) / `canonical` (normalized key matching
ssh and https) / `local_path` (this machine's checkout). `local_path` is
environment-specific and is stripped on export/share; `repo list` / `repo show`
are local-inspection commands and show it.

Joining a second repo:

```bash
cd ~/dev/frontend && arctx init "feature X" --run-id run_x --extension git
arctx git init                           # register frontend
cd ~/dev/backend  && arctx git repo add --run run_x   # join the same run
# commit in either repo; tips are keyed by (repo_id, branch), so two mains never collide
```

Export (shareable document):

`arctx export` is distinct from `dump` (inspection / LLM): it produces an
artifact to hand to people.

- `--format md|tex|html` (default `md`)
- `--exclude-cut` — drop cut (inactive) nodes/transitions (kept by default)
- `--include-local` — include repo `local_path` (stripped by default)
- `--node` / `--depth` / `--full-payloads` — same traversal options as `dump`
- `--output PATH` / `-o PATH` — write to a file (default stdout)

When repos are registered, a Repos section is included.

Worktree attachment:

- `arctx work-session start --worktree PATH` / `arctx work-session env --new --worktree PATH` / `arctx work-session spawn --worktree PATH -- <cmd>` — record the resolved worktree path (plus current branch and `git --git-common-dir`) on `WorkSession.metadata["worktree"]` and export `ARCTX_GIT_WORKTREE=PATH`.
- `ARCTX_GIT_WORKTREE` env var — when set, every git verb (`arctx git commit / revert / cherry-pick / merge / reset / verify` and the post-rewrite hook) runs its `git` subprocess with `cwd=$ARCTX_GIT_WORKTREE` instead of the shell cwd. Combine with `arctx git worktree add` to give each agent an isolated checkout while still sharing one ARCTX run.

Graph:

- `arctx graph dump [--format outline|mermaid]`
- `arctx graph trace <node_id>`
- `arctx graph reachable <node_id>`

Compatibility commands such as `arctx show`, `arctx dump`, `arctx trace`, `arctx reachable`, and `arctx outcomes` still exist. Prefer the `node`, `transition`, `payload`, and `graph` namespaces for new usage.
