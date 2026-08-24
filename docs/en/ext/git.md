# Git Integration Extension (`git`)

The `git` extension links **commits you made** to the ARCTX RunGraph and
derives their diffs from git at read time.

**arctx does not run git, and does not watch git.** The verbs that did —
`arctx git commit` / `revert` / `merge` / `cherry-pick` / `reset` / `branch` /
`init` / `hook` / `worktree` — were all removed, for two reasons:

- arctx's own git subprocesses tripped arctx's own hooks, so the same
  operation was recorded twice: an active phantom Step anchored at the run
  root, two Steps claiming the same `head_commit`, and a `session_hook` lane
  nobody created.
- hook-driven adoption re-guessed a graph position `arctx add` already
  tracks. Two mechanisms, so they drifted.

Recording is explicit: **you make the commit, then you record its sha.**

---

## What it gives you

1. **Commit references**: only the commit hashes and a branch name are stored
   on the Step, as a `GitChangePayload`.
2. **One run, one repo**: a run lives inside the repository carrying its data,
   and a git record with no repo qualifier means that repo ("absent = self").
3. **Diffs are derived, never copied**: diff stats, commit subjects, file
   lists, and patch text are read **from git at display time** using the
   recorded shas (`arctx.ext.git.derive`). A commit missing from the clone
   comes back with `available=false` and `(commit not available locally)`
   rather than raising.
4. **Diff preview in the GUI**, syntax-highlighted.

---

## CLI

### 1. Create the run and bind the checkout

```bash
arctx init <req_id> --extension git
```

Inside a repo this also writes `<gitdir>/arctx-id` (the run pointer).
**No hooks are installed.**

### 2. Record a commit

```bash
git commit -m "summary of the change"
arctx add --title "summary of the change" --type commit --commit HEAD
```

One command records both the Step and the commit it stands for. Exactly one
mechanism tracks lane position — `arctx add`'s. Pass `--from NODE` (repeatable
for fan-in) to branch off a chosen node instead of the lane frontier.

To add a commit to a Step that already exists:

```bash
arctx git add --step <STEP_ID> --commit <SHA>
```

### 3. Read it back

```bash
# the commits recorded on a step, plus the diff git reports for them now
arctx git show --step <STEP_ID>

# just the hashes
arctx git list --step <STEP_ID>

# descendant constraint over all steps
arctx git verify
```

There are **no commands for recording branches, merges, reverts, or
cherry-picks**. Do the operation in git, then record the resulting commit with
`arctx add --commit`. When histories converge, repeat `--from` to make a
multi-input Step.

---

## Python API

The `handle.git` namespace is read-only.

```python
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

handle.git.verify()                 # descendant constraint
handle.git.current_sha(step_id)     # latest head_commit on that step
handle.git.step_by_sha(sha)         # find the step carrying a sha
```

To record a commit, use `arctx.ext.git.helpers.attach.attach_commits_to_step`
— the same call `arctx add --commit` and `arctx git add` make.
