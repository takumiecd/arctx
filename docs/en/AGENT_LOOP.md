# Agent Loop

## Recommended Loop

1. Read context with `arctx log`.
2. Append intent with `arctx add --from NODE_ID --type suggestion --field proposal="..."`.
3. Do external work: implementation, experiment, review, debugging, or research.
4. Append the result with `arctx add --from NODE_ID --type implementation --field result="..."`.
5. Cut wrong branches with `arctx cut NODE_ID` instead of deleting records.
6. At checkpoints, produce an artifact with `arctx export --format md`; add
   `--exclude-cut` when the recipient should not see inactive branches.

Fan-out is represented by creating multiple steps from the same input
node. Multi-input joins use repeated `--from` flags.

Parallel processes can work in the same run when each writer appends only new
records. Merge is record-level append, not mutation of existing history.

## Parallel Experiment Strategy

When approaches are independent, fan them out from the same baseline node
instead of serializing them in one lane. Give each approach its own lane, and
for code changes prefer a separate git worktree as well. This is different from
ordinary git branching: ARCTX records the experiment relationship in the
RunGraph, not just code refs.

Record each branch's hypothesis, result, and evaluation signal. Do not discard a
branch only because it is weak by itself; sometimes the best answer is a later
multi-input join of ideas that were mediocre in isolation. After independent
runs finish, combine promising terminal nodes with repeated `--from` arguments
and record the synthesis as one step.

Use `cut` for branches that should remain in history but no longer participate
in the active solution. Use `arctx lane close --summary "..."` to preserve the
final finding for each lane.

## Setup Mental Model

ARCTX has three separate pieces of state:

- **Run:** the graph under `<repo_root>/.arctx/runs/<run_id>` (or
  `<ARCTX_HOME>/runs/<run_id>` when `ARCTX_HOME` is set / outside a repo).
- **Repo pointer:** `<gitdir>/arctx-id`, written by `arctx init`, `arctx use`,
  and `arctx git init`.
- **Shell pointer:** `ARCTX_RUN_ID`, set with
  `eval "$(arctx use <run_id> --shell)"` (this terminal only; it does not write
  the repo pointer).

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
`arctx git init` binds this checkout to that run (repo pointer) and installs
hooks. After that, regular `arctx git ...` commands can resolve the run from
the repo pointer.

## One Run, One Repo

A run lives inside exactly one repository: its data sits in that repo's
`.arctx/`, and every git record refers to that repo implicitly ("absent =
self"). There is no repo registry and no `repo_id`.

- To follow `run_x` from one terminal while moving between checkouts, pin the
  terminal instead of relying on each repo's pointer:
  `eval "$(arctx use run_x --shell)"`.

## Per-terminal Fixed Mode

Parallel agents should not rely only on shared repo pointers. Pin the run and
lane in each process environment instead.

```bash
eval "$(arctx use run_x --shell)"            # export ARCTX_RUN_ID=run_x
arctx lane create codex --purpose "..." --user codex
eval "$(arctx lane switch codex --shell)"    # export ARCTX_LANE_ID=lane_...
export ARCTX_USER_ID=codex

arctx add --from NODE_ID --type suggestion
```

`--shell` writes no pointer, so sibling terminals sharing one checkout hold
different lanes. To hand a child process its own lane, pass the variables when
launching it:

```bash
ARCTX_LANE_ID=$(arctx lane show codex --json | jq -r .lane.lane_id) \
ARCTX_USER_ID=codex codex
```

`arctx add` (frontier resolution when `--from` is omitted) and `arctx guide`
resolve `ARCTX_LANE_ID` ahead of the repo pointer, so a child process sees its
own lane.

For explicit mode, pass both `--run` and `--lane` on every mutating
command.

```bash
arctx add --run run_x --lane ws_xxx --from NODE_ID --type implementation
```

The default attribution is `user=user` and `lane=default`. Set `--user`
or `ARCTX_USER_ID` for each agent when you need to distinguish who wrote which
records.

This fixed-mode workflow assumes multiple processes on the same machine. Do not
directly share one run directory across machines through NFS or a cloud sync
folder. The public sync CLI is intentionally deferred until the remote/sharing
model is settled.

## Worktree Per Agent

For parallel coding agents, pair lanes with git worktrees:

```bash
arctx git worktree add ../my-repo-codex codex/run-x --base main
export ARCTX_GIT_WORKTREE=../my-repo-codex
```

When `ARCTX_GIT_WORKTREE` is set, git verbs run in that worktree even if the
shell cwd is somewhere else.
