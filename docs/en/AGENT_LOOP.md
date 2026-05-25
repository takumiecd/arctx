# Agent Loop

Recommended loop:

1. Read context with `stag dump`.
2. Append intent with `stag plan`.
3. Optionally append predictions with `stag predict`.
4. Do external work.
5. Append observed result with `stag observe`.
6. Cut wrong branches with `stag cut` instead of deleting records.

Agents can work in parallel when each writer appends a batch containing only new
records. Merge is record-level append, not mutation of existing history.
