"""arctx-web extension discovery and script loading.

This is intentionally separate from ``arctx.ext``. Core ARCTX extensions own
schema, verbs, and CLI behavior; arctx-web extensions own browser-side display
code such as payload renderers.
"""

from __future__ import annotations

import importlib.metadata
from pathlib import Path
from typing import Protocol, runtime_checkable

from arctx.ext.enabled import load_enabled

ENTRY_POINT_GROUP = "arctx_web.extensions"


@runtime_checkable
class WebExtension(Protocol):
    """Browser-side contribution for one arctx extension."""

    def scripts(self) -> list[str]:
        """Return JavaScript snippets to inject into the GUI page."""


class WebExtensionBase:
    """Convenience base class for arctx-web extensions."""

    def scripts(self) -> list[str]:
        return []


def _get_entry_points() -> dict[str, importlib.metadata.EntryPoint]:
    try:
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        eps = importlib.metadata.entry_points().get(ENTRY_POINT_GROUP, [])
    return {ep.name: ep for ep in eps}


def load_enabled_scripts(run_dir: str | Path) -> list[str]:
    """Load web scripts for extensions enabled on this run.

    Entry point names must match the ARCTX extension names recorded in
    ``extensions.json``. Missing web extensions are ignored; not every core
    extension needs browser-side display code.
    """
    entry_points = _get_entry_points()
    scripts: list[str] = []
    for item in load_enabled(run_dir):
        ep = entry_points.get(item.name)
        if ep is None:
            continue
        provider = _instantiate(ep.load())
        scripts.extend(provider.scripts())
    return scripts


def _instantiate(raw: object) -> WebExtension:
    if isinstance(raw, type):
        raw = raw()
    if not isinstance(raw, WebExtension):
        raise TypeError("arctx_web.extensions entry point must implement scripts()")
    return raw
