# Direction

The canonical graph model is now:

```text
Node -> Step -> Node -> Step -> Node
```

There are no specialized step record types. Payloads attach meaning to a
plain `Step`.

Core is standalone and does not depend on git. Git integration is the standard
extension under `arctx.ext.git`; its canonical CLI is `arctx git <verb>`, with
a default alias, `arctx verify`.

Future UI work should render the DAG visually and show payload details only for
the focused node or step.

## Git worktree-aware workflows

The Git extension does not run git, so there is nothing to point at a
worktree (`ARCTX_GIT_WORKTREE` and `arctx git worktree` are gone). To give each
agent an isolated checkout: create the tree with `git worktree add`, commit
inside it, and run `arctx add --commit HEAD` there. One ARCTX run is shared;
the worktree lifecycle stays entirely in git.
