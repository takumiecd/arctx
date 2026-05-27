"""Storage adapters for run directories."""

from arctx.storage.base import RunStore
from arctx.storage.jsonl import JsonlRunStore

__all__ = ["RunStore", "JsonlRunStore", "SqliteRunStore"]


def __getattr__(name: str):
    if name == "SqliteRunStore":
        from arctx.storage.sqlite import SqliteRunStore

        return SqliteRunStore
    raise AttributeError(name)
