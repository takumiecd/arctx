# STAG Demo: Director's Script

Use this script when recording your screen using the Ghostty terminal. 

## Video 1: Parallel Work Sessions (CLI)

**Setup:**
1. Open Ghostty.
2. Split the screen vertically into two panes.
3. In both panes, run: `export PYTHONPATH=src`

**Action 1: Left Pane (Codex)**
*Type these commands slowly to show them off:*
```bash
# Initialize a new STAG run with Git support
stag init req_parallel --extension git --run-id demo_cli

# Create a work session for Codex
eval "$(stag work-session env --run demo_cli --name codex --new)"

# Make an experimental commit
stag git commit -m "Codex: trying parallel map implementation"
```

**Action 2: Right Pane (Claude)**
*Switch your focus to the right pane and type:*
```bash
# Create a parallel work session for Claude
eval "$(stag work-session env --run demo_cli --name claude --new)"

# Make a completely different experimental commit in parallel
stag git commit -m "Claude: trying vectorization approach"
```

**Action 3: Left Pane (Check History)**
*Switch back to the left pane and type:*
```bash
# Notice that Codex's session is isolated from Claude's session!
stag show --run demo_cli
```

*Stop recording.*

---

## Video 2: The Complex TUI (Visual)

**Setup:**
1. Close the split screen so you have one large, full-screen terminal pane.
2. Run the generator script to create a massive DAG automatically:
   ```bash
   ./examples/generate_tui_graph.sh
   ```

**Action (Recording):**
*Start recording.*
```bash
# Let's visualize the complex optimization graph!
stag tui --run demo_tui
```
*Once the TUI opens, use the arrow keys (or `j`/`k`) to navigate the tree, showing off the branches, failed nodes, and success states.*

*Stop recording.*
