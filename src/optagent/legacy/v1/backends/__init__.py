"""LLM backend integrations."""

from optagent.legacy.v1.backends.base import Backend, HypothesisResult
from optagent.legacy.v1.backends.mock import MockBackend

__all__ = ["Backend", "HypothesisResult", "MockBackend"]
