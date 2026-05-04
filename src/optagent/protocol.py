"""File-based protocol for parent-child agent communication.

ManagerAgent and child agents communicate via files:
  work_items/
    h_001/
      request.json
      response.json
      patch.diff
      logs/
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ProtocolError(Exception):
    """Protocol violation."""
    pass


class WorkItemDir:
    """Manages a work item directory."""

    def __init__(self, base_dir: Path | str, item_id: str) -> None:
        self.base_dir = Path(base_dir)
        self.item_id = item_id
        self.path = self.base_dir / item_id
        self.path.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.path / "logs"
        self.logs_dir.mkdir(exist_ok=True)

    @property
    def request_path(self) -> Path:
        return self.path / "request.json"

    @property
    def response_path(self) -> Path:
        return self.path / "response.json"

    @property
    def patch_path(self) -> Path:
        return self.path / "patch.diff"

    def write_request(self, data: dict[str, Any]) -> None:
        """Write request from parent to child."""
        self.request_path.write_text(json.dumps(data, indent=2, default=str))

    def read_request(self) -> dict[str, Any]:
        """Read request (child side)."""
        if not self.request_path.exists():
            raise ProtocolError(f"No request found at {self.request_path}")
        return json.loads(self.request_path.read_text())

    def write_response(self, data: dict[str, Any]) -> None:
        """Write response from child to parent."""
        self.response_path.write_text(json.dumps(data, indent=2, default=str))

    def read_response(self) -> dict[str, Any]:
        """Read response (parent side)."""
        if not self.response_path.exists():
            raise ProtocolError(f"No response found at {self.response_path}")
        return json.loads(self.response_path.write_text())

    def write_patch(self, content: str) -> None:
        """Write patch file."""
        self.patch_path.write_text(content)

    def read_patch(self) -> str:
        """Read patch file."""
        if not self.patch_path.exists():
            return ""
        return self.patch_path.read_text()

    def write_log(self, name: str, content: str) -> None:
        """Write log file."""
        log_path = self.logs_dir / f"{name}.log"
        log_path.write_text(content)

    def read_log(self, name: str) -> str:
        """Read log file."""
        log_path = self.logs_dir / f"{name}.log"
        if not log_path.exists():
            return ""
        return log_path.read_text()


def create_work_item(base_dir: Path | str, item_id: str) -> WorkItemDir:
    """Factory for creating work item directories."""
    return WorkItemDir(base_dir, item_id)
