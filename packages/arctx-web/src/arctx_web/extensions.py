"""arctx-web extension discovery and script loading.

This is intentionally separate from ``arctx.ext``. Core ARCTX extensions own
schema, verbs, and CLI behavior; arctx-web extensions own browser-side display
code such as payload renderers.
"""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

from arctx.ext.enabled import load_enabled

ENTRY_POINT_GROUP = "arctx_web.extensions"


@dataclass(frozen=True)
class WebRequest:
    """Context passed to an arctx-web extension route."""

    store: Any
    run_id: str
    run_dir: Path
    body: dict[str, Any]
    user_id: str
    work_session_id: str


WebRouteHandler = Callable[[WebRequest], tuple[int, dict[str, Any]]]


@dataclass(frozen=True)
class WebRoute:
    """One JSON route contributed by an arctx-web extension."""

    method: str
    path: str
    handler: WebRouteHandler


@runtime_checkable
class WebExtension(Protocol):
    """Browser-side contribution for one arctx extension."""

    def scripts(self) -> list[str]:
        """Return JavaScript snippets to inject into the GUI page."""

    def routes(self) -> list[WebRoute]:
        """Return JSON API routes owned by this web extension."""


class WebExtensionBase:
    """Convenience base class for arctx-web extensions."""

    def scripts(self) -> list[str]:
        """Return JavaScript snippets to inject into the GUI page."""
        return []

    def routes(self) -> list[WebRoute]:
        """Return JSON API routes owned by this web extension."""
        return []


_BUILTIN: dict[str, str] = {
    "diagram": "arctx_web.ext.diagram:DiagramWebExtension",
    "git": "arctx_web.ext.git:GitWebExtension",
}


def _get_entry_points() -> dict[str, importlib.metadata.EntryPoint]:
    try:
        eps = importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:
        selectable = cast(Any, importlib.metadata.entry_points())
        eps = selectable.get(ENTRY_POINT_GROUP, [])
    return {ep.name: ep for ep in eps}


def _load_provider(name: str) -> WebExtension | None:
    if name in _BUILTIN:
        spec = _BUILTIN[name]
        module_path, class_name = spec.split(":")
        import importlib

        module = importlib.import_module(module_path)
        return _instantiate(getattr(module, class_name))
    ep = _get_entry_points().get(name)
    return _instantiate(ep.load()) if ep is not None else None


def load_enabled_scripts(run_dir: str | Path) -> list[str]:
    """Load web scripts for extensions enabled on this run.

    Entry point names must match the ARCTX extension names recorded in
    ``extensions.json``. Missing web extensions are ignored; not every core
    extension needs browser-side display code.
    """
    scripts: list[str] = []
    for item in load_enabled(run_dir):
        provider = _load_provider(item.name)
        if provider is None:
            continue
        scripts.extend(provider.scripts())
    return scripts


def load_enabled_routes(run_dir: str | Path) -> list[WebRoute]:
    """Load JSON routes for extensions enabled on this run."""
    routes: list[WebRoute] = []
    for item in load_enabled(run_dir):
        provider = _load_provider(item.name)
        if provider is None:
            continue
        routes.extend(provider.routes())
    return routes


def _instantiate(raw: object) -> WebExtension:
    if isinstance(raw, type):
        raw = raw()
    if not callable(getattr(raw, "scripts", None)):
        raise TypeError("arctx_web.extensions entry point must implement scripts()")
    if callable(getattr(raw, "routes", None)):
        return cast(WebExtension, raw)
    return _ScriptOnlyExtension(raw)


class _ScriptOnlyExtension(WebExtensionBase):
    """Adapter for older web extensions that only contributed scripts."""

    def __init__(self, raw: object) -> None:
        self._raw: Any = raw

    def scripts(self) -> list[str]:
        return list(self._raw.scripts())
