"""Storage adapters for run directories."""

from stag_api.storage.base import RunStore
from stag_api.storage.jsonl import JsonlRunStore

__all__ = ["RunStore", "JsonlRunStore", "SqliteRunStore"]


def __getattr__(name: str):
    if name == "SqliteRunStore":
        from stag_api.storage.sqlite import SqliteRunStore

        return SqliteRunStore
    raise AttributeError(name)
