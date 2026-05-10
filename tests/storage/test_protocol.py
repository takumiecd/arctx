"""Verify that JsonlRunStore satisfies the RunStore Protocol."""

from __future__ import annotations

import tempfile

from stag.storage import JsonlRunStore, RunStore


def test_jsonl_run_store_is_instance_of_run_store() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = JsonlRunStore(tmp)
        assert isinstance(store, RunStore)
