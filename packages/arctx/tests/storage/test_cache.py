"""Tests for RunGraph pickle cache."""

from __future__ import annotations

import tempfile
from pathlib import Path

from arctx import init
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.storage._cache import CACHE_SCHEMA_VERSION, load_cache, save_cache
from arctx.storage.jsonl import JsonlRunStore


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _tp() -> StepPayload:
    return StepPayload(payload_id="_", target_id="_", type="experiment")


def test_cache_miss_on_empty_dir():
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td) / "run"
        run_dir.mkdir()
        result = load_cache(run_dir, (0, 0, 0, 0, 0, 0))
        assert result is None


def test_cache_roundtrip():
    run = init(_req(), run_id="cache_rt")
    t1 = run.add_step([run.root_node_id], _tp())
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        run_dir = Path(td) / "cache_rt"
        row_counts = (2, 1, 1, 1, 0, 0)
        save_cache(run_dir, row_counts, run.run_graph)
        cached = load_cache(run_dir, row_counts)
        assert cached is not None
        assert len(cached.nodes) == len(run.run_graph.nodes)


def test_cache_miss_on_stale_counts():
    run = init(_req(), run_id="cache_stale")
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        run_dir = Path(td) / "cache_stale"
        row_counts = (1, 0, 0, 1, 0, 0)
        save_cache(run_dir, row_counts, run.run_graph)
        # Different counts → cache miss.
        stale = load_cache(run_dir, (99, 0, 0, 1, 0, 0))
        assert stale is None


def test_cache_used_on_load():
    """JsonlRunStore.load_run should use the cache on second load."""
    run = init(_req(), run_id="cache_use")
    t1 = run.add_step([run.root_node_id], _tp())
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        # First load populates cache.
        loaded1 = store.load_run("cache_use")
        # Second load should hit cache (no error expected).
        loaded2 = store.load_run("cache_use")
        assert len(loaded2.run_graph.nodes) == len(loaded1.run_graph.nodes)
