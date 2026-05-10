"""Abstract RunStore protocol for pluggable storage backends."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from stag.core.run import RunHandle


@runtime_checkable
class RunStore(Protocol):
    """Minimal interface that any run-storage backend must satisfy.

    Implementations are discovered structurally (no inheritance required).
    The constructor signature is intentionally excluded from the Protocol
    because different backends may require different initialisation arguments
    (e.g. a file-system root path vs. a database URL).
    """

    def run_path(self, run_id: str) -> Path:
        """Return the canonical filesystem path for *run_id*.

        For non-filesystem backends this may be a synthetic path used only
        for display purposes.
        """
        ...

    def list_runs(self) -> list[dict]:
        """Return a summary list of all stored runs.

        Each entry is a plain dict containing at minimum ``run_id``.
        """
        ...

    def save_run(self, run: RunHandle) -> Path:
        """Persist *run* to the store and return its storage path."""
        ...

    def load_run(self, run_id: str) -> RunHandle:
        """Load and return the ``RunHandle`` for *run_id*."""
        ...
