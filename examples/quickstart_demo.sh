#!/usr/bin/env bash
# ARCTX 30-second "wow" demo — one command, one shareable graph.
#
# Story: two agents attack the same task from the same starting point.
#   - Claude tries a memoization cache.  It's slower + buggy on mutation.
#   - Codex tries the builtin sum().      It's 5x faster.
#
# Git would only show you the surviving file on whatever branch you keep.
# ARCTX keeps BOTH attempts — as sibling steps in one graph — *and why*
# the cache was abandoned (a benchmark payload + a cut with a reason). Then it
# exports a shareable HTML document you can drop into a PR or a blog post.
#
#   ./examples/quickstart_demo.sh
#
# Everything happens in a throwaway temp dir + temp ARCTX home, so this never
# touches your real repos or your real run store. The exported HTML path is
# printed at the end.
#
# Works with an installed `arctx` command, or — when run from inside this
# repository without installing — the local source via PYTHONPATH.

set -euo pipefail

# --- Resolve how to invoke arctx -------------------------------------------
# Prefer the working-tree source when this script lives inside the repo, so the
# demo always exercises the code you're hacking on (not a stale global install).
# When copied out of the repo, fall back to whatever `arctx` is on PATH.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -d "$REPO_ROOT/packages/arctx/src" ]; then
  export PYTHONPATH="$REPO_ROOT/packages/arctx/src:$REPO_ROOT/packages/arctx-cli/src${PYTHONPATH:+:$PYTHONPATH}"
  # arctx needs >= 3.10, and `python3` is still 3.9 on stock macOS — running the
  # source under it fails at import with a bare SyntaxError. Pick a real one.
  PY_BIN=""
  for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" >/dev/null 2>&1 &&
       "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      PY_BIN="$candidate"; break
    fi
  done
  if [ -z "$PY_BIN" ]; then
    echo "error: need Python 3.10+ to run arctx from source; none found" >&2
    exit 1
  fi
  ARCTX() { "$PY_BIN" -m arctx_cli.main "$@"; }
  echo "(running from local source: $REPO_ROOT, using $PY_BIN)"
elif command -v arctx >/dev/null 2>&1; then
  ARCTX() { arctx "$@"; }
else
  echo "error: no local source and no 'arctx' on PATH — pip install arctx-cli" >&2
  exit 1
fi

node_id() { python3 -c "import sys,json;print(json.load(sys.stdin)['output_node_id'])"; }
step_id() { python3 -c "import sys,json;print(json.load(sys.stdin)['step_id'])"; }
# (the two helpers above only parse JSON, so any python3 will do)

# --- Throwaway sandbox ------------------------------------------------------
WORK="$(mktemp -d "${TMPDIR:-/tmp}/arctx-demo.XXXXXX")"
export ARCTX_HOME="$WORK/arctx-home"
mkdir -p "$ARCTX_HOME"
cd "$WORK"

git init -q
git config user.email "demo@arctx.dev"
git config user.name "ARCTX demo"

echo "==> sandbox: $WORK"
echo

# --- Baseline: a naive implementation. Capture its node id so both agents ---
# --- branch their experiments off the same baseline. ------------------------
ARCTX init optimize --extension git --run-id quickstart >/dev/null 2>&1
cat > work.py <<'PY'
def sum_list(data):
    total = 0
    for x in data:
        total += x
    return total
PY
git add work.py
git commit -qm "baseline: naive python loop"
BASE="$(ARCTX add --title "baseline: naive python loop" --type commit --commit HEAD | node_id)"
echo "[1/4] baseline committed"

# --- Agent 1 (Claude): memoization cache — a dead end -----------------------
ARCTX lane create claude --purpose "claude work" --run quickstart >/dev/null 2>&1
eval "$(ARCTX lane switch claude --run quickstart --shell 2>/dev/null)"
export ARCTX_USER_ID=claude
git checkout -q -b claude/cache
cat > work.py <<'PY'
_cache = {}

def sum_list(data):
    key = id(data)            # BUG: id() is reused after GC; stale on mutation
    if key not in _cache:
        _cache[key] = sum(data)
    return _cache[key]
PY
git add work.py
git commit -qm "Claude: memoization cache"
CACHE_NODE="$(ARCTX add --title "Claude: memoization cache" --type commit --commit HEAD --from "$BASE" | node_id)"
ARCTX attach "$CACHE_NODE" \
  --type benchmark \
  --field elapsed_ms=1300 \
  --field 'verdict=SLOWER + stale results on mutation' >/dev/null
echo "[2/4] Claude's attempt recorded (benchmark attached)"

# --- Agent 2 (Codex): builtin sum() — the winner ----------------------------
ARCTX lane create codex --purpose "codex work" --run quickstart >/dev/null 2>&1
eval "$(ARCTX lane switch codex --run quickstart --shell 2>/dev/null)"
export ARCTX_USER_ID=codex
git checkout -q main
git checkout -q -b codex/builtin
cat > work.py <<'PY'
def sum_list(data):
    return sum(data)
PY
git add work.py
git commit -qm "Codex: builtin sum()"
WIN_NODE="$(ARCTX add --title "Codex: builtin sum()" --type commit --commit HEAD --from "$BASE" | node_id)"
ARCTX attach "$WIN_NODE" \
  --type benchmark \
  --field elapsed_ms=260 \
  --field 'verdict=5x faster, correct' >/dev/null
echo "[3/4] Codex's attempt recorded (winner)"

# --- Abandon the dead end — it stays in the graph, marked inactive ----------
ARCTX cut node "$CACHE_NODE" --reason "slower than baseline and stale on mutation" >/dev/null
echo "[4/4] dead end cut — kept in the graph as a ✂ record, with a reason"
echo

# --- The payoff: one shareable artifact ------------------------------------
OUT="$WORK/run.html"
ARCTX export --format html -o "$OUT" >/dev/null

echo "================================================================"
echo " Both attempts, the cut, and the WHY — in one graph:"
echo "================================================================"
ARCTX export --format md --full-payloads
echo
echo "================================================================"
echo " Shareable HTML written to:"
echo "   $OUT"
echo " Open it:  open '$OUT'  (macOS)  |  xdg-open '$OUT'  (Linux)"
echo "================================================================"
