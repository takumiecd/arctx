"""Tests for the lane open/close lifecycle and the closed-lane write gate."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.cut import run_cut_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.lane import (
    list_lanes,
    run_lane_close_command,
    run_lane_create_command,
    run_lane_open_command,
)
from arctx.core.schema.payloads import SummaryPayload
from arctx_cli.context import resolve_store


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init(td: str) -> None:
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_lc",
        store_dir=_store_dir(td),
    )


def _create_lane(sd: str) -> str:
    res = run_lane_create_command(name="work", run_id="run_lc", user_id="alice", store_dir=sd)
    return res["lane_id"]


def _root(sd: str) -> str:
    return resolve_store(sd).load_run("run_lc").root_node_id


def _add(sd: str, from_node: str, lane_id: str, *, title: str, force: bool = False) -> str:
    res = run_add_step_command(
        run_id="run_lc",
        input_node_ids=[from_node],
        title=title,
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=sd,
        user_id="alice",
        lane_id=lane_id,
        force=force,
    )
    return res["step"]["output_node_id"]


def _status(sd: str, lane_id: str) -> str:
    return next(l["status"] for l in list_lanes(run_id="run_lc", store_dir=sd) if l["lane_id"] == lane_id)


def test_close_single_leaf_stamps_existing_leaf_no_extra_node():
    with tempfile.TemporaryDirectory() as td:
        sd = _store_dir(td)
        _init(td)
        lane_id = _create_lane(sd)
        leaf = _add(sd, _root(sd), lane_id, title="s1")

        res = run_lane_close_command(
            name_or_id="work", summary="findings", node_ids=None, reason="done",
            run_id="run_lc", user_id="alice", store_dir=sd,
        )
        # The summary lands on the existing leaf — no convergence node is created.
        assert res["status"] == "closed"
        assert res["summary_node"] == leaf
        assert res["joined_nodes"] == [leaf]
        assert _status(sd, lane_id) == "closed"


def test_status_persists_across_reload():
    with tempfile.TemporaryDirectory() as td:
        sd = _store_dir(td)
        _init(td)
        lane_id = _create_lane(sd)
        _add(sd, _root(sd), lane_id, title="s1")
        run_lane_close_command(
            name_or_id="work", summary="x", node_ids=None, reason=None,
            run_id="run_lc", user_id="alice", store_dir=sd,
        )
        # Fresh load → status is the projection of the lane_closed event.
        assert _status(sd, lane_id) == "closed"


def test_close_summary_format_is_recorded_on_summary_payload():
    with tempfile.TemporaryDirectory() as td:
        sd = _store_dir(td)
        _init(td)
        lane_id = _create_lane(sd)
        leaf = _add(sd, _root(sd), lane_id, title="s1")

        run_lane_close_command(
            name_or_id="work",
            summary="<h2>Conclusion</h2><p>Ship it.</p>",
            summary_format="html",
            node_ids=None,
            reason=None,
            run_id="run_lc",
            user_id="alice",
            store_dir=sd,
        )

        handle = resolve_store(sd).load_run("run_lc")
        summaries = [
            payload
            for payload in handle.run_graph.payloads_for_node(leaf)
            if isinstance(payload, SummaryPayload)
        ]
        assert summaries
        assert summaries[-1].metadata["format"] == "html"


def test_write_to_closed_lane_is_blocked_then_force_overrides():
    with tempfile.TemporaryDirectory() as td:
        sd = _store_dir(td)
        _init(td)
        lane_id = _create_lane(sd)
        leaf = _add(sd, _root(sd), lane_id, title="s1")
        run_lane_close_command(
            name_or_id="work", summary="x", node_ids=None, reason=None,
            run_id="run_lc", user_id="alice", store_dir=sd,
        )
        with pytest.raises(ValueError, match="closed"):
            _add(sd, leaf, lane_id, title="s2")
        # --force punches through.
        forced = _add(sd, leaf, lane_id, title="s2", force=True)
        assert forced


def test_open_reopens_and_allows_writes():
    with tempfile.TemporaryDirectory() as td:
        sd = _store_dir(td)
        _init(td)
        lane_id = _create_lane(sd)
        leaf = _add(sd, _root(sd), lane_id, title="s1")
        run_lane_close_command(
            name_or_id="work", summary="x", node_ids=None, reason=None,
            run_id="run_lc", user_id="alice", store_dir=sd,
        )
        res = run_lane_open_command(
            name_or_id="work", reason="resume", run_id="run_lc",
            user_id="alice", store_dir=sd,
        )
        assert res["status"] == "open"
        assert _status(sd, lane_id) == "open"
        # Writing now succeeds without --force.
        assert _add(sd, leaf, lane_id, title="s2")


def test_open_when_open_and_close_when_closed_error():
    with tempfile.TemporaryDirectory() as td:
        sd = _store_dir(td)
        _init(td)
        _create_lane(sd)
        # opening an already-open lane errors
        with pytest.raises(ValueError, match="already open"):
            run_lane_open_command(
                name_or_id="work", reason=None, run_id="run_lc",
                user_id="alice", store_dir=sd,
            )
        with pytest.raises(ValueError, match="requires --summary"):
            run_lane_close_command(
                name_or_id="work", summary=None, node_ids=None, reason=None,
                run_id="run_lc", user_id="alice", store_dir=sd,
            )
        # An empty lane closes with the summary riding the lane_closed event
        # (no terminal to stamp) — reopen it and give it real work below.
        empty_close = run_lane_close_command(
            name_or_id="work", summary="done", node_ids=None, reason=None,
            run_id="run_lc", user_id="alice", store_dir=sd,
        )
        assert empty_close["summary_node"] is None
        run_lane_open_command(
            name_or_id="work", reason=None, run_id="run_lc",
            user_id="alice", store_dir=sd,
        )
        _add(sd, _root(sd), next(l["lane_id"] for l in list_lanes(run_id="run_lc", store_dir=sd)), title="s1")
        run_lane_close_command(
            name_or_id="work", summary="done", node_ids=None, reason=None,
            run_id="run_lc", user_id="alice", store_dir=sd,
        )
        # closing an already-closed lane errors
        with pytest.raises(ValueError, match="already closed"):
            run_lane_close_command(
                name_or_id="work", summary="again", node_ids=None, reason=None,
                run_id="run_lc", user_id="alice", store_dir=sd,
            )


def test_close_without_summary_message_is_corrective():
    """The missing --summary error must name the exact command to run."""
    with tempfile.TemporaryDirectory() as td:
        sd = _store_dir(td)
        _init(td)
        _create_lane(sd)
        with pytest.raises(ValueError) as excinfo:
            run_lane_close_command(
                name_or_id="work", summary=None, node_ids=None, reason=None,
                run_id="run_lc", user_id="alice", store_dir=sd,
            )
        message = str(excinfo.value)
        assert "arctx lane close work requires --summary" in message
        assert "closing node's synthesis" in message
        assert 'arctx lane close work --summary "<your findings>"' in message


def test_close_without_summary_cli_returns_corrective_message(capsys):
    from arctx_cli.main import main

    with tempfile.TemporaryDirectory() as td:
        sd = _store_dir(td)
        _init(td)
        _create_lane(sd)
        rc = main(["lane", "close", "work", "--run", "run_lc", "--store-dir", sd])
        assert rc == 2
        err = capsys.readouterr().err
        assert "arctx lane close work requires --summary" in err
        assert 'arctx lane close work --summary "<your findings>"' in err


def test_close_succeeds_without_explicit_node_after_cutting_only_child(
    tmp_path, monkeypatch
):
    """Regression for the frontier bug: a node whose only child was cut must
    count as an active terminal again, so `lane close` without `--node`
    should find it instead of raising "requires at least one active
    terminal node".

    Isolated via monkeypatch.chdir(tmp_path): run_init_command writes the
    active-run pointer under the nearest git repo's .git/arctx-id, and this
    repo's own .git/arctx-id must not be touched by test runs.
    """
    monkeypatch.chdir(tmp_path)
    td = str(tmp_path)
    sd = _store_dir(td)
    _init(td)
    lane_id = _create_lane(sd)
    root = _root(sd)
    parent = _add(sd, root, lane_id, title="parent")
    child = _add(sd, parent, lane_id, title="child")

    run = resolve_store(sd).load_run("run_lc")
    child_step_id = next(
        s.step_id for s in run.run_graph.steps.values() if s.output_node_id == child
    )
    run_cut_command(
        run_id="run_lc",
        target_id=child,
        target_kind="node",
        reason="stale",
        store_dir=sd,
        user_id="alice",
        lane_id=lane_id,
    )
    run_cut_command(
        run_id="run_lc",
        target_id=child_step_id,
        target_kind="step",
        reason="stale",
        store_dir=sd,
        user_id="alice",
        lane_id=lane_id,
    )

    res = run_lane_close_command(
        name_or_id="work", summary="findings", node_ids=None, reason="done",
        run_id="run_lc", user_id="alice", store_dir=sd,
    )
    assert res["status"] == "closed"
    assert res["summary_node"] == parent
    assert res["joined_nodes"] == [parent]


def test_close_empty_lane_records_summary_on_event(tmp_path):
    """A lane that owns no steps must still be closable; the conclusion rides
    the lane_closed event and lane_overview falls back to it."""
    from arctx.core.lanes import lane_overview
    from arctx_cli.commands.lane import run_lane_close_command, run_lane_create_command
    from arctx_cli.context import resolve_store

    store_dir = str(tmp_path / "runs")
    from arctx_cli.commands.init import run_init_command

    run_init_command(
        requirement_id="r", target_type="task", target_id="t",
        run_id="run_hyg", store_dir=store_dir,
    )
    created = run_lane_create_command(
        name="zombie", run_id="run_hyg", user_id="u", store_dir=store_dir
    )
    result = run_lane_close_command(
        name_or_id="zombie", summary="empty duplicate; no work recorded",
        node_ids=None, reason=None, run_id="run_hyg", user_id="u", store_dir=store_dir,
    )
    assert result["status"] == "closed"
    assert result["summary_node"] is None

    graph = resolve_store(store_dir).load_run("run_hyg").run_graph
    overview = lane_overview(graph, created["lane_id"])
    assert overview.status == "closed"
    assert overview.summary_text == "empty duplicate; no work recorded"


def test_close_falls_back_to_last_output_when_no_frontier(tmp_path):
    """A lane whose outputs were consumed elsewhere has no frontier, but close
    still stamps its last output node instead of refusing."""
    from arctx_cli.commands.add import run_add_step_command
    from arctx_cli.commands.init import run_init_command
    from arctx_cli.commands.lane import run_lane_close_command, run_lane_create_command

    store_dir = str(tmp_path / "runs")
    init = run_init_command(
        requirement_id="r", target_type="task", target_id="t",
        run_id="run_hyg2", store_dir=store_dir,
    )
    lane_a = run_lane_create_command(
        name="feeder", run_id="run_hyg2", user_id="u", store_dir=store_dir
    )
    run_lane_create_command(
        name="consumer", run_id="run_hyg2", user_id="u", store_dir=store_dir
    )
    step = run_add_step_command(
        run_id="run_hyg2", input_node_ids=[init["root_node_id"]], title="produce",
        payload_kind=None, payload_type="step_payload", field_data={}, json_data={},
        store_dir=store_dir, user_id="u", lane_id=lane_a["lane_id"],
    )["step"]
    # Consume feeder's output from another lane → feeder has no frontier left.
    consumer_lane = [
        l for l in __import__("arctx_cli.context", fromlist=["resolve_store"])
        .resolve_store(store_dir).load_run("run_hyg2").run_graph.lanes.values()
        if l.name == "consumer"
    ][0]
    run_add_step_command(
        run_id="run_hyg2", input_node_ids=[step["output_node_id"]], title="consume",
        payload_kind=None, payload_type="step_payload", field_data={}, json_data={},
        store_dir=store_dir, user_id="u", lane_id=consumer_lane.lane_id,
    )
    result = run_lane_close_command(
        name_or_id="feeder", summary="produced the baseline; consumed downstream",
        node_ids=None, reason=None, run_id="run_hyg2", user_id="u", store_dir=store_dir,
    )
    assert result["status"] == "closed"
    assert result["summary_node"] == step["output_node_id"]


def test_lane_create_warns_about_stale_open_lanes(tmp_path):
    from datetime import datetime, timedelta, timezone

    from arctx.core.lanes import stale_open_lanes
    from arctx_cli.commands.init import run_init_command
    from arctx_cli.commands.lane import run_lane_create_command
    from arctx_cli.context import resolve_store

    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="r", target_type="task", target_id="t",
        run_id="run_hyg3", store_dir=store_dir,
    )
    run_lane_create_command(name="old", run_id="run_hyg3", user_id="u", store_dir=store_dir)

    graph = resolve_store(store_dir).load_run("run_hyg3").run_graph
    future = datetime.now(timezone.utc) + timedelta(days=30)
    stale = stale_open_lanes(graph, now=future)
    assert [lane.name for lane, _, _ in stale] == ["old"]
    assert stale[0][2] >= 7

    result = run_lane_create_command(
        name="newer", run_id="run_hyg3", user_id="u", store_dir=store_dir
    )
    # Fresh lanes are not stale yet; the field exists and excludes itself.
    assert result["stale_open_lanes"] == []
