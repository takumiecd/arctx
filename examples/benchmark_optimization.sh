#!/usr/bin/env bash
# Example: Benchmark-driven optimization with ARCTX
#
# This script demonstrates how ARCTX records the reasoning history
# behind a performance optimization: try variant A, measure, cut it,
# try variant B, measure — the whole story stays in the graph.
#
# Run inside a git repository with arctx-cli installed.

set -e

# Clean up any previous run
rm -rf .arctx-id
rm -rf /tmp/arctx-bench-demo

step_id() { python3 -c "import sys, json; print(json.load(sys.stdin)['step_id'])"; }
node_id() { python3 -c "import sys, json; print(json.load(sys.stdin)['output_node_id'])"; }

# 1. Initialize the run
arctx init optimize --extension git --run-id bench-demo

# 2. Baseline — a naive implementation
cat > work.py <<'PY'
def sum_list(data):
    total = 0
    for x in data:
        total += x
    return total
PY
# Capture the baseline node so both hypotheses fan out from the SAME baseline,
# even after one of them is cut.
git add work.py
BASE=$(arctx git commit -m "baseline: naive loop" | node_id)

# 3. Hypothesis A — add a cache layer (spoiler: it gets slower)
git checkout -b feat/cache
cat > work.py <<'PY'
_cache = {}

def sum_list(data):
    key = id(data)
    if key in _cache:
        return _cache[key]
    total = 0
    for x in data:
        total += x
    _cache[key] = total
    return total
PY
git add work.py
STEP_A=$(arctx git commit -m "hypothesis A: add cache layer" --from "$BASE" | step_id)

# Attach benchmark result to the step — slower than baseline
arctx attach "$STEP_A" \
  --type benchmark \
  --field elapsed_ms=1200 \
  --field note="slower than baseline — cache overhead dominates"

# 4. Cut hypothesis A — it stays in the graph, just marked inactive
arctx cut step "$STEP_A" --reason "slower than baseline"

# 5. Hypothesis B — vectorize with built-in sum (faster!)
git checkout main && git checkout -b feat/vectorize
cat > work.py <<'PY'
def sum_list(data):
    return sum(data)
PY
git add work.py
STEP_B=$(arctx git commit -m "hypothesis B: use built-in sum" --from "$BASE" | step_id)

# Attach benchmark result to the step — much faster
arctx attach "$STEP_B" \
  --type benchmark \
  --field elapsed_ms=180 \
  --field note="5x faster than baseline"

# 6. Show the story

echo ""
echo "=== The graph tells the whole story ==="
arctx dump --format outline --run bench-demo --full-payloads

echo ""
echo "=== Or as Mermaid ==="
arctx dump --format mermaid --run bench-demo
