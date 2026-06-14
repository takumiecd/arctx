# Agent Loop

## Recommended Loop

1. Read context with `arctx log`.
2. Append intent with `arctx add step --from NODE_ID --type suggestion --field proposal="..."`.
3. Do external work: implementation, experiment, review, debugging, or research.
4. Append the result with `arctx add step --from NODE_ID --type implementation --field result="..."`.
5. Cut wrong branches with `arctx cut NODE_ID` instead of deleting records.
6. At checkpoints, produce an artifact with `arctx export --format md`; add
   `--exclude-cut` when the recipient should not see inactive branches.

Fan-out is represented by creating multiple steps from the same input
node. Multi-input joins use repeated `--from` flags.

Parallel processes can work in the same run when each writer appends only new
records. Merge is record-level append, not mutation of existing history.

## Setup Mental Model

ARCTX has three separate pieces of state:

- **Run:** the graph under `<ARCTX_HOME>/runs/<run_id>`.
- **Repo pointer:** `<gitdir>/arctx-id`, written by `arctx init`, `arctx use`,
  `arctx git init`, and `arctx git repo add`.
- **Shell pointer:** `ARCTX_RUN_ID`, usually set with
  `eval "$(arctx use <run_id> --shell)"` or `arctx work-session env`.

Resolution order is:

```text
--run <id>
ARCTX_RUN_ID
<gitdir>/arctx-id
```

Use the repo pointer for "this checkout normally belongs to this run". Use the
shell pointer when one terminal should follow a run while moving across repos,
or when a child process should be isolated from other terminals.

## Single Repo With Git

```bash
cd ~/dev/my-repo
arctx init "feature X" --run-id run_x --extension git
arctx git init
arctx git commit -m "first change"
```

`arctx init --extension git` creates the run and enables git integration.
`arctx git init` explicitly registers the repo in that run, writes the repo
marker, and installs hooks. After that, regular `arctx git ...` commands can
resolve the run from the repo pointer.

## One Run Across Multiple Repos

A run sits above git and can span several repos. Register each repo in the
registry and commits from any of them land in the same run's history.

```bash
cd ~/dev/frontend
arctx init "feature X" --run-id run_x --extension git
arctx git init

cd ~/dev/backend
arctx git repo add --run run_x
```

- Commit tip consistency is keyed by `(repo_id, branch)`, so same-named
  branches in different repos, such as two `main` branches, do not collide.
- To follow `run_x` from one terminal while moving between repos, pin the
  terminal instead of relying on each repo's pointer:
  `eval "$(arctx use run_x --shell)"`.
- `arctx export` lists registered repos in a Repos section. `local_path` is
  dropped by default to avoid leaking machine-specific paths; use
  `--include-local` for local diagnostics.

## Work Session Fixed Mode

Parallel agents should not rely only on shared repo pointers. Pin the run and
work session in each process environment instead.

```bash
eval "$(arctx work-session env --run run_x --new --user codex)"
arctx add step --from NODE_ID --type suggestion
```

Use `spawn` for child processes. The child receives a unique
`ARCTX_WORK_SESSION_ID`; sibling terminals and sibling child processes do not
share the fixed session.

```bash
arctx work-session spawn --run run_x --user codex -- codex
arctx work-session spawn --run run_x --user claude-code -- claude
```

For explicit mode, pass both `--run` and `--work-session` on every mutating
command.

```bash
arctx add step --run run_x --work-session ws_xxx --from NODE_ID --type implementation
```

The default attribution is `user=user` and `work_session=default`. Set `--user`
or `ARCTX_USER_ID` for each agent when you need to distinguish who wrote which
records.

This fixed-mode workflow assumes multiple processes on the same machine. Do not
directly share one run directory across machines through NFS or a cloud sync
folder. The public sync CLI is intentionally deferred until the remote/sharing
model is settled.

## Worktree Per Agent

For parallel coding agents, pair work sessions with git worktrees:

```bash
arctx git worktree add ../my-repo-codex codex/run-x --base main
arctx work-session spawn --run run_x --user codex --worktree ../my-repo-codex -- codex
```

The work session records the worktree path and exports
`ARCTX_GIT_WORKTREE=PATH` to the child. Git verbs then run in that worktree
even if the shell cwd is somewhere else.
