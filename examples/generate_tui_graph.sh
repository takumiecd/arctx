#!/usr/bin/env bash
# Generates a complex STAG graph for the TUI demo video.

set -euo pipefail
export PYTHONPATH=src

RUN_ID="demo_tui"
STORE_DIR="${STORE_DIR:-runs}"

echo "Cleaning up old run..."
rm -rf "$STORE_DIR/$RUN_ID"

echo "Building a complex graph for the TUI..."

# 1. Init
stag init req_tui_demo --extension git --run-id "$RUN_ID" > /dev/null

# 2. Baseline
stag git commit --run "$RUN_ID" -m "Baseline: Simple loop" > /dev/null

# 3. Branch A (Fails)
eval "$(stag work-session env --run $RUN_ID --name exp_a --new)"
stag git commit --run "$RUN_ID" -m "Exp A: Multithreading" > /dev/null
stag git commit --run "$RUN_ID" -m "Exp A: Add mutex locks" > /dev/null
stag git revert --run "$RUN_ID" -m "Revert Exp A (Deadlock encountered)" > /dev/null

# 4. Branch B (Fails)
eval "$(stag work-session env --run $RUN_ID --name exp_b --new)"
stag git commit --run "$RUN_ID" -m "Exp B: Rewrite in Rust" > /dev/null
stag git revert --run "$RUN_ID" -m "Revert Exp B (Too complex)" > /dev/null

# 5. Branch C (Succeeds)
eval "$(stag work-session env --run $RUN_ID --name exp_c --new)"
stag git commit --run "$RUN_ID" -m "Exp C: Vectorization" > /dev/null
stag git commit --run "$RUN_ID" -m "Exp C: Optimize cache hits" > /dev/null
stag git commit --run "$RUN_ID" -m "Exp C: Final Polish (10x speedup!)" > /dev/null

echo "Graph generation complete! Run 'stag tui --run demo_tui' to view it."
