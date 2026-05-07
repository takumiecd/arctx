"""Tests for Step 1 of the multi-actor cursor model.

Run init seeds a default human Actor and a ``main`` Cursor. The main
cursor's ``current_state_id`` mirrors ``current_observed_state_id``
through observe / promote / rewind. Storage roundtrip preserves both
records.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import optagent
from optagent.core.schema.cursor import (
    DEFAULT_ACTOR_ID,
    DEFAULT_CURSOR_ID,
    Actor,
    Cursor,
)
from optagent.core.schema.requirements import Requirement
from optagent.core.schema.results import ActionResult
from optagent.storage.jsonl import JsonlRunStore


def _new_run(run_id: str = "r"):
    return optagent.init(
        Requirement(requirement_id="req_test", target_type="code", target_id="t"),
        run_id=run_id,
    )


def _advance(handle, plan_intent: str, result_id: str) -> str:
    plan = handle.plan(intent=plan_intent)[0]
    handle.observe(
        plan.plan_id,
        ActionResult(
            result_id=result_id,
            execution_plan_id=plan.plan_id,
            status="completed",
        ),
    )
    return handle.current_observed_state_id


class TestDefaultSeeding:
    def test_init_creates_default_actor(self):
        run = _new_run()
        assert DEFAULT_ACTOR_ID in run.actors
        actor = run.actors[DEFAULT_ACTOR_ID]
        assert isinstance(actor, Actor)
        assert actor.actor_type == "human"
        assert actor.status == "active"

    def test_init_creates_main_cursor(self):
        run = _new_run()
        assert DEFAULT_CURSOR_ID in run.cursors
        cursor = run.cursors[DEFAULT_CURSOR_ID]
        assert isinstance(cursor, Cursor)
        assert cursor.owner_actor_id == DEFAULT_ACTOR_ID
        assert cursor.state_kind == "observed"
        assert cursor.current_state_id == run.current_observed_state_id


class TestMainCursorMirrorsCurrent:
    """Until ``current_observed_state_id`` is retired, the main cursor mirrors it."""

    def test_observe_advances_main_cursor(self):
        run = _new_run()
        new_state = _advance(run, "first", "r_0001")
        assert run.cursors[DEFAULT_CURSOR_ID].current_state_id == new_state
        assert new_state == run.current_observed_state_id

    def test_rewind_moves_main_cursor_back(self):
        run = _new_run()
        s0 = run.current_observed_state_id
        plan = run.plan()[0]
        observed = run.observe(
            plan.plan_id,
            ActionResult(
                result_id="r_0001",
                execution_plan_id=plan.plan_id,
                status="completed",
            ),
        )
        assert run.cursors[DEFAULT_CURSOR_ID].current_state_id != s0

        run.rewind(observed.transition_id)
        assert run.cursors[DEFAULT_CURSOR_ID].current_state_id == s0
        assert run.current_observed_state_id == s0

    def test_main_cursor_does_not_drift_independently(self):
        """The cursor mirrors the field; field stays the source of truth."""
        run = _new_run()
        _advance(run, "first", "r_0001")
        run.cursors[DEFAULT_CURSOR_ID].current_state_id = "tampered"
        # The next observed-pointer move re-syncs main cursor to current.
        s2 = _advance(run, "second", "r_0002")
        assert run.cursors[DEFAULT_CURSOR_ID].current_state_id == s2


class TestStorageRoundtrip:
    def test_actors_and_cursors_persist(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlRunStore(Path(tmpdir))
            run = _new_run("persist_run")
            _advance(run, "first", "r_0001")
            store.save_run(run)

            loaded = store.load_run("persist_run")
            assert DEFAULT_ACTOR_ID in loaded.actors
            assert loaded.actors[DEFAULT_ACTOR_ID].actor_type == "human"
            assert DEFAULT_CURSOR_ID in loaded.cursors
            main = loaded.cursors[DEFAULT_CURSOR_ID]
            assert main.current_state_id == run.cursors[DEFAULT_CURSOR_ID].current_state_id
            assert main.owner_actor_id == DEFAULT_ACTOR_ID
            assert main.state_kind == "observed"

    def test_load_existing_run_without_cursor_files(self):
        """Older runs that predate cursor files should load with empty maps.

        New code seeds default actor/cursor on init(). For runs saved
        before this commit, actors.jsonl / cursors.jsonl do not exist;
        the loader must tolerate that and not crash.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            store = JsonlRunStore(Path(tmpdir))
            run = _new_run("legacy_run")
            store.save_run(run)
            # Simulate a legacy run by deleting the cursor files.
            (Path(tmpdir) / "legacy_run" / "actors.jsonl").unlink()
            (Path(tmpdir) / "legacy_run" / "cursors.jsonl").unlink()

            loaded = store.load_run("legacy_run")
            assert loaded.actors == {}
            assert loaded.cursors == {}
            # Legacy field still works.
            assert loaded.current_observed_state_id == run.current_observed_state_id
