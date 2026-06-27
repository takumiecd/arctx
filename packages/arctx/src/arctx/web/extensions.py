"""Browser-side extension discovery for the bundled GUI."""

from __future__ import annotations

import importlib.metadata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast, runtime_checkable

from arctx.ext.enabled import load_enabled


@dataclass(frozen=True)
class WebRequest:
    store: Any
    run_id: str
    run_dir: Path
    body: dict[str, Any]
    user_id: str
    lane_id: str


WebRouteHandler = Callable[[WebRequest], tuple[int, dict[str, Any]]]


@dataclass(frozen=True)
class WebRoute:
    method: str
    path: str
    handler: WebRouteHandler


ENTRY_POINT_GROUP = "arctx_web.extensions"


@runtime_checkable
class WebExtension(Protocol):
    def scripts(self) -> list[str]:
        """Return JavaScript snippets to inject into the GUI page."""

    def routes(self) -> list[WebRoute]:
        """Return JSON routes owned by this web extension."""


class WebExtensionBase:
    def scripts(self) -> list[str]:
        return []

    def routes(self) -> list[WebRoute]:
        return []


_BUILTIN: dict[str, str] = {
    "diagram": "arctx.web.ext.diagram:DiagramWebExtension",
    "git": "arctx.web.ext.git:GitWebExtension",
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
    scripts: list[str] = []
    for item in load_enabled(run_dir):
        provider = _load_provider(item.name)
        if provider is None:
            continue
        scripts.extend(provider.scripts())
    return scripts


def load_enabled_routes(run_dir: str | Path) -> list[WebRoute]:
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
    def __init__(self, raw: object) -> None:
        self._raw: Any = raw

    def scripts(self) -> list[str]:
        return list(self._raw.scripts())
