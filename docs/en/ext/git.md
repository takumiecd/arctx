# Git Integration Extension (`git`)

The `git` extension allows you to track Git activities (commits, branches, merges, etc.) during your development process and attach their metadata and diff summaries directly to Nodes and Steps in the ARCTX RunGraph.

---

## Core Features

1. **Commit and Diff Tracking**:
   Links commit hashes, commit messages, and diff statistics to Steps as payloads.
2. **Multi-Repository Management**:
   Registers multiple local Git repositories to a single run (`repo add`) to track parallel histories.
3. **Git Hooks Integration**:
   Installs hooks like `post-commit` and `post-rewrite` to automatically capture Git actions as you work.
4. **GUI Diff Preview**:
   Provides syntax-highlighted side-by-side or inline diff previews in the Web GUI detail panel.

---

## CLI Usage

### 1. Initialize Git Repo and Hooks
Registers the current working directory's Git repository to the active run and installs hooks:

```bash
arctx git init
```

### 2. Record Commit Details (`arctx git commit` / `arctx commit`)
Captures current working tree changes or a commit's metadata to record a new Step / Payload:

```bash
# Record commit (alias `arctx commit` works too)
arctx commit -m "Summary of changes"
```

### 3. Manage Repositories
Manages the list of repositories registered to this run:

```bash
# Add a repository to this run (defaults to cwd; use --repo-path to specify)
arctx git repo add --repo-path <local_path> --slug <USER/REPO>

# List all registered repositories
arctx git repo list

# Show details of a repository (defaults to resolving cwd; use --repo-id)
arctx git repo show --repo-id <repo_id>
```

### 4. Record Merging and Reverting
Records merges, reverts, and cherry-picks. Recorded branch tips can be inspected with `branch list` / `branch show`:

```bash
# List recorded branches
arctx git branch list

# Show a branch's tip and members
arctx git branch show <branch_name>

# Merge another branch (or node) into the current branch and record it
arctx git merge --other <branch_or_ref>

# Record a revert (--sha to name the commit, or --step to resolve from a Step)
arctx git revert --sha <commit_sha>
```

---

## Python API

Invoke Git actions via the `handle.git` namespace:

```python
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

# Commit the current working tree via git and record the matching Step.
# The repo is resolved from repo_path (defaults to the cwd worktree).
handle.git.commit(
    message="Implement new feature",
    branch="main",          # optional (inferred from git if omitted)
    # repo_path=Path("/path/to/repo"),  # optional (defaults to cwd)
)
```
