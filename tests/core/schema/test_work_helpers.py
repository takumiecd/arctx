"""Tests for work_helpers: make_*_event and latest_* query functions."""

from __future__ import annotations

import pytest

from stag.core.schema.work import WorkSession
from stag.core.schema.work_helpers import (
    BRANCH_TIP_EVENT,
    SESSION_POINTER_EVENT,
    latest_branch_tip,
    latest_session_pointer,
    make_branch_tip_event,
    make_session_pointer_event,
)
from stag.core.run_graph import RunGraph
from stag.core.schema.graph import Node


def _make_graph_with_session(session_id: str = "ws_1", user_id: str = "user") -> RunGraph:
    graph = RunGraph()
    root = Node(node_id="n_root")
    graph.add_node(root)
    session = WorkSession(
        work_session_id=session_id,
        run_id="run_1",
        user_id=user_id,
    )
    graph.add_work_session(session)
    return graph


class TestMakeSessionPointerEvent:
    def test_event_type(self):
        ev = make_session_pointer_event(
            event_id="we_1",
            run_id="run_1",
            work_session_id="ws_1",
            user_id="user",
            current_node_ids=("n_abc",),
            current_branch="main",
        )
        assert ev.event_type == SESSION_POINTER_EVENT

    def test_data_fields(self):
        ev = make_session_pointer_event(
            event_id="we_1",
            run_id="run_1",
            work_session_id="ws_1",
            user_id="user",
            current_node_ids=("n_1", "n_2"),
            current_branch="feature",
        )
        assert ev.data["current_node_ids"] == ["n_1", "n_2"]
        assert ev.data["current_branch"] == "feature"

    def test_current_branch_none(self):
        ev = make_session_pointer_event(
            event_id="we_1",
            run_id="run_1",
            work_session_id="ws_1",
            user_id="user",
            current_node_ids=("n_1",),
            current_branch=None,
        )
        assert ev.data["current_branch"] is None

    def test_metadata(self):
        ev = make_session_pointer_event(
            event_id="we_x",
            run_id="run_1",
            work_session_id="ws_1",
            user_id="alice",
            current_node_ids=("n_1",),
            current_branch=None,
        )
        assert ev.event_id == "we_x"
        assert ev.run_id == "run_1"
        assert ev.work_session_id == "ws_1"
        assert ev.user_id == "alice"


class TestMakeBranchTipEvent:
    def test_event_type(self):
        ev = make_branch_tip_event(
            event_id="we_2",
            run_id="run_1",
            work_session_id="ws_1",
            user_id="user",
            branch="main",
            tip_node_id="n_tip",
        )
        assert ev.event_type == BRANCH_TIP_EVENT

    def test_data_fields(self):
        ev = make_branch_tip_event(
            event_id="we_2",
            run_id="run_1",
            work_session_id="ws_1",
            user_id="user",
            branch="feature/x",
            tip_node_id="n_tip",
        )
        assert ev.data["branch"] == "feature/x"
        assert ev.data["tip_node_id"] == "n_tip"


class TestLatestSessionPointer:
    def test_returns_none_when_no_events(self):
        graph = _make_graph_with_session()
        assert latest_session_pointer(graph, "ws_1") is None

    def test_returns_latest_event(self):
        graph = _make_graph_with_session()
        ev1 = make_session_pointer_event(
            event_id="we_1", run_id="run_1", work_session_id="ws_1", user_id="user",
            current_node_ids=("n_a",), current_branch="main",
        )
        ev2 = make_session_pointer_event(
            event_id="we_2", run_id="run_1", work_session_id="ws_1", user_id="user",
            current_node_ids=("n_b",), current_branch="main",
        )
        graph.add_work_event(ev1)
        graph.add_work_event(ev2)

        result = latest_session_pointer(graph, "ws_1")
        assert result is not None
        assert result.event_id == "we_2"
        assert result.data["current_node_ids"] == ["n_b"]

    def test_filters_by_session(self):
        graph = RunGraph()
        root = Node(node_id="n_root")
        graph.add_node(root)
        ws_a = WorkSession(work_session_id="ws_a", run_id="run_1", user_id="user")
        ws_b = WorkSession(work_session_id="ws_b", run_id="run_1", user_id="user")
        graph.add_work_session(ws_a)
        graph.add_work_session(ws_b)

        ev_a = make_session_pointer_event(
            event_id="we_a", run_id="run_1", work_session_id="ws_a", user_id="user",
            current_node_ids=("n_root",), current_branch="main",
        )
        ev_b = make_session_pointer_event(
            event_id="we_b", run_id="run_1", work_session_id="ws_b", user_id="user",
            current_node_ids=("n_other",), current_branch="dev",
        )
        graph.add_work_event(ev_a)
        graph.add_work_event(ev_b)

        result = latest_session_pointer(graph, "ws_a")
        assert result is not None
        assert result.event_id == "we_a"

        result_b = latest_session_pointer(graph, "ws_b")
        assert result_b is not None
        assert result_b.event_id == "we_b"


class TestLatestBranchTip:
    def test_returns_none_when_no_events(self):
        graph = _make_graph_with_session()
        assert latest_branch_tip(graph, "main") is None

    def test_returns_latest_tip_for_branch(self):
        graph = _make_graph_with_session()
        ev1 = make_branch_tip_event(
            event_id="we_1", run_id="run_1", work_session_id="ws_1", user_id="user",
            branch="main", tip_node_id="n_old_tip",
        )
        ev2 = make_branch_tip_event(
            event_id="we_2", run_id="run_1", work_session_id="ws_1", user_id="user",
            branch="main", tip_node_id="n_new_tip",
        )
        graph.add_work_event(ev1)
        graph.add_work_event(ev2)

        result = latest_branch_tip(graph, "main")
        assert result is not None
        assert result.data["tip_node_id"] == "n_new_tip"

    def test_filters_by_branch(self):
        graph = _make_graph_with_session()
        ev_main = make_branch_tip_event(
            event_id="we_m", run_id="run_1", work_session_id="ws_1", user_id="user",
            branch="main", tip_node_id="n_main_tip",
        )
        ev_dev = make_branch_tip_event(
            event_id="we_d", run_id="run_1", work_session_id="ws_1", user_id="user",
            branch="dev", tip_node_id="n_dev_tip",
        )
        graph.add_work_event(ev_main)
        graph.add_work_event(ev_dev)

        assert latest_branch_tip(graph, "main").data["tip_node_id"] == "n_main_tip"
        assert latest_branch_tip(graph, "dev").data["tip_node_id"] == "n_dev_tip"
        assert latest_branch_tip(graph, "other") is None
