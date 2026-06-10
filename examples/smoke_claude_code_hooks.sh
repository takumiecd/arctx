#!/usr/bin/env bash
# Smoke test for the Claude Code hooks adapter.
# Creates a throwaway run, replays a realistic hook event sequence through
# `arctx claude-code hook`, and dumps the resulting graph.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

export PYTHONPATH="$REPO_ROOT/packages/arctx/src:$REPO_ROOT/packages/arctx-cli/src"
export ARCTX_HOME="$WORKDIR/.arctx-home"
unset ARCTX_RUN_ID ARCTX_USER_ID ARCTX_WORK_SESSION_ID 2>/dev/null || true

cd "$WORKDIR"
git init -q .

A() { python3 -m arctx_cli.main "$@"; }
hook() { echo "$1" | A claude-code hook --run demo; }

A init cc_demo --run-id demo >/dev/null
A claude-code install --settings .claude/settings.json >/dev/null
echo '--- .claude/settings.json (PostToolUse entry):'
python3 -c "import json;print(json.dumps(json.load(open('.claude/settings.json'))['hooks']['PostToolUse'],indent=2))"

# Session 1: Claude works on the task.
hook '{"hook_event_name":"SessionStart","session_id":"sess-claude","transcript_path":"/t/a.jsonl","cwd":"'"$WORKDIR"'","source":"startup","model":"claude-fable-5"}'
hook '{"hook_event_name":"UserPromptSubmit","session_id":"sess-claude","prompt":"カーネルを最適化して"}'
hook '{"hook_event_name":"PostToolUse","session_id":"sess-claude","tool_name":"Edit","tool_input":{"file_path":"kernel.py","old_string":"loop","new_string":"vectorized"},"tool_output":"ok"}'
hook '{"hook_event_name":"PostToolUse","session_id":"sess-claude","tool_name":"Bash","tool_input":{"command":"pytest -q"},"tool_output":"3 passed"}'
hook '{"hook_event_name":"Stop","session_id":"sess-claude"}'

# Session 2 in parallel: lands as a sibling branch off the root.
hook '{"hook_event_name":"UserPromptSubmit","session_id":"sess-codex","prompt":"同じタスクを別アプローチで"}'

echo '--- dump:'
A dump --run demo --format outline --full-payloads
echo '--- work sessions:'
A work-session list --run demo | python3 -c "import json,sys;[print(s['work_session_id'],s['user_id'],s['metadata'].get('claude_code',{}).get('model','')) for s in json.load(sys.stdin)['work_sessions']]"
