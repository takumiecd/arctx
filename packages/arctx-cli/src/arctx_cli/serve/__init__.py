"""Compatibility wrapper for the shared ARCTX local API."""

from arctx.serve import dispatch  # noqa: F401
from arctx.serve import serve  # noqa: F401

__all__ = ["dispatch", "serve"]
