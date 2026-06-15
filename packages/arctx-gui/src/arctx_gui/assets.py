"""Locate the built frontend assets.

Resolution order (first hit wins):

1. ``ARCTX_GUI_STATIC`` env var — explicit override.
2. The packaged ``arctx_gui/static/`` directory — populated at packaging time
   by ``python -m arctx_gui.bundle`` and shipped in the wheel.
3. The repo's ``gui/dist`` — development fallback so ``arctx-gui`` works from a
   source checkout after ``npm --prefix gui run build`` without re-bundling.

Returns ``None`` when no built frontend can be found, so callers can print a
helpful "build the frontend first" message instead of serving 404s.
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGED_STATIC = Path(__file__).resolve().parent / "static"


def _has_index(path: Path) -> bool:
    return (path / "index.html").is_file()


def _repo_gui_dist() -> Path | None:
    # Walk up from this file looking for a sibling ``gui/dist`` (source checkout).
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "gui" / "dist"
        if _has_index(candidate):
            return candidate
    return None


def find_static_dir() -> Path | None:
    override = os.environ.get("ARCTX_GUI_STATIC")
    if override:
        path = Path(override).expanduser()
        return path if _has_index(path) else None
    if _has_index(PACKAGED_STATIC):
        return PACKAGED_STATIC
    return _repo_gui_dist()
