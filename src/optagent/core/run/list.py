"""Run listing helper."""

from __future__ import annotations

from optagent.storage.jsonl import JsonlRunStore


def list_runs(store_dir: str) -> list[dict]:
    """Return a list of run summaries from the store directory.

    Parameters
    ----------
    store_dir:
        Directory where runs are stored.

    Returns
    -------
    List of run summary dicts.
    """
    store = JsonlRunStore(store_dir)
    return store.list_runs()
