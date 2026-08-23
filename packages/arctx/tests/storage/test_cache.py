"""Tests for RunGraph pickle cache."""

from __future__ import annotations

import tempfile
from pathlib import Path

from arctx import init
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.storage._cache import (
    CACHE_SCHEMA_VERSION,
    FINGERPRINTED_FILES,
    fingerprint,
    load_cache,
    save_cache,
)
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


def test_cache_miss_on_stale_key():
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


def test_cache_miss_when_payload_registry_differs(monkeypatch):
    """A cache written by a process with a different decode capability is
    ignored: an older install without an extension's payload types would
    otherwise poison the cache with degraded generic payloads."""
    from arctx.storage import _cache

    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td)
        run = init(Requirement(requirement_id="r", target_type="task", target_id="t"))
        row_counts = (1, 0, 0, 0, 0, 0)
        save_cache(run_dir, row_counts, run.run_graph)
        assert load_cache(run_dir, row_counts) is not None

        # Simulate a reader whose registry differs from the writer's.
        monkeypatch.setattr(
            _cache, "registered_payload_types", lambda: ("something", "else")
        )
        assert load_cache(run_dir, row_counts) is None


def test_cache_miss_when_content_changes_but_row_count_does_not():
    """The failure this fingerprint exists for.

    Storage is git-native, so the ordinary way a run directory changes is a
    checkout, and a checkout routinely swaps content while leaving the number
    of lines alone. Keyed on row counts, the cache answered such a swap with
    the *previous* branch's run — no error, just the wrong data.
    """
    run = init(_req(), run_id="cache_swap")
    run.add_step([run.root_node_id], StepPayload(payload_id="_", target_id="_",
                                                 type="experiment",
                                                 content={"where": "BRANCH-A"}))
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        run_dir = Path(td) / "cache_swap"

        before = store.load_run("cache_swap")
        assert _where(before) == "BRANCH-A"

        payloads = run_dir / "payloads.jsonl"
        rows = payloads.read_text(encoding="utf-8").splitlines()
        swapped = [line.replace("BRANCH-A", "BRANCH-B") for line in rows]
        assert len(swapped) == len(rows)  # same row count, different content
        payloads.write_text("\n".join(swapped) + "\n", encoding="utf-8")

        after = store.load_run("cache_swap")
        assert _where(after) == "BRANCH-B"


def test_cache_miss_when_a_lane_event_changes():
    """lane_events.jsonl is read by load_run, so it must be fingerprinted.

    Row counts covered five files; this was not one of them, so a lane close
    arriving by `git pull` left the cache claiming the lane was still open.
    """
    run = init(_req(), run_id="cache_lane_events")
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(run)
        run_dir = Path(td) / "cache_lane_events"

        first = fingerprint(run_dir)
        (run_dir / "lane_events.jsonl").write_text(
            '{"event_id": "we_x", "event_type": "lane_closed"}\n', encoding="utf-8"
        )
        assert fingerprint(run_dir) != first


def test_fingerprint_covers_every_file_load_run_reads():
    """A file added to the load path must be added to the fingerprint.

    Forgetting one is invisible in every test that does not edit that
    particular file, and shows up in the field as a stale read.
    """
    import inspect
    import re

    source = inspect.getsource(JsonlRunStore.load_run)
    read = set(re.findall(r'"([A-Za-z_]+\.jsonl?|[A-Za-z_]+\.json)"', source))
    missing = read - set(FINGERPRINTED_FILES)
    assert not missing, f"load_run reads {sorted(missing)}, which the cache does not fingerprint"


def _where(handle) -> str | None:
    for payload in handle.run_graph.payloads.values():
        value = (getattr(payload, "content", None) or {}).get("where")
        if value:
            return value
    return None


def test_a_cache_planted_in_the_run_directory_is_never_read(tmp_path):
    """Unpickling is executing, so a run directory must not carry a pickle.

    Git was never the exposed path — the file is git-ignored — but a run
    handed over as a zip, on a shared drive, or over NFS is, and reading it
    took only `arctx dump`.
    """
    import pickle

    canary = tmp_path / "canary.txt"

    class Detonate:
        def __reduce__(self):
            return (_write_canary, (str(canary),))

    run = init(_req(), run_id="planted")
    store = JsonlRunStore(str(tmp_path / "runs"))
    store.save_run(run)
    run_dir = tmp_path / "runs" / "planted"

    planted = run_dir / "run.cache.pkl"
    planted.write_bytes(
        pickle.dumps(
            {
                "schema_version": CACHE_SCHEMA_VERSION,
                "fingerprint": fingerprint(run_dir),
                "payload_types": (),
                "run_graph": Detonate(),
            }
        )
    )

    store.load_run("planted")

    assert not canary.exists(), "a pickle inside the run directory was executed"
    assert not planted.exists(), "the planted file should be discarded, not left to rot"


def _write_canary(path: str) -> str:  # pragma: no cover - only runs if unpickled
    Path(path).write_text("executed", encoding="utf-8")
    return path


def test_the_cache_lives_outside_the_run_directory(tmp_path, monkeypatch):
    from arctx.storage._cache import cache_path, cache_root

    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    run_dir = tmp_path / "runs" / "somewhere"
    run_dir.mkdir(parents=True)

    path = cache_path(run_dir)
    assert cache_root() in path.parents
    assert run_dir not in path.parents


def test_two_checkouts_of_one_run_do_not_share_a_cache(tmp_path, monkeypatch):
    """Two worktrees hold different content under the same run id."""
    from arctx.storage._cache import cache_path

    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    first = tmp_path / "checkout-a" / ".arctx" / "runs" / "demo"
    second = tmp_path / "checkout-b" / ".arctx" / "runs" / "demo"
    first.mkdir(parents=True)
    second.mkdir(parents=True)

    assert cache_path(first) != cache_path(second)


def test_cache_root_follows_the_environment(tmp_path, monkeypatch):
    from arctx.storage._cache import cache_root

    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "explicit"))
    assert cache_root() == tmp_path / "explicit"

    monkeypatch.delenv("ARCTX_CACHE_DIR")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert cache_root() == tmp_path / "xdg" / "arctx"
