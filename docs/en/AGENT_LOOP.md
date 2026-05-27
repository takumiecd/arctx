# Agent Loop

Recommended loop:

1. Read context with `arctx graph dump`.
2. Append intent with `arctx transition create --from NODE_ID --payload-type transition_payload --field type=suggestion --field proposal="..."`.
3. Do external work.
4. Append the result with `arctx transition create --from NODE_ID --payload-type transition_payload --field type=implementation --field result="..."`.
5. Cut wrong branches with `arctx cut node NODE_ID` instead of deleting records.

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
