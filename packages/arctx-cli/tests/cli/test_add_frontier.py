"""Tests for ``arctx add`` defaulting ``--from`` to the current lane frontier."""

from __future__ import annotations

from pathlib import Path

import pytest

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.lane import run_lane_create_command
from arctx_cli.context import resolve_store
from arctx_cli.main import main


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init(td: str, run_id: str = "run_add_frontier") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(td),
    )


def _step(sd: str, run_id: str, parent: str, title: str, lane_id: str | None = None) -> dict:
    return run_add_step_command(
        run_id=run_id,
        input_node_ids=[parent],
        title=title,
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=sd,
        user_id="alice",
        lane_id=lane_id,
    )["step"]


def test_add_without_from_uses_single_lane_frontier(tmp_path):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    lane = run_lane_create_command(
        name="work", run_id="run_add_frontier", user_id="alice", store_dir=sd
    )
    first = _step(sd, "run_add_frontier", init["root_node_id"], "s1", lane["lane_id"])

    # No --from: exactly one active frontier in the lane (first's output node).
    result = run_add_step_command(
        run_id="run_add_frontier",
        input_node_ids=None,
        title="s2",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=sd,
        user_id="alice",
        lane_id=lane["lane_id"],
    )
    assert result["step"]["input_node_ids"] == [first["output_node_id"]]


def test_add_without_from_zero_frontiers_raises_clear_error(tmp_path):
    # Once the run root has already been consumed by a step elsewhere, a lane
    # with zero frontiers of its own has no unambiguous node to default to —
    # the root fallback only applies while the root is still untouched.
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    other_lane = run_lane_create_command(
        name="other", run_id="run_add_frontier", user_id="alice", store_dir=sd
    )
    _step(sd, "run_add_frontier", init["root_node_id"], "s1", other_lane["lane_id"])

    lane = run_lane_create_command(
        name="empty", run_id="run_add_frontier", user_id="alice", store_dir=sd
    )
    with pytest.raises(ValueError, match="no active frontiers"):
        run_add_step_command(
            run_id="run_add_frontier",
            input_node_ids=None,
            title="s",
            payload_kind=None,
            payload_type="step_payload",
            field_data={},
            json_data={},
            store_dir=sd,
            user_id="alice",
            lane_id=lane["lane_id"],
        )


def test_add_without_from_fresh_run_uses_root_node(tmp_path):
    """The very first ``add`` on a fresh run has no lane frontiers at all —
    the root node itself is the only possible input, so it should be used
    automatically instead of forcing an explicit ``--from``."""
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)

    first = run_add_step_command(
        run_id="run_add_frontier",
        input_node_ids=None,
        title="s1",
        payload_kind="suggestion",
        payload_type="step_payload",
        field_data={"proposal": "x"},
        json_data={},
        store_dir=sd,
        user_id="alice",
        lane_id="default",
    )["step"]
    assert first["input_node_ids"] == [init["root_node_id"]]

    # Chains from the first step's output on the second add, still with no
    # --from, now that the default lane has exactly one active frontier.
    second = run_add_step_command(
        run_id="run_add_frontier",
        input_node_ids=None,
        title="s2",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=sd,
        user_id="alice",
        lane_id="default",
    )["step"]
    assert second["input_node_ids"] == [first["output_node_id"]]


def test_add_without_from_multiple_frontiers_lists_candidates(tmp_path):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    lane = run_lane_create_command(
        name="fanout", run_id="run_add_frontier", user_id="alice", store_dir=sd
    )
    first = _step(sd, "run_add_frontier", init["root_node_id"], "s1", lane["lane_id"])
    left = _step(sd, "run_add_frontier", first["output_node_id"], "left", lane["lane_id"])
    right = _step(sd, "run_add_frontier", first["output_node_id"], "right", lane["lane_id"])

    with pytest.raises(ValueError) as excinfo:
        run_add_step_command(
            run_id="run_add_frontier",
            input_node_ids=None,
            title="s",
            payload_kind=None,
            payload_type="step_payload",
            field_data={},
            json_data={},
            store_dir=sd,
            user_id="alice",
            lane_id=lane["lane_id"],
        )
    message = str(excinfo.value)
    assert "2 active" in message
    assert left["output_node_id"] in message
    assert right["output_node_id"] in message
    assert "arctx add --from" in message


def test_add_explicit_from_unchanged(tmp_path):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    lane = run_lane_create_command(
        name="work", run_id="run_add_frontier", user_id="alice", store_dir=sd
    )
    first = _step(sd, "run_add_frontier", init["root_node_id"], "s1", lane["lane_id"])
    left = _step(sd, "run_add_frontier", first["output_node_id"], "left", lane["lane_id"])
    right = _step(sd, "run_add_frontier", first["output_node_id"], "right", lane["lane_id"])

    # Even though there are 2 frontiers, an explicit --from still works and is
    # not affected by frontier resolution.
    result = run_add_step_command(
        run_id="run_add_frontier",
        input_node_ids=[left["output_node_id"], right["output_node_id"]],
        title="merge",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=sd,
        user_id="alice",
        lane_id=lane["lane_id"],
    )
    assert set(result["step"]["input_node_ids"]) == {
        left["output_node_id"],
        right["output_node_id"],
    }


def test_add_rejects_new_lane_validation_error(tmp_path):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    math = run_lane_create_command(
        name="math", run_id="run_add_frontier", user_id="alice", store_dir=sd
    )
    other = run_lane_create_command(
        name="other", run_id="run_add_frontier", user_id="alice", store_dir=sd
    )
    _step(sd, "run_add_frontier", init["root_node_id"], "math-root", math["lane_id"])
    other_root = _step(
        sd, "run_add_frontier", init["root_node_id"], "other-root", other["lane_id"]
    )

    with pytest.raises(ValueError, match="multiple_lane_roots"):
        _step(
            sd,
            "run_add_frontier",
            other_root["output_node_id"],
            "bad second root",
            math["lane_id"],
        )

    handle = resolve_store(sd).load_run("run_add_frontier")
    assert len(handle.run_graph.steps) == 2


def test_add_cli_without_from_flag_succeeds(tmp_path, capsys):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    lane = run_lane_create_command(
        name="work", run_id="run_add_frontier", user_id="alice", store_dir=sd
    )
    first = _step(sd, "run_add_frontier", init["root_node_id"], "s1", lane["lane_id"])

    rc = main(
        [
            "add",
            "--type", "note",
            "--field", "text=hello",
            "--run", "run_add_frontier",
            "--store-dir", sd,
            "--lane", lane["lane_id"],
            "--user", "alice",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert first["output_node_id"] in out


def test_add_cli_without_from_ambiguous_returns_1(tmp_path, capsys):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    lane = run_lane_create_command(
        name="fanout", run_id="run_add_frontier", user_id="alice", store_dir=sd
    )
    first = _step(sd, "run_add_frontier", init["root_node_id"], "s1", lane["lane_id"])
    _step(sd, "run_add_frontier", first["output_node_id"], "left", lane["lane_id"])
    _step(sd, "run_add_frontier", first["output_node_id"], "right", lane["lane_id"])

    rc = main(
        [
            "add",
            "--type", "note",
            "--field", "text=hello",
            "--run", "run_add_frontier",
            "--store-dir", sd,
            "--lane", lane["lane_id"],
            "--user", "alice",
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "active frontiers" in err
