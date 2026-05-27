"""Shared append-log store interfaces and file-backed implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from arctx.core import _json as _fast_json
from arctx.core.sync.records import read_batches, records_path


@runtime_checkable
class SharedRunStore(Protocol):
    """Minimal append-log interface for shared DAG sync backends."""

    def records_path(self, remote: str, shared_run_id: str) -> Path:
        """Return the backing path for display/debugging."""
        ...

    def read_batches(self, remote: str, shared_run_id: str) -> list[dict[str, Any]]:
        """Read all batch envelopes from a shared run."""
        ...

    def append_batches(
        self,
        remote: str,
        shared_run_id: str,
        batches: list[dict[str, Any]],
    ) -> None:
        """Append batch envelopes atomically enough for a local file prototype."""
        ...


class FileSharedRunStore:
    """File-backed shared append log under a local remotes directory."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    def records_path(self, remote: str, shared_run_id: str) -> Path:
        return records_path(self.root, remote, shared_run_id)

    def read_batches(self, remote: str, shared_run_id: str) -> list[dict[str, Any]]:
        return read_batches(self.root, remote, shared_run_id)

    def append_batches(
        self,
        remote: str,
        shared_run_id: str,
        batches: list[dict[str, Any]],
    ) -> None:
        if not batches:
            return
        path = self.records_path(remote, shared_run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            for batch in batches:
                fh.write(_fast_json.dumps(batch) + "\n")

    def ensure_run(self, remote: str, shared_run_id: str) -> Path:
        """Create the shared run directory and append log if needed."""
        path = self.records_path(remote, shared_run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)
        return path
