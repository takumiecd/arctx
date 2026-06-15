#!/usr/bin/env bash
# Example: Debugging trace with ARCTX
#
# This script demonstrates how ARCTX records every hypothesis while
# chasing a bug, so you can walk the trace backwards once you find
# the root cause.
#
# Run inside a git repository with arctx-cli installed.

set -e

# Clean up any previous run
rm -rf .arctx-id
rm -rf /tmp/arctx-debug-demo

step_id() { python3 -c "import sys, json; print(json.load(sys.stdin)['step_id'])"; }
node_id() { python3 -c "import sys, json; print(json.load(sys.stdin)['output_node_id'])"; }

# 1. Initialize the run
arctx init debug --extension git --run-id bug-42-demo

# 2. Reproduction script
cat > repro.py <<'PY'
def process(items):
    result = []
    for i in range(len(items)):
        result.append(items[i] * 2)
    return result

# Bug: should be i + 1, not i
PY
git add repro.py && arctx git commit -m "reproduction script: demonstrates off-by-one"

# 3. Hypothesis 1: race condition in cache (wrong — still flaky)
git checkout -b try/race-fix
cat > repro.py <<'PY'
import threading
_lock = threading.Lock()

def process(items):
    with _lock:
        result = []
        for i in range(len(items)):
            result.append(items[i] * 2)
        return result
PY
git add repro.py
STEP_1=$(arctx git commit -m "hypothesis: add lock around cache" | step_id)

arctx attach "$STEP_1" \
  --type observation \
  --field result="still flaky — lock didn't help"

# 4. Hypothesis 2: off-by-one in loop bound (correct!)
git checkout main && git checkout -b try/index-fix
cat > repro.py <<'PY'
def process(items):
    result = []
    for i in range(len(items) - 1):  # Bug fix: off-by-one
        result.append(items[i] * 2)
    return result
PY
git add repro.py
FIX=$(arctx git commit -m "fix: correct loop bound")
STEP_FIX=$(echo "$FIX" | step_id)
FIX_NODE=$(echo "$FIX" | node_id)

arctx attach "$STEP_FIX" \
  --type observation \
  --field result="bug gone — 3 consecutive green runs"

# 5. Show the trace

echo ""
echo "=== The debugging trace ==="
arctx dump --format outline --run bug-42-demo --full-payloads

echo ""
echo "=== Walk backwards from the fix ==="
arctx graph trace "$FIX_NODE" --run bug-42-demo
