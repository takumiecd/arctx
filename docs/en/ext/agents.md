# Agent Integration Extension (`agents` / `codex`)

The `agents` extension (and its associated adapter `codex`) automatically records activities from AI coding agents (such as OpenAI's Codex) into the ARCTX RunGraph, tracking tool calls, prompts, and session lifecycles.

---

## Features

1. **WorkSession Tracking**:
   Logs agent executions as distinct `WorkSession` lanes, showing temporal agent branches.
2. **Automated Step Generation**:
   Converts agent tool calls and prompts into Steps on the DAG.
3. **Session Completion Detection**:
   Marks session terminations by attaching completion `NodePayload` markers containing results metadata.
4. **Fail-Safe Design**:
   Hook operations run silently in the background and default to exit code `0` on failures to avoid blocking the agent process (override with `--strict`).

---

## Architecture

The recording pipeline uses a two-tier decoupled design:

1. **Session Recorder (`SessionRecorder`)**:
   An agent-neutral API (`arctx/ext/agents/recorder.py`, re-exported from `arctx.ext.agents`) that records generic `agent.*` payload types onto the graph.
2. **Codex Adapter (`arctx/ext/codex/adapter.py`)**:
   Parses Codex's hook events JSON format from stdin and dispatches calls to the `SessionRecorder`.

---

## CLI Usage

Hook integrations run automatically in the background.

### 1. Install Hook Scripts
Merges hook commands into the Codex hooks file (`.codex/hooks.json`):

```bash
# Register hooks in .codex/hooks.json
arctx codex install

# Target $CODEX_HOME/hooks.json (or ~/.codex/hooks.json) globally
arctx codex install --global

# Override command executable path
arctx codex install --command "/usr/local/bin/arctx"
```

### 2. Handle Hook Events (Internal Flow)
Once installed, the hook calls the following command in response to agent lifecycle triggers:

```bash
# Feeds hook event payload from stdin into the graph recorder
arctx codex hook < event.json
```
*(💡 Errors inside the hook program exit 0 by default to prevent blocking agent runs. Specify `--strict` to fail loudly on hook errors).*
