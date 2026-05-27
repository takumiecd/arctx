"""Tests for make_reset_event helper and round-trip serialization."""

from __future__ import annotations

import json

from stag_api.core.schema.work import WorkEvent
from stag_api.core.schema.work_helpers import RESET_EVENT, make_reset_event


def _build_event(**overrides) -> WorkEvent:
    defaults = dict(
        event_id="we_reset_1",
        run_id="run_test",
        work_session_id="ws_1",
        user_id="user",
        from_node_id="n_from",
        to_node_id="n_to",
        mode="hard",
        discarded_transition_ids=("t_1", "t_2"),
    )
    defaults.update(overrides)
    return make_reset_event(**defaults)


class TestMakeResetEvent:
    def test_event_type(self):
        event = _build_event()
        assert event.event_type == RESET_EVENT
        assert event.event_type == "reset"

    def test_data_fields(self):
        event = _build_event(
            from_node_id="n_from",
            to_node_id="n_to",
            mode="mixed",
            discarded_transition_ids=("t_a", "t_b", "t_c"),
        )
        assert event.data["from_node_id"] == "n_from"
        assert event.data["to_node_id"] == "n_to"
        assert event.data["mode"] == "mixed"
        assert event.data["discarded_transition_ids"] == ["t_a", "t_b", "t_c"]

    def test_identity_fields(self):
        event = _build_event(
            event_id="we_x",
            run_id="run_42",
            work_session_id="ws_abc",
            user_id="alice",
        )
        assert event.event_id == "we_x"
        assert event.run_id == "run_42"
        assert event.work_session_id == "ws_abc"
        assert event.user_id == "alice"

    def test_empty_discarded(self):
        event = _build_event(discarded_transition_ids=())
        assert event.data["discarded_transition_ids"] == []

    def test_mode_hard(self):
        event = _build_event(mode="hard")
        assert event.data["mode"] == "hard"

    def test_mode_soft(self):
        event = _build_event(mode="soft")
        assert event.data["mode"] == "soft"

    def test_round_trip_json(self):
        """WorkEvent.data must be JSON-serializable."""
        event = _build_event()
        raw = json.dumps(event.data)
        loaded = json.loads(raw)
        assert loaded["from_node_id"] == "n_from"
        assert loaded["to_node_id"] == "n_to"
        assert loaded["mode"] == "hard"
        assert loaded["discarded_transition_ids"] == ["t_1", "t_2"]
