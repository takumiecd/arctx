# Direction

The canonical graph model is now:

```text
Node -> Step -> Node -> Step -> Node
```

There are no specialized step record types. Payloads attach meaning to a
plain `Step`.

Core is standalone and does not depend on git. Git integration is the standard
extension under `arctx.ext.git`; its canonical CLI is `arctx git <verb>`, with
default aliases such as `arctx commit` for common workflows.

Future UI work should render the DAG visually and show payload details only for
the focused node or step.

## Git worktree-aware workflows

The Git extension is worktree-aware. A `WorkSession` can be attached to
a specific `git worktree`, and ARCTX commands inside that session run
their git subprocesses inside the linked working tree:

- `ARCTX_GIT_WORKTREE` overrides the cwd for every git verb
  (`arctx git commit / revert / cherry-pick / merge / reset / verify`).
- `arctx work-session start / env / spawn --worktree PATH` records the
  resolved path (plus current branch and `git --git-common-dir`) on
  `WorkSession.metadata["worktree"]` and exports `ARCTX_GIT_WORKTREE`
  for downstream processes.
- `arctx git worktree {add,list,remove}` is a thin wrapper around the
  upstream `git worktree` plumbing. Lifecycle stays in git so that
  worktrees created outside ARCTX can still be attached.

Possible follow-ups:

- Surface the worktree path in `arctx work-session list` / TUI views.
- Record a per-step workspace path when an agent moves between
  worktrees during a single session.
- Auto-create a worktree when `work-session env --new --worktree PATH`
  points at a missing directory.
