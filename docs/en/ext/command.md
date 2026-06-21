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

Automate execution logging using Python scripting:

```python
import subprocess
import time
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

# The command to run
cmd = ["pytest", "packages/arctx/tests/core/test_run_api.py", "-q"]

start_time = time.time()
res = subprocess.run(cmd, capture_output=True, text=True)
duration_ms = int((time.time() - start_time) * 1000)

# Record command log to node n_abc123
handle.command.run(
    command=cmd,
    exit_code=res.returncode,
    cwd=".",
    stdout=res.stdout,
    stderr=res.stderr,
    duration_ms=duration_ms,
    target_id="n_abc123"
)
```
