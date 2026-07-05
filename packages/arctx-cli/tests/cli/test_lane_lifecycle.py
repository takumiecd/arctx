"""Tests for the lane open/close lifecycle and the closed-lane write gate."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from arctx_cli.commands.add import run_add_step_command
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
        with pytest.raises(ValueError, match="terminal node"):
            run_lane_close_command(
                name_or_id="work", summary="done", node_ids=None, reason=None,
                run_id="run_lc", user_id="alice", store_dir=sd,
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
