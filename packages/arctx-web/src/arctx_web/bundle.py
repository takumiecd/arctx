"""Build the frontend and copy it into the package (``arctx_web/static/``).

Run before packaging so the wheel ships a self-contained GUI:

    python -m arctx_web.bundle

Requires Node/npm and the ``web/`` source tree (only present in a source
checkout). This is a packaging-time tool, not a runtime dependency.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from arctx_web.assets import PACKAGED_STATIC


def _find_web_src() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "web"
        if (candidate / "package.json").is_file():
            return candidate
    return None


def bundle() -> int:
    web = _find_web_src()
    if web is None:
        print("arctx_web.bundle: could not find the web/ source tree", file=sys.stderr)
        return 1

    dist = web / "dist"
    print(f"building frontend in {web} …")
    subprocess.run(["npm", "install"], cwd=web, check=True)
    subprocess.run(["npm", "run", "build"], cwd=web, check=True)
    if not (dist / "index.html").is_file():
        print("arctx_web.bundle: build produced no dist/index.html", file=sys.stderr)
        return 1

    if PACKAGED_STATIC.exists():
        shutil.rmtree(PACKAGED_STATIC)
    shutil.copytree(dist, PACKAGED_STATIC)
    print(f"copied {dist} -> {PACKAGED_STATIC}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(bundle())
