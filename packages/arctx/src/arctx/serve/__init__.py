"""Shared local HTTP API for ARCTX runs."""

from arctx.serve.api import dispatch
from arctx.serve.server import serve

__all__ = ["dispatch", "serve"]
