# Git Integration

Git integration records commit and diff metadata as `GitChangePayload` on a
Transition.

```bash
stag git start <transition_id>
stag git finish <session_id> --status completed
stag git diff --transition <transition_id>
stag git log --transition <transition_id>
```

`git finish` can create a ResultPayload and attach GitChangePayload to the same
Transition. Patch artifacts are stored under the run directory.
