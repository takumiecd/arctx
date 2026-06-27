"""Per-run sidecar storage for graph layout state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FILENAME = "web_layouts.json"
DEFAULT_VIEW = "default"


def layout_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / FILENAME


def default_document() -> dict[str, Any]:
    return {"version": 1, "layouts": {}}


def load_layouts(run_dir: str | Path) -> dict[str, Any]:
    path = layout_path(run_dir)
    if not path.exists():
        return default_document()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return default_document()
    layouts = data.get("layouts")
    if not isinstance(layouts, dict):
        layouts = {}
    return {"version": 1, "layouts": layouts}


def get_layout(run_dir: str | Path, view: str = DEFAULT_VIEW) -> dict[str, Any]:
    doc = load_layouts(run_dir)
    raw = doc["layouts"].get(view, {})
    if not isinstance(raw, dict):
        raw = {}
    nodes = raw.get("nodes", {})
    if not isinstance(nodes, dict):
        nodes = {}
    return {"view": view, "nodes": _clean_nodes(nodes)}


def save_layout(run_dir: str | Path, body: dict[str, Any]) -> dict[str, Any]:
    view = str(body.get("view") or DEFAULT_VIEW)
    nodes = body.get("nodes", {})
    if not isinstance(nodes, dict):
        raise ValueError("nodes must be an object")
    cleaned = _clean_nodes(nodes)
    doc = load_layouts(run_dir)
    doc["layouts"][view] = {"nodes": cleaned}
    layout_path(run_dir).write_text(
        json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"view": view, "nodes": cleaned}


def _clean_nodes(raw: dict[str, Any]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for node_id, pos in raw.items():
        if not isinstance(pos, dict):
            continue
        try:
            x = float(pos["x"])
            y = float(pos["y"])
        except (KeyError, TypeError, ValueError):
            continue
        out[str(node_id)] = {"x": x, "y": y}
    return out
