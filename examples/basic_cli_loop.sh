#!/usr/bin/env bash
# Basic CLI loop example for optagent.
#
# This script demonstrates a full cycle of the optagent CLI:
#   init → plan → predict → observe → show → trace → refresh → list
#
# Usage:
#   chmod +x examples/basic_cli_loop.sh
#   ./examples/basic_cli_loop.sh

set -euo pipefail

# Use the source tree directly
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH=src

RUN_ID="demo_loop"
STORE_DIR=".optagent/runs"

echo "=== 1. init ==="
python3 -m optagent.cli.main init \
  "req_optimize_kernel" \
  --target-type "code" \
  --target-id "matmul_v1" \
  --run-id "$RUN_ID" \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 2. plan ==="
PLAN_RESULT=$(python3 -m optagent.cli.main plan \
  "$RUN_ID" \
  --planner default \
  --max-plans 1 \
  --store-dir "$STORE_DIR")
echo "$PLAN_RESULT"
PLAN_ID=$(echo "$PLAN_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)[0]['plan_id'])")

echo ""
echo "=== 3. predict ==="
PRED_RESULT=$(python3 -m optagent.cli.main predict \
  "$RUN_ID" \
  "$PLAN_ID" \
  --max-outcomes 1 \
  --store-dir "$STORE_DIR")
echo "$PRED_RESULT"
PRED_ID=$(echo "$PRED_RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)[0]['transition_id'])")

echo ""
echo "=== 4. observe ==="
python3 -m optagent.cli.main observe \
  "$RUN_ID" \
  "$PLAN_ID" \
  --result-id "r_0001" \
  --status completed \
  --artifact "build.log" \
  --raw-output "benchmark.txt" \
  --log "stderr.log" \
  --metric "speedup=1.15" \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 5. show (run summary) ==="
python3 -m optagent.cli.main show \
  "$RUN_ID" \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 6. trace ==="
python3 -m optagent.cli.main trace \
  "$RUN_ID" \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 7. refresh ==="
python3 -m optagent.cli.main refresh \
  "$RUN_ID" \
  --store-dir "$STORE_DIR"

echo ""
echo "=== 8. list ==="
python3 -m optagent.cli.main list \
  --store-dir "$STORE_DIR"

echo ""
echo "Done. Run directory: $STORE_DIR/$RUN_ID"
