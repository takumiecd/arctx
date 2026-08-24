"""A writer must not commit a decision made against a stale snapshot.

`reparent` reads the run, finds the node's single active producer, retires it,
and appends its own. The run lock is taken only for the append — so two writers
that loaded the same state both decide "retire T0, add mine", both append, and
the node ends with two active producers. Neither writer errs; nothing detects
it at write time.

These tests do not race on timing. They reproduce the same thing
deterministically: two handles loaded from the same disk state, each deciding
against its own snapshot, both committed through the real append path.
"""

from __future__ import annotations

import pytest

from arctx import init
from arctx.core.cuts import nodes_with_multiple_active_producers
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.storage.jsonl import ConcurrentWriteRejected, JsonlRunStore
from arctx_cli.append_batch import build_append_batch, graph_counts


def _tp() -> StepPayload:
    return StepPayload(payload_id="_", target_id="_", type="note")


def _seed(tmp_path):
    """root -> A, root -> B, root -> C, A -> X. X's producer is the A step."""
    store = JsonlRunStore(str(tmp_path / "runs"))
    handle = init(Requirement(requirement_id="r", target_type="task", target_id="t"),
                  run_id="race")
    handle.ensure_lane(user_id="u", lane_id="L")
    kw = dict(user_id="u", lane_id="L")
    a = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    b = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    c = handle.add_step([handle.root_node_id], _tp(), **kw).output_node_id
    x = handle.add_step([a], _tp(), **kw).output_node_id
    store.save_run(handle)
    return store, x, b, c


def _reparent_and_commit(store, node_id, new_input, title):
    """One writer's whole cycle: load, decide, append — as the CLI does."""
    handle = store.load_run("race")
    before = graph_counts(handle)
    handle.reparent(
        node_id,
        [new_input],
        StepPayload(payload_id="_", target_id="_", type=title),
        user_id="u",
        lane_id="L",
    )
    return store.append_batch(
        build_append_batch(handle, user_id="u", lane_id="L", before=before)
    )


def test_the_second_stale_writer_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    store, x, b, c = _seed(tmp_path)

    # Both writers load the same state before either commits. This is exactly
    # what two concurrent processes see.
    first = store.load_run("race")
    second = store.load_run("race")
    for handle, new_input in ((first, b), (second, c)):
        handle._pending_before = graph_counts(handle)
        handle.reparent(
            x, [new_input], _tp(), user_id="u", lane_id="L",
        )

    store.append_batch(
        build_append_batch(first, user_id="u", lane_id="L", before=first._pending_before)
    )
    with pytest.raises(ConcurrentWriteRejected):
        store.append_batch(
            build_append_batch(
                second, user_id="u", lane_id="L", before=second._pending_before
            )
        )

    # And the run on disk is intact.
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cold"))
    fresh = JsonlRunStore(str(tmp_path / "runs")).load_run("race")
    assert nodes_with_multiple_active_producers(fresh.run_graph) == []


def test_sequential_reparents_still_work(tmp_path, monkeypatch):
    """The guard must only reject a *stale* writer, not a normal one."""
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    store, x, b, c = _seed(tmp_path)

    _reparent_and_commit(store, x, b, "first")
    _reparent_and_commit(store, x, c, "second")

    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cold"))
    fresh = JsonlRunStore(str(tmp_path / "runs")).load_run("race")
    assert nodes_with_multiple_active_producers(fresh.run_graph) == []


def test_unrelated_concurrent_writes_are_not_refused(tmp_path, monkeypatch):
    """Two writers touching different nodes must both land."""
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    store, x, b, c = _seed(tmp_path)

    first = store.load_run("race")
    second = store.load_run("race")
    b1 = graph_counts(first)
    b2 = graph_counts(second)
    first.add_step([b], _tp(), user_id="u", lane_id="L")
    second.add_step([c], _tp(), user_id="u", lane_id="L")

    store.append_batch(build_append_batch(first, user_id="u", lane_id="L", before=b1))
    store.append_batch(build_append_batch(second, user_id="u", lane_id="L", before=b2))

    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cold"))
    fresh = JsonlRunStore(str(tmp_path / "runs")).load_run("race")
    assert nodes_with_multiple_active_producers(fresh.run_graph) == []
    assert len(fresh.run_graph.steps) == 6


def test_without_the_guard_the_corruption_is_exactly_what_lands(tmp_path, monkeypatch):
    """Pin what the guard is for: the same sequence with it off corrupts the run.

    `validate=False` is the pre-fix behaviour — the lock covers the append but
    not the decision that produced it.
    """
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    store, x, b, c = _seed(tmp_path)

    first = store.load_run("race")
    second = store.load_run("race")
    b1, b2 = graph_counts(first), graph_counts(second)
    first.reparent(x, [b], _tp(), user_id="u", lane_id="L")
    second.reparent(x, [c], _tp(), user_id="u", lane_id="L")

    store.append_batch(
        build_append_batch(first, user_id="u", lane_id="L", before=b1), validate=False
    )
    store.append_batch(
        build_append_batch(second, user_id="u", lane_id="L", before=b2), validate=False
    )

    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cold"))
    fresh = JsonlRunStore(str(tmp_path / "runs")).load_run("race")
    broken = nodes_with_multiple_active_producers(fresh.run_graph)
    assert [node_id for node_id, _ in broken] == [x]


def test_a_pre_existing_error_does_not_block_an_unrelated_write(tmp_path, monkeypatch):
    """Only *new* errors are the writer's fault."""
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    store, x, b, c = _seed(tmp_path)

    # Corrupt the run first, with the guard off.
    first = store.load_run("race")
    second = store.load_run("race")
    b1, b2 = graph_counts(first), graph_counts(second)
    first.reparent(x, [b], _tp(), user_id="u", lane_id="L")
    second.reparent(x, [c], _tp(), user_id="u", lane_id="L")
    store.append_batch(
        build_append_batch(first, user_id="u", lane_id="L", before=b1), validate=False
    )
    store.append_batch(
        build_append_batch(second, user_id="u", lane_id="L", before=b2), validate=False
    )

    # An ordinary write elsewhere must still be allowed through.
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache2"))
    later = store.load_run("race")
    before = graph_counts(later)
    later.add_step([b], _tp(), user_id="u", lane_id="L")
    store.append_batch(
        build_append_batch(later, user_id="u", lane_id="L", before=before)
    )


def test_a_lane_closed_after_the_decision_refuses_the_write(tmp_path, monkeypatch):
    """The closed-lane gate runs before the lock, against the writer's snapshot.

    A lane closed between the gate and the append used to let the write land
    anyway — the gate had already said yes.
    """
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    store, x, b, c = _seed(tmp_path)

    writer = store.load_run("race")
    before = graph_counts(writer)
    writer.add_step([b], _tp(), user_id="u", lane_id="L")

    # Someone else closes the lane in between, the documented way.
    closer = store.load_run("race")
    closer.set_lane_status("L", status="closed", user_id="other", reason="done")
    store.save_run(closer)

    with pytest.raises(ConcurrentWriteRejected, match="closed"):
        store.append_batch(
            build_append_batch(writer, user_id="u", lane_id="L", before=before)
        )


def test_force_still_writes_to_a_closed_lane(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path / "cache"))
    store, x, b, c = _seed(tmp_path)

    writer = store.load_run("race")
    before = graph_counts(writer)
    writer.add_step([b], _tp(), user_id="u", lane_id="L")
    closer = store.load_run("race")
    closer.set_lane_status("L", status="closed", user_id="other", reason="done")
    store.save_run(closer)

    store.append_batch(
        build_append_batch(
            writer, user_id="u", lane_id="L", before=before, force=True
        )
    )
