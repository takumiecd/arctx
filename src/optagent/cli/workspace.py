"""Workspace-local cursor persistence.

Cursors are view state for UI and wrapper commands. Core RunHandle
writers must not read this module.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from optagent.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class CursorRecord:
    cursor_id: str
    user_id: str
    run_id: str
    target_kind: str
    target_id: str
    label: str = ""
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


def workspace_dir(store_dir: str) -> Path:
    return Path(store_dir).parent / "workspace"


def cursors_path(store_dir: str) -> Path:
    return workspace_dir(store_dir) / "cursors.json"


def load_cursors(store_dir: str) -> dict[str, CursorRecord]:
    path = cursors_path(store_dir)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        cursor_id: CursorRecord(**record)
        for cursor_id, record in data.get("cursors", {}).items()
    }


def save_cursor(record: CursorRecord, store_dir: str) -> Path:
    cursors = load_cursors(store_dir)
    cursors[record.cursor_id] = record
    path = cursors_path(store_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"cursors": {key: value.to_dict() for key, value in cursors.items()}},
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
