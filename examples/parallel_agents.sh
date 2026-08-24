#!/usr/bin/env bash
# Example: Multi-agent parallel work with ARCTX
#
# This script sets up a demonstration of two agents (Claude and Codex)
# working against the same ARCTX run without stepping on each other.
#
# Because this requires two concurrent terminals, this script only
# prints the commands you would run in each terminal.
#
# Prerequisites:
#   - arctx-cli installed
#   - Inside a git repository
#   - Two terminal windows/tabs

set -e

cat <<'INSTRUCTIONS'

=== Multi-Agent Parallel Work Demo ===

This demo shows how Claude and Codex can drive the same ARCTX run
in parallel. Each agent gets its own lane; both attempts
land as sibling steps in the same RunGraph.

Prerequisites:
  1. arctx-cli installed:   pip install arctx-cli
  2. Inside a git repository with at least one commit
  3. Two terminal windows/tabs

--- Step 1: Initialize the run (Terminal 1) ---

  arctx init optimize --extension git --run-id multi-agent-demo
  git commit -qm "baseline: empty project"
  arctx add --title "baseline: empty project" --type commit --commit HEAD

--- Step 2: Start Claude's session (Terminal 1) ---

  arctx lane create claude --purpose "claude work" --run multi-agent-demo
  eval "$(arctx lane switch claude --shell)"
  export ARCTX_USER_ID=claude
  git checkout -b claude/vec

  # ... make some edits ...

  git add . && git commit -qm "Claude: vectorize inner loop"
  arctx add --title "Claude: vectorize inner loop" --type commit --commit HEAD

--- Step 3: Start Codex's session (Terminal 2) ---

  arctx lane create codex --purpose "codex work" --run multi-agent-demo
  eval "$(arctx lane switch codex --shell)"
  export ARCTX_USER_ID=codex
  git checkout main && git checkout -b codex/map

  # ... make some edits ...

  git add . && git commit -qm "Codex: parallel map"
  arctx add --title "Codex: parallel map" --type commit --commit HEAD

--- Step 4: Inspect the graph (either terminal) ---

  arctx dump --format outline --run multi-agent-demo

You will see both attempts as sibling steps branching from
baseline. No merge conflicts in the graph — both stay reviewable.

--- Optional: Use separate worktrees for physical isolation ---

If you want each agent to have its own checkout directory:

  # Terminal 1
  git worktree add ../wt-claude -b claude/vec
  arctx lane create claude --purpose "claude work" --run multi-agent-demo
  eval "$(arctx lane switch claude --shell)"
  export ARCTX_USER_ID=claude
  cd ../wt-claude

  # Terminal 2
  git worktree add ../wt-codex -b codex/map
  arctx lane create codex --purpose "codex work" --run multi-agent-demo
  eval "$(arctx lane switch codex --shell)"
  export ARCTX_USER_ID=codex
  cd ../wt-codex

INSTRUCTIONS
