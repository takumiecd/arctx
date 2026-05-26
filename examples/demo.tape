Output examples/demo.gif

Set FontSize 16
Set Width 1200
Set Height 700
Set Theme "Catppuccin Mocha"
Set WindowBar Colorful
Set Padding 20

Hide
Type "export PYTHONPATH=src"
Enter
Type "rm -rf /tmp/stag_vhs_demo"
Enter
Type "clear"
Enter
Show

Type "# 1. Initialize a new STAG run"
Enter
Type "stag init req_vhs_demo --run-id vhs_demo --store-dir /tmp/stag_vhs_demo"
Sleep 500ms
Enter
Sleep 2s
Enter

Type "# 2. Use the built-in TUI to visualize the optimization DAG"
Enter
Type "stag tui --run vhs_demo --store-dir /tmp/stag_vhs_demo"
Sleep 500ms
Enter
Sleep 4s

# Close TUI
Type "q"
Sleep 1s
