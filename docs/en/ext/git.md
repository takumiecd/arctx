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
# Add a repository path to this run
arctx git repo add <slug> <local_path>

# List all registered repositories
arctx git repo list

# Show details of a repository
arctx git repo show <repo_id>
```

### 4. Record Branching and Merging
Records branch creations, merges, reverts, and cherry-picks:

```bash
# Record a branch tip
arctx git branch <branch_name>

# Record a merge merge between branches
arctx git merge --from <from_branch> --into <into_branch>

# Record a revert commit
arctx git revert <commit_sha>
```

---

## Python API

Invoke Git actions via the `handle.git` namespace:

```python
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

# Attach a git commit to the graph
handle.git.commit(
    message="Implement new feature",
    repo_id="repo_1",
    branch="main",
)
```
