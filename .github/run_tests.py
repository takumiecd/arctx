#!/usr/bin/env python3
"""Run the suite from source on any platform.

The packages are not installed in CI; they run from `src/` via PYTHONPATH, and
the separator for that differs between POSIX and Windows. Building it here
keeps one command working on both runners.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = [ROOT / "packages" / "arctx" / "src", ROOT / "packages" / "arctx-cli" / "src"]

env = dict(os.environ)
existing = env.get("PYTHONPATH")
paths = [str(p) for p in SRC] + ([existing] if existing else [])
env["PYTHONPATH"] = os.pathsep.join(paths)

result = subprocess.run(
    [
        sys.executable,
        "-m",
        "pytest",
        str(ROOT / "packages" / "arctx" / "tests"),
        str(ROOT / "packages" / "arctx-cli" / "tests"),
        "--import-mode=importlib",
        "-q",
    ],
    env=env,
    cwd=str(ROOT),
)
sys.exit(result.returncode)
