"""A batch lands whole, or it is still recoverable.

One `append_batch` spans four files, so there are four places for it to stop:
a killed process, a full disk, a laptop losing power. Before the journal, what
survived a stop was permanent — a step whose payload never landed stayed that
way for the life of the run, describing nothing about what it did.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from arctx import init
from arctx.core.append import AppendBatch, GraphRecordEnvelope
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.core.schema.work import Lane, WorkEvent
from arctx.storage import jsonl as jsonl_module
from arctx.storage.jsonl import JsonlRunStore, read_journal


def _store(td: str) -> tuple[JsonlRunStore, str]:
    run = init(Requirement(requirement_id="r", target_type="task", target_id="t"),
               run_id="journal")
    store = JsonlRunStore(td)
    store.save_run(run)
    return store, run.root_node_id


def _batch(store: JsonlRunStore, root: str) -> AppendBatch:
    """A batch shaped like the CLI's: a step, its output node, and a payload."""
    handle = store.load_run("journal")
    step = handle.add_step([root], StepPayload(payload_id="_", target_id="_",
                                               type="experiment", content={"n": 1}))
    graph = handle.run_graph
    node = graph.nodes[step.output_node_id]
    payload = next(
        graph.payloads[pid] for pid in graph.payloads_by_step.get(step.step_id, ())
    )
    lane = Lane(lane_id="default", run_id="journal", created_by="u")
    return AppendBatch(
        run_id="journal",
        user_id="u",
        lane_id="default",
        lane=lane,
        records=(
            GraphRecordEnvelope(record_kind="node", record_id=node.node_id, record=node),
            GraphRecordEnvelope(record_kind="step", record_id=step.step_id, record=step),
            GraphRecordEnvelope(record_kind="payload", record_id=payload.payload_id,
                                record=payload),
        ),
        events=(
            WorkEvent(event_id="we_1", run_id="journal", lane_id="default", user_id="u",
                      event_type="add_step", created_records=[step.step_id]),
        ),
    )


@pytest.fixture()
def torn(monkeypatch):
    """Run a batch that dies partway through writing payloads.jsonl."""
    with tempfile.TemporaryDirectory() as td:
        store, root = _store(td)
        run_path = Path(td) / "journal"
        batch = _batch(store, root)

        real = jsonl_module._append_dicts

        def flaky(path: Path, rows):
            if path.name == "payloads.jsonl" and rows:
                raise OSError(28, "No space left on device")
            return real(path, rows)

        monkeypatch.setattr(jsonl_module, "_append_dicts", flaky)
        with pytest.raises(OSError):
            store.append_batch(batch)
        monkeypatch.setattr(jsonl_module, "_append_dicts", real)

        yield store, run_path, batch


def test_the_interrupted_file_really_did_not_get_its_rows(torn):
    _, run_path, _ = torn
    rows = (run_path / "payloads.jsonl").read_text(encoding="utf-8").strip()
    assert rows == ""


def test_a_reader_still_sees_the_whole_batch(torn):
    """Without this, a step exists that says nothing about what it did."""
    store, _, _ = torn
    graph = store.load_run("journal").run_graph
    steps_without_payloads = [
        step_id for step_id in graph.steps if not graph.payloads_by_step.get(step_id)
    ]
    assert steps_without_payloads == []


def test_the_journal_survives_the_failure(torn):
    _, run_path, _ = torn
    pending = read_journal(run_path)
    assert "payloads.jsonl" in pending


def test_the_next_write_replays_it(torn):
    store, run_path, _ = torn
    handle = store.load_run("journal")
    tip = next(iter(handle.run_graph.steps.values())).output_node_id
    store.append_batch(_batch(store, tip))

    assert not (run_path / ".append.journal").exists()
    payload_rows = [
        line for line in (run_path / "payloads.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(payload_rows) == 2  # the replayed one and the new one


def test_replay_does_not_double_write(torn):
    """Records are immutable and keyed by opaque id, so replay must be a no-op
    for anything already on disk."""
    store, run_path, batch = torn
    jsonl_module._recover_journal(run_path)
    jsonl_module._recover_journal(run_path)
    rows = [
        line for line in (run_path / "payloads.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1


def test_a_pending_batch_is_not_cached(torn):
    """The cache key describes the files; a graph holding journal rows is not
    what those files say."""
    store, run_path, _ = torn
    cache = run_path / "run.cache.pkl"
    cache.unlink(missing_ok=True)   # written by the earlier clean save_run
    store.load_run("journal")
    assert not cache.exists()


def test_a_torn_journal_describes_nothing(torn):
    """A journal cut off mid-write belongs to a batch that had not started
    landing, so the safe reading is "nothing pending"."""
    _, run_path, _ = torn
    (run_path / ".append.journal").write_text('{"files": {"payloads.js', encoding="utf-8")
    assert read_journal(run_path) == {}
    store = JsonlRunStore(str(run_path.parent))
    assert store.load_run("journal") is not None


def test_a_clean_batch_leaves_no_journal():
    with tempfile.TemporaryDirectory() as td:
        store, root = _store(td)
        store.append_batch(_batch(store, root))
        assert not (Path(td) / "journal" / ".append.journal").exists()
