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
arctx lane create geometry # create lane "geometry"; does not switch
arctx lane switch geometry # switch to an existing lane; typo is an error
arctx lane geometry        # shorthand for switch; missing names are not created
                           # switch records <gitdir>/arctx-lane → persists across shells. No eval.
arctx lane                 # show the current lane
arctx lane list            # list lanes
arctx lane adopt geometry --history <tip> # adopt existing history into a lane without rewriting creation provenance
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

## 5. Sync = union (arctx-native)

```bash
arctx remote add origin <dir>   # register a remote (v1: a file-backed shared log)
arctx push                      # send records the remote lacks (id diff, idempotent)
arctx pull                      # union the remote's records in
```

Merging across people/machines is an **ID-aware union** (append-only, idempotent,
commutative, convergent). Modeled on git's UX but arctx-native — **git is not
reused**. Being a CRDT means **no conflicts, no history rewrite, no hand
reconciliation**; a rejection just stays as a cut. After `pull` brings records
in, the target owner runs `accept`/`reject` (a PR is the decision layer, not
transport).

---

### PR flow (gate-type, arctx-native)

A PR is an append-only review STATE in the DAG. Proposing is not a transport
(push) — it attaches a `proposal`. The target tip does NOT advance until accept
(that is what "pending" means).

| Step | Command |
|---|---|
| open a workspace | `arctx lane <name>` |
| propose (open a pending PR) | `arctx propose <source> --into <target>` |
| see pending proposals | `arctx propose --list` |
| review | `arctx log` / `arctx dump` |
| accept (guarded merge) | `arctx accept <source>` (refused → rebase & re-propose) |
| reject (kept) | `arctx reject <source> --reason ...` (= cut) |
| sync | `arctx push` / `arctx pull` (`arctx remote add` first; union converges) |

`accept` runs a multi-input `add step` (join); if the base was cut, it would
cycle, or the target advanced, it is **refused** (never silent corruption).
`reject` is a `cut`. Consistency is checked **at accept time against the target**
— the only correct place once replicas are split (remote/local).
