#!/usr/bin/env bash
# Generates a complex ARCTX graph for the TUI demo video.
# Assumes the caller has already sourced examples/demo_env.sh,
# so $PWD is a fresh scratch git repo (with PATH/ARCTX_HOME set).

set -euo pipefail

RUN_ID="demo_tui"

echo "Building a complex graph for the TUI..."

write_change() {
  local file="$1" line="$2"
  echo "$line" >> "$file"
  git add "$file"
}

# 1. Init
arctx init req_tui_demo --extension git --run-id "$RUN_ID" > /dev/null

# 2. Baseline
write_change optimize.py "# baseline: simple loop"
arctx git commit --run "$RUN_ID" -m "Baseline: Simple loop" > /dev/null

# 3. Branch A (Fails)
git checkout -q -b exp/multithreading
eval "$(arctx work-session env --run $RUN_ID --new --user exp_a)"
write_change optimize.py "# attempt: threading"
arctx git commit --run "$RUN_ID" -m "Exp A: Multithreading" > /dev/null
write_change optimize.py "# attempt: mutex locks"
arctx git commit --run "$RUN_ID" -m "Exp A: Add mutex locks" > /dev/null
arctx git revert --run "$RUN_ID" --sha "$(git rev-parse HEAD)" -m "Revert Exp A (Deadlock encountered)" > /dev/null

# 4. Branch B (Fails)
git checkout -q main
git checkout -q -b exp/rust
eval "$(arctx work-session env --run $RUN_ID --new --user exp_b)"
write_change optimize.py "# attempt: rewrite in rust"
arctx git commit --run "$RUN_ID" -m "Exp B: Rewrite in Rust" > /dev/null
arctx git revert --run "$RUN_ID" --sha "$(git rev-parse HEAD)" -m "Revert Exp B (Too complex)" > /dev/null

# 5. Branch C (Succeeds)
git checkout -q main
git checkout -q -b exp/vectorization
eval "$(arctx work-session env --run $RUN_ID --new --user exp_c)"
write_change optimize.py "# attempt: vectorization"
arctx git commit --run "$RUN_ID" -m "Exp C: Vectorization" > /dev/null
write_change optimize.py "# attempt: cache hits"
arctx git commit --run "$RUN_ID" -m "Exp C: Optimize cache hits" > /dev/null
write_change optimize.py "# attempt: final polish"
arctx git commit --run "$RUN_ID" -m "Exp C: Final Polish (10x speedup!)" > /dev/null

echo "Graph generation complete! Run 'arctx-tui --run demo_tui' to view it."
