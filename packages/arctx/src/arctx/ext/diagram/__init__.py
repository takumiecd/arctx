"""Built-in diagram extension."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from arctx.ext.base import ExtensionBase

if TYPE_CHECKING:
    from arctx.core.run.handle import RunHandle


@dataclass
class DiagramNamespace:
    """Python API namespace for diagram extension helpers."""

    handle: RunHandle


class DiagramExtension(ExtensionBase):
    """Extension for cyclic-capable diagram/model payload artifacts."""

    name = "diagram"
    version = "0.1"
    description = "Diagram generation and attachment extension."

    def register_schema(self) -> None:
        import arctx.ext.diagram.payloads  # noqa: F401

    def register_verbs(self, handle: RunHandle) -> None:
        if hasattr(handle, self.name):
            return
        setattr(handle, self.name, DiagramNamespace(handle))


__all__ = ["DiagramExtension", "DiagramNamespace"]
