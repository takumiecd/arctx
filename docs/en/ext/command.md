# Command Execution Logs Extension (`command`)

The `command` extension captures execution metadata and output logs (exit codes, working directory, execution duration, stdout, and stderr) of external terminal commands or test runners, attaching them to Nodes or Steps.

---

## Features

1. **Automation Auditing**:
   Maintains execution logs of code checks, test commands, or compilers directly inside the RunGraph.
2. **GUI Log Viewer**:
   Renders standard outputs (stdout) and errors (stderr) in a collapsed log viewer within the Web GUI detail panel.

---

## GUI Usage

1. Select a Node or Step, then click **Attach Payload**.
2. Select **Command Run** from the preset list.
3. Fill in the execution details:
   * **Command**: Command executed (e.g. `pytest tests/`)
   * **Exit Code**: Exit status code (e.g. `0` for success)
   * **Working Directory (Cwd)**: Relative or absolute path where it ran
   * **Stdout**: Standard output log
   * **Stderr**: Standard error log
4. Click **attach payload**. The logs are saved and displayed with status tags.

---

## Python API

Automate execution logging using Python scripting. `handle.command.run(...)` **executes the command itself (via `subprocess`)** and automatically captures the exit code, stdout, stderr, and duration, recording them as a new Step. You do not pass stdout/stderr/exit_code yourself.

```python
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

# Runs the command and records its result (exit code / stdout / stderr /
# duration) as a new Step automatically.
result = handle.command.run(
    command=["pytest", "packages/arctx/tests/core/test_run_api.py", "-q"],
    cwd=".",
    # Optional: cap long output (default 20000 chars)
    max_output_chars=20000,
)

print(result)  # dict including exit code and the recorded step_id
```

> Key arguments: `command` (required list), `cwd`, `user_id`, `work_session_id`, `max_output_chars`.
> The new Step is appended at the work-session tip (it is not attached to an arbitrary node after the fact).
