"""LLM backend integrations."""

from optagent.backends.base import Backend, HypothesisResult
from optagent.backends.mock import MockBackend

__all__ = ["Backend", "HypothesisResult", "MockBackend"]
