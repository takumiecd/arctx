"""Build the frontend and copy it into the package (``arctx_gui/static/``).

Run before packaging so the wheel ships a self-contained GUI:

    python -m arctx_gui.bundle

Requires Node/npm and the ``gui/`` source tree (only present in a source
checkout). This is a packaging-time tool, not a runtime dependency.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from arctx_gui.assets import PACKAGED_STATIC


def _find_gui_src() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "gui"
        if (candidate / "package.json").is_file():
            return candidate
    return None


def bundle() -> int:
    gui = _find_gui_src()
    if gui is None:
        print("arctx_gui.bundle: could not find the gui/ source tree", file=sys.stderr)
        return 1

    dist = gui / "dist"
    print(f"building frontend in {gui} …")
    subprocess.run(["npm", "install"], cwd=gui, check=True)
    subprocess.run(["npm", "run", "build"], cwd=gui, check=True)
    if not (dist / "index.html").is_file():
        print("arctx_gui.bundle: build produced no dist/index.html", file=sys.stderr)
        return 1

    if PACKAGED_STATIC.exists():
        shutil.rmtree(PACKAGED_STATIC)
    shutil.copytree(dist, PACKAGED_STATIC)
    print(f"copied {dist} -> {PACKAGED_STATIC}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(bundle())
