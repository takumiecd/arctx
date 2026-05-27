#!/usr/bin/env bash
# Basic CLI loop example for arctx 0.1 alpha.
#
# Demonstrates:
#   init -> transition create -> payload add -> graph trace -> cut -> graph dump -> list

set -euo pipefail

export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=packages/arctx/src:packages/arctx-cli/src:packages/arctx-tui/src

RUN_ID="demo_loop"
STORE_DIR="${STORE_DIR:-/tmp/arctx_demo_runs}"

rm -rf "$STORE_DIR/$RUN_ID"

echo "=== 1. init ==="
INIT_RESULT=$(python3 -m arctx_cli.main init \
  "req_optimize_kernel" \
  --target-type "kernel" \
  --target-id "matmul_v1" \
  --run-id "$RUN_ID" \
  --store-dir "$STORE_DIR")
echo "$INIT_RESULT"
ROOT_NODE_ID=$(echo "$INIT_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['root_node_id'])")

echo ""
echo "=== 2. transition create ==="
TRANSITION_RESULT=$(python3 -m arctx_cli.main transition create \
  --from "$ROOT_NODE_ID" \
  --payload-type transition_payload \
  --field type=experiment \
  --field intent="run baseline benchmark" \
  --store-dir "$STORE_DIR")
echo "$TRANSITION_RESULT"
TRANSITION_ID=$(echo "$TRANSITION_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['transition_id'])")
OUTPUT_NODE_ID=$(echo "$TRANSITION_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['output_node_id'])")

echo ""
echo "=== 3. payload add ==="
python3 -m arctx_cli.main payload add \
  --node "$OUTPUT_NODE_ID" \
  --payload-type node_payload \
  --field type=result \
  --field speedup=1.15 \
  --field status=completed \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 4. transition payloads ==="
python3 -m arctx_cli.main transition payloads "$TRANSITION_ID" \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 5. graph trace ==="
python3 -m arctx_cli.main graph trace "$OUTPUT_NODE_ID" \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 6. graph dump ==="
python3 -m arctx_cli.main graph dump \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 7. list ==="
python3 -m arctx_cli.main list \
  --store-dir "$STORE_DIR"

echo ""
echo "Done. Run directory: $STORE_DIR/$RUN_ID"
