#!/usr/bin/env bash
# Basic CLI loop example for arctx 0.3.0b1.
#
# Demonstrates the pure DAG core surface:
#   init -> add step -> attach -> show -> graph trace -> dump -> list

set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=packages/arctx/src:packages/arctx-cli/src:packages/arctx-tui/src

RUN_ID="demo_loop"
STORE_DIR="${STORE_DIR:-/tmp/arctx_demo_runs}"

rm -rf "$STORE_DIR/$RUN_ID"

echo "=== 1. init ==="
# init prints the run id; the root node id is read back from `show`.
python3 -m arctx_cli.main init \
  "req_optimize_kernel" \
  --target-type "kernel" \
  --target-id "matmul_v1" \
  --run-id "$RUN_ID" \
  --store-dir "$STORE_DIR"
ROOT_NODE_ID=$(python3 -m arctx_cli.main show \
  --run "$RUN_ID" \
  --store-dir "$STORE_DIR" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['root_node_id'])")
echo "root node: $ROOT_NODE_ID"

echo ""
echo "=== 2. add step ==="
STEP_RESULT=$(python3 -m arctx_cli.main add step \
  --run "$RUN_ID" \
  --from "$ROOT_NODE_ID" \
  --type experiment \
  --field intent="run baseline benchmark" \
  --store-dir "$STORE_DIR")
echo "$STEP_RESULT"
STEP_ID=$(echo "$STEP_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['step_id'])")
OUTPUT_NODE_ID=$(echo "$STEP_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['output_node_id'])")

echo ""
echo "=== 3. attach payload to the output node ==="
python3 -m arctx_cli.main attach "$OUTPUT_NODE_ID" \
  --run "$RUN_ID" \
  --type result \
  --field speedup=1.15 \
  --field status=completed \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 4. step payloads ==="
python3 -m arctx_cli.main show \
  --step "$STEP_ID" \
  --run "$RUN_ID" \
  --with-payloads \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 5. graph trace ==="
python3 -m arctx_cli.main graph trace "$OUTPUT_NODE_ID" \
  --run "$RUN_ID" \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 6. dump ==="
python3 -m arctx_cli.main dump \
  --run "$RUN_ID" \
  --format outline \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 7. list ==="
python3 -m arctx_cli.main list \
  --store-dir "$STORE_DIR"

echo ""
echo "Done. Run directory: $STORE_DIR/$RUN_ID"
