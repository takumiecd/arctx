"""Lane: a solo-or-collaborative, append-only unit of work.

A lane is NOT owned by one user. ``created_by`` only records who opened it; any
actor may append events to a shared lane, and per-action attribution lives on
each WorkEvent.user_id. These tests pin that contract (the old per-user owner
lock is gone) plus the back-compat deserialization of the new ``name`` field and
the ``lane_id`` / ``created_by`` aliases.
"""

from __future__ import annotations

import tempfile

import arctx
from arctx import Lane, Requirement, WorkSession
from arctx.core.schema.work import work_session_from_dict
from arctx.storage.jsonl import JsonlRunStore


def _handle(run_id="run_lane"):
    return arctx.init(
        Requirement(requirement_id="r", target_type="repo", target_id="t"),
        run_id=run_id,
    )


def test_lane_is_worksession_alias():
    assert Lane is WorkSession


def test_ensure_lane_sets_name_and_aliases():
    h = _handle()
    lane = h.ensure_lane(name="mips-scd", lane_id="lane_1", created_by="alice")
    assert lane.lane_id == "lane_1"
    assert lane.name == "mips-scd"
    assert lane.created_by == "alice"
    # idempotent: same id returns the existing lane, not a duplicate.
    again = h.ensure_lane(name="ignored", lane_id="lane_1", created_by="bob")
    assert again.lane_id == "lane_1"
    assert again.name == "mips-scd"
    assert len(h.run_graph.work_sessions) == 1


def test_shared_lane_accepts_multiple_actors():
    """No owner lock: alice and bob both append to one lane; attribution per event."""
    h = _handle("run_lane_shared")
    h.ensure_lane(name="shared", lane_id="lane_s", created_by="alice")
    h.record_work_event(user_id="alice", work_session_id="lane_s", event_type="note")
    # different actor, same lane — must NOT raise.
    h.record_work_event(user_id="bob", work_session_id="lane_s", event_type="note")

    actors = {
        e.user_id for e in h.run_graph.work_events if e.work_session_id == "lane_s"
    }
    assert actors == {"alice", "bob"}
    assert len(h.run_graph.work_sessions) == 1  # still one lane


def test_name_survives_round_trip():
    h = _handle("run_lane_rt")
    h.ensure_lane(name="geometry-probe", lane_id="lane_rt", created_by="alice")
    with tempfile.TemporaryDirectory() as td:
        store = JsonlRunStore(td)
        store.save_run(h)
        loaded = store.load_run("run_lane_rt")
    assert loaded.run_graph.work_sessions["lane_rt"].name == "geometry-probe"


def test_from_dict_back_compat():
    # Old row (no name) still loads with name=None.
    old = work_session_from_dict(
        {"work_session_id": "w1", "run_id": "r", "user_id": "alice"}
    )
    assert old.name is None and old.lane_id == "w1"

    # New row may use the lane_* aliases.
    new = work_session_from_dict(
        {"lane_id": "w2", "run_id": "r", "created_by": "bob", "name": "x"}
    )
    assert new.lane_id == "w2" and new.created_by == "bob" and new.name == "x"
