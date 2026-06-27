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
  arctx git commit -m "baseline: empty project"

--- Step 2: Start Claude's session (Terminal 1) ---

  eval $(arctx lane env --run multi-agent-demo --new --user claude)
  git checkout -b claude/vec

  # ... make some edits ...

  git add . && arctx git commit -m "Claude: vectorize inner loop"

--- Step 3: Start Codex's session (Terminal 2) ---

  eval $(arctx lane env --run multi-agent-demo --new --user codex)
  git checkout main && git checkout -b codex/map

  # ... make some edits ...

  git add . && arctx git commit -m "Codex: parallel map"

--- Step 4: Inspect the graph (either terminal) ---

  arctx dump --format outline --run multi-agent-demo

You will see both attempts as sibling steps branching from
baseline. No merge conflicts in the graph — both stay reviewable.

--- Optional: Use separate worktrees for physical isolation ---

If you want each agent to have its own checkout directory:

  # Terminal 1
  arctx git worktree add ../wt-claude claude/vec
  eval $(arctx lane env --run multi-agent-demo --new --user claude --worktree ../wt-claude)

  # Terminal 2
  arctx git worktree add ../wt-codex codex/map
  eval $(arctx lane env --run multi-agent-demo --new --user codex --worktree ../wt-codex)

INSTRUCTIONS
