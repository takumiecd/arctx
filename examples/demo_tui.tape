Output examples/demo_tui.gif

Set Shell "bash"
Set FontSize 15
Set Width 1600
Set Height 800
Set Theme "Catppuccin Macchiato"
Set Padding 20
Set WindowBar Colorful

Hide
Type "source examples/demo_env.sh"
Enter
Type "clear"
Enter
Show

Type "# 1. Automatically generating a complex DAG for the demo..."
Enter
Type "bash $STAG_PROJECT_ROOT/examples/generate_tui_graph.sh"
Enter
Sleep 3s

Type "clear"
Enter

Type "# 2. Open the TUI to visualize the graph"
Enter
Type "stag-tui"
Enter
Sleep 2.5s

# Focus the Flowchart pane so arrow keys move the selection.
Type "2"
Sleep 1s

# Walk down into one of the experiment branches, then back up.
Down
Sleep 600ms
Down
Sleep 600ms
Down
Sleep 600ms
Down
Sleep 1s
Up
Sleep 600ms
Up
Sleep 600ms
Up
Sleep 1s

# Slide across branches to show every experiment is tracked.
Right
Sleep 600ms
Right
Sleep 600ms
Right
Sleep 1s
Left
Sleep 600ms
Left
Sleep 600ms
Left
Sleep 1s

# Open the detail modal for the selected node, then close it.
Enter
Sleep 2.5s
Escape
Sleep 1.2s

# Quit
Type "q"
Sleep 1.5s
