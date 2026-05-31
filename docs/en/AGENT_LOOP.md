# Agent Loop

Recommended loop:

1. Read context with `arctx graph dump`.
2. Append intent with `arctx transition create --from NODE_ID --payload-type transition_payload --field type=suggestion --field proposal="..."`.
3. Do external work.
4. Append the result with `arctx transition create --from NODE_ID --payload-type transition_payload --field type=implementation --field result="..."`.
5. Cut wrong branches with `arctx cut node NODE_ID` instead of deleting records.
6. At checkpoints, produce an artifact with `arctx export --format md` (add
   `--exclude-cut` to drop dead branches).

Fan-out is represented by creating multiple transitions from the same input node.
Multi-input joins use repeated `--from` flags.

Parallel processes can work in the same run when each writer appends a batch
containing only new records. Merge is record-level append, not mutation of
existing history.

## Work Session Fixed Mode

Parallel processes should not rely on shared `current.json` state. Pin the run
and work session in each process environment instead.

```bash
eval "$(arctx work-session env --run run_xxx --new)"
arctx transition create --from NODE_ID --payload-type transition_payload --field type=suggestion
```

Use `spawn` for child processes. The child receives a unique
`ARCTX_WORK_SESSION_ID`; sibling terminals and sibling child processes do not
share the fixed session.

```bash
arctx work-session spawn --run run_xxx -- codex
arctx work-session spawn --run run_xxx -- claude
```

For explicit mode, pass both `--run` and `--work-session` on every mutating
command.

```bash
arctx transition create --run run_xxx --work-session ws_xxx --from NODE_ID
```

## One run across multiple repos

A run sits above git and can span several repos. Register each repo in the
registry and commits from any of them land in the same run's history.

```bash
cd ~/dev/frontend && arctx init "feature X" --run-id run_x --extension git
arctx git init                              # register frontend
cd ~/dev/backend  && arctx git repo add --run run_x   # join the same run
```

- Commit tip consistency is keyed by `(repo_id, branch)`, so same-named
  branches in different repos (e.g. two `main`s) never collide.
- To follow run_x from one terminal while moving between repos, pin the
  terminal instead of relying on each repo's `.arctx-id`:
  `eval "$(arctx use run_x --shell)"` (env takes priority).
- `arctx export` lists the registry in a Repos section; `local_path` is dropped
  by default (to avoid leaking it on share) and kept with `--include-local`.
