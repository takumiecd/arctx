Output examples/demo_cli.gif

Set Shell "bash"
Set FontSize 15
Set Width 1200
Set Height 600
Set Theme "Catppuccin Macchiato"
Set Padding 20
Set WindowBar Colorful

Hide
Type "source examples/demo_env.sh"
Enter
Type "tmux kill-server 2>/dev/null; true"
Enter
Type "clear"
Enter
Show

Type "tmux new -s arctx_vhs"
Enter
Sleep 1.5s

Type "# 1. Initialize a new ARCTX run"
Enter
Type "arctx init req_parallel --extension git --run-id ws_demo"
Enter
Sleep 1.5s

Type "# 2. Give each agent its own git worktree (separate checkouts)"
Enter
Type "arctx git worktree add ../wt-claude claude/vec"
Enter
Sleep 1s
Type "arctx git worktree add ../wt-codex  codex/map"
Enter
Sleep 1.2s

Type "# 3. Split the screen to simulate two AI agents working in parallel"
Enter
Ctrl+B
Type "%"
Sleep 1s

# Right pane = Claude, pinned to ../wt-claude
Type "clear"
Enter
Sleep 300ms
Type "# [Claude's Terminal — ../wt-claude]"
Enter
Type "cd ../wt-claude"
Enter
Type `eval $(arctx work-session env --run ws_demo --new --user claude --worktree .)`
Enter
Sleep 800ms

Type "echo 'def claude_vec(xs): return [x*2 for x in xs]' > claude.py"
Enter
Type "git add claude.py"
Enter
Type "arctx git commit -m 'Claude: vectorization approach'"
Enter
Sleep 1.8s

# Back to left pane = Codex, pinned to ../wt-codex
Ctrl+B
Left
Sleep 800ms

Type "clear"
Enter
Sleep 300ms
Type "# [Codex's Terminal — ../wt-codex]"
Enter
Type "cd ../wt-codex"
Enter
Type `eval $(arctx work-session env --run ws_demo --new --user codex --worktree .)`
Enter
Sleep 800ms

Type "echo 'def codex_map(xs): return list(map(lambda x: x*2, xs))' > codex.py"
Enter
Type "git add codex.py"
Enter
Type "arctx git commit -m 'Codex: parallel map implementation'"
Enter
Sleep 1.8s

Type "# Separate checkouts, no shared working tree — both branches"
Enter
Type "# land as sibling steps in the same RunGraph."
Enter
Type "arctx dump --run ws_demo --format outline"
Enter
Sleep 5s

Hide
Type "tmux kill-server 2>/dev/null; true"
Enter
