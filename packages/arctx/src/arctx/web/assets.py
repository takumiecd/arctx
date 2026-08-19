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
    # In a source checkout, prefer the freshly-built frontend. The packaged
    # bundle also exists in the repository and may be older than ``web/dist``;
    # choosing it first makes ``npm run build`` appear to have no effect when
    # developers restart ``arctx web``. Installed wheels do not have a sibling
    # source ``web/dist``, so they continue to fall back to PACKAGED_STATIC.
    repo_dist = _repo_web_dist()
    if repo_dist is not None:
        return repo_dist
    if _has_index(PACKAGED_STATIC):
        return PACKAGED_STATIC
    return None
