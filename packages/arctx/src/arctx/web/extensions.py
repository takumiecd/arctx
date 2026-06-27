"""Browser-side extension hooks for the bundled GUI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any


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


def load_enabled_scripts(run_dir: str | Path) -> list[str]:
    return []


def load_enabled_routes(run_dir: str | Path) -> list[WebRoute]:
    return []
