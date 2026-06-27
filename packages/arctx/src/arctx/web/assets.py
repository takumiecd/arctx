"""Locate built frontend assets for ``arctx web``."""

from __future__ import annotations

import os
from pathlib import Path

PACKAGED_STATIC = Path(__file__).resolve().parent / "static"


def _has_index(path: Path) -> bool:
    return (path / "index.html").is_file()


def _repo_web_dist() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "web" / "dist"
        if _has_index(candidate):
            return candidate
    return None


def find_static_dir() -> Path | None:
    override = os.environ.get("ARCTX_WEB_STATIC")
    if override:
        path = Path(override).expanduser()
        return path if _has_index(path) else None
    if _has_index(PACKAGED_STATIC):
        return PACKAGED_STATIC
    return _repo_web_dist()
