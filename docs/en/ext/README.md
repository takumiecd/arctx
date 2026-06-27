# ARCTX Extensions Overview

ARCTX provides various extensions to add domain-specific features on top of the core DAG-based process recording model (RunGraph). 

This directory contains the documentation and usage guides for each standard extension.

---

## Standard Extensions List

| Extension | Document | Role |
| :--- | :--- | :--- |
| **Git Integration (`git`)** | [Git Integration Guide](git.md) | Links Git repositories, branches, commit logs, and diff summaries to Steps / Nodes. |
| **Diagrams (`diagram`)** | [Diagrams Guide](diagram.md) | Defines and renders Mermaid or Graphviz diagrams as vector graphs on Nodes / Steps. |
| **Command Execution Logs (`command`)** | [Command Logs Guide](command.md) | Records command lines, exit codes, stdout, stderr, and run durations for external tool executions. |
| **Agent Integration (`agents` / `codex`)** | [Agent Recorder Guide](agents.md) | Records AI agent sessions, including tool calls, prompts, and session events into Lanes. |

> Note: **Attachments / Media (`asset`)** used to be an extension; it is now a core standard payload (always available, no enabling needed). → [Attachments Guide](asset.md)

---

## Managing Extensions

You can enable or disable extensions for a run using either the CLI commands or the **extensions** dropdown menu in the Web GUI.

### CLI Management

```bash
# 1. List available extensions and their status for a run
arctx ext list

# 2. Enable an extension (e.g. git)
arctx ext enable git

# 3. Disable an extension
arctx ext disable git
```

### Initializing a Run with Extensions

You can enable one or more extensions when initializing a new run:

```bash
arctx init req_demo --extension git --extension diagram
```
