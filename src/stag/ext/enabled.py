"""Persist / load the per-run list of enabled extensions.

Stored at <run_dir>/extensions.json:

    {
      "enabled": [
        {"name": "git", "version": "0.1", "config": {...}}
      ]
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_FILENAME = "extensions.json"


@dataclass(frozen=True)
class EnabledExtension:
    name: str
    version: str
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "version": self.version, "config": dict(self.config)}


def enabled_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / _FILENAME


def load_enabled(run_dir: str | Path) -> list[EnabledExtension]:
    """Return the list of enabled extensions for *run_dir*. Empty list if none."""
    path = enabled_path(run_dir)
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("enabled", []) if isinstance(data, dict) else []
    out: list[EnabledExtension] = []
    for item in items:
        out.append(
            EnabledExtension(
                name=str(item.get("name", "")),
                version=str(item.get("version", "")),
                config=dict(item.get("config") or {}),
            )
        )
    return out


def save_enabled(run_dir: str | Path, enabled: list[EnabledExtension]) -> Path:
    path = enabled_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"enabled": [e.to_dict() for e in enabled]}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def add_enabled(run_dir: str | Path, ext: EnabledExtension) -> list[EnabledExtension]:
    """Append *ext* if not already enabled. Returns updated list."""
    current = load_enabled(run_dir)
    if any(e.name == ext.name for e in current):
        return current
    current.append(ext)
    save_enabled(run_dir, current)
    return current
