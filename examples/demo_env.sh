#!/usr/bin/env bash
# Source this from a VHS tape's `Hide` block to enter a clean, reproducible
# demo environment. Isolates HOME / STAG_HOME, sets up a fresh scratch git
# repo with an initial commit, and installs a minimal prompt so recordings
# look like a normal user shell on any machine.

set -e

export STAG_PROJECT_ROOT="$PWD"
export DEMO_HOME="${DEMO_HOME:-/tmp/stag_demo_home}"
rm -rf "$DEMO_HOME"
mkdir -p "$DEMO_HOME"

# Ensure the project's venv is on PATH so `stag` resolves in sub-shells.
if [ -x "$STAG_PROJECT_ROOT/.venv/bin/stag" ]; then
  export PATH="$STAG_PROJECT_ROOT/.venv/bin:$PATH"
fi

# Sub-shells launched by tmux/etc inherit HOME and will read this bashrc,
# so the prompt and stag stay consistent across panes.
cat > "$DEMO_HOME/.bashrc" <<BASHRC
export PS1=\$'\[\e[1;36m\]~/stag-demo\[\e[0m\] \[\e[1;32m\]❯\[\e[0m\] '
export PROMPT_COMMAND=''
export PYTHONPATH=$STAG_PROJECT_ROOT/packages/stag-api/src:$STAG_PROJECT_ROOT/packages/stag-cli/src:$STAG_PROJECT_ROOT/packages/stag-tui/src
export STAG_HOME=$DEMO_HOME/.stag
export PATH="$PATH"
cd "$DEMO_HOME/scratch" 2>/dev/null || true
BASHRC

export HOME="$DEMO_HOME"
export STAG_HOME="$DEMO_HOME/.stag"
export PYTHONPATH="$STAG_PROJECT_ROOT/packages/stag-api/src:$STAG_PROJECT_ROOT/packages/stag-cli/src:$STAG_PROJECT_ROOT/packages/stag-tui/src"
export PS1=$'\[\e[1;36m\]~/stag-demo\[\e[0m\] \[\e[1;32m\]❯\[\e[0m\] '
export PROMPT_COMMAND=''
unset VIRTUAL_ENV_PROMPT

# Force bash for sub-shells (tmux panes, etc). The user's default zsh has
# interactive_comments off, which turns demo `# headings` into errors.
export SHELL=/bin/bash

# Minimal tmux config so panes spawn bash and the status bar stays clean.
cat > "$DEMO_HOME/.tmux.conf" <<'TMUXCONF'
set -g default-shell /bin/bash
set -g default-command /bin/bash
set -g status off
TMUXCONF

# Set up a fresh scratch git repo to act as the user's workspace.
mkdir -p "$DEMO_HOME/scratch"
cd "$DEMO_HOME/scratch"
git init -q -b main
git config user.email "demo@stag.dev"
git config user.name "Demo User"
cat > optimize.py <<'PY'
def run(xs):
    out = []
    for x in xs:
        out.append(x * 2)
    return out
PY
git add optimize.py
git commit -q -m "Initial: baseline loop"

set +e
