# ARCTX core commands (basically all you need)

Day to day, these **five verbs** are enough. Everything else (`log`/`dump`/`show`/
`list`/`export`/`use`/`serve`/`git` …) is viewing, plumbing, or extensions — not core.

| Verb | Role | In a word |
|------|------|-----------|
| `init` | create a run (once) | the start |
| `lane` | the work **context** (a solo/shared line of work) | which lane you work in |
| `add`  | create nodes/steps = grow the **topology** | grow the graph |
| `attach` | add a payload to an existing node/step = **annotate** | pin results / intent |
| `cut`  | deactivate (with a reason) = **reject/retract** | keep it, don't delete |

Mental model: **`init` to start, `lane` to pick the context, `add` (topology) +
`attach` (annotation) to grow, `cut` to retract.** Failures and history stay in the DAG.

## 1. Start

```bash
arctx init my_task --run-id scd-dev      # create a run (recorded in <gitdir>/arctx-id)
```

## 2. Lane (the work context) — `source .venv` / `git switch` style

```bash
arctx lane geometry        # switch to (create) lane "geometry"; recorded in
                           # <gitdir>/arctx-lane → persists across shells. No eval.
arctx lane                 # show the current lane
arctx lane --list          # list lanes
```

A lane is **not** owned by one user: others may join the same lane (attribution is
per-action, per actor). Only when running **parallel** explorations across terminals
do you pin it shell-locally:

```bash
eval "$(arctx lane geometry --shell)"    # pin via env for THIS terminal (env beats the file)
```

→ No eval for normal use (the file pointer is the default). The eval is **parallel-only**.

## 3. Grow the graph

```bash
arctx add step --from <node> --title "explore ProductGeometry"   # grow topology
arctx add step --from <A> --from <B> --title "merge A and B"      # multi-input = join/merge
arctx attach <node> --type result --json '{"recall@k":"rough at scale"}'  # annotate
```

## 4. Reject (and keep)

```bash
arctx cut --node <tip> --reason "grow-score not smooth at scale"  # deactivate, keep, with reason
```

Accept (merge) = simply don't cut. To continue, stack more `add` on the tip.

## 5. Sync = union

Merging across people/machines is an **ID-aware union** (append-only, idempotent):
commutative, idempotent, convergent. Transport is git (push/pull). **No hand
reconciliation** — a rejection just stays as a cut.

---

### PR flow (no new command needed)

| Step | Command |
|---|---|
| open a workspace | `arctx lane <name>` |
| propose (PR) | `git push` (store tracked in the repo) |
| review | `arctx log` / `arctx dump` |
| accept | do nothing (stays active) |
| reject | `arctx cut --reason ...` |
| combine results | `arctx add step --from A --from B` |
| sync | `git pull` / `push` (union converges) |
