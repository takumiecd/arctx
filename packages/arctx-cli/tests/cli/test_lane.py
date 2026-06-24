"""Tests for the ``lane`` CLI command (switch-by-name, open membership)."""

from __future__ import annotations

import tempfile
from argparse import Namespace
from pathlib import Path

from arctx.core.schema.payloads import StepPayload

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.lane import (
    list_lanes,
    run_lane_adopt_command,
    run_lane_create_command,
    run_lane_switch_command,
    validate_lane_run,
)
from arctx_cli.context import resolve_store, resolve_work_session_id_from_args


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init(td: str) -> dict:
    return run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_lane",
        store_dir=_store_dir(td),
    )


def _seed_default_lane_node(sd: str) -> str:
    """Add a step (with its output node) into the ``default`` lane low-level.

    Exercises the non-blocking ``default_lane_membership`` warning. A bare
    producer-less node would now also trip the ``lane_root_not_step_output``
    error, so we derive the node as a step output instead — a lane root must be
    a step output.
    """
    store = resolve_store(sd)
    handle = store.load_run("run_lane")
    payload = StepPayload(payload_id=handle._next_id("pl"), target_id="pending", type="seed")
    step = handle.add_step(
        [handle.root_node_id],
        payload,
        user_id="alice",
        work_session_id="default",
    )
    store.save_run(handle)
    return step.output_node_id


def test_create_then_switch_named_lane():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        sd = _store_dir(td)
        created = run_lane_create_command(
            name="geometry", run_id="run_lane", user_id="alice",
            store_dir=sd,
        )
        assert created["created"] is True
        assert created["name"] == "geometry"

        switched = run_lane_switch_command(
            name="geometry", run_id="run_lane", user_id="bob",
            store_dir=sd, shell=True,
        )
        assert switched["created"] is False
        assert switched["lane_id"] == created["lane_id"]
        assert switched["export"].startswith("export ARCTX_LANE_ID=")
        assert "ARCTX_WORK_SESSION_ID=" in switched["export"]

        lanes = list_lanes(run_id="run_lane", store_dir=sd)
        assert len(lanes) == 1
        assert lanes[0]["name"] == "geometry"
        assert lanes[0]["created_by"] == "alice"  # creator recorded, not a lock


def test_switch_unknown_lane_errors():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        try:
            run_lane_switch_command(
                name="geomtry",
                run_id="run_lane",
                user_id="alice",
                store_dir=_store_dir(td),
            )
        except KeyError as exc:
            assert "unknown lane" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("expected KeyError")


def test_adopt_existing_record_into_lane():
    with tempfile.TemporaryDirectory() as td:
        init = _init(td)
        sd = _store_dir(td)
        lane = run_lane_create_command(
            name="geometry",
            run_id="run_lane",
            user_id="alice",
            store_dir=sd,
        )
        made = run_add_step_command(
            run_id="run_lane",
            input_node_ids=[init["root_node_id"]],
            title="old work",
            payload_kind=None,
            payload_type="step_payload",
            field_data={},
            json_data={},
            store_dir=sd,
            user_id=None,
            work_session_id=None,
        )
        step_id = made["step"]["step_id"]
        output_id = made["step"]["output_node_id"]

        adopted = run_lane_adopt_command(
            name="geometry",
            run_id="run_lane",
            user_id="bob",
            store_dir=sd,
            record_ids=[step_id, output_id],
        )

        assert adopted["lane_id"] == lane["lane_id"]
        assert adopted["count"] == 2
        handle = resolve_store(sd).load_run("run_lane")
        event = handle.run_graph.work_events[-1]
        assert event.event_type == "lane_adopted"
        assert event.data["record_ids"] == [step_id, output_id]


def test_validate_lane_run_reports_issues():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        sd = _store_dir(td)
        _seed_default_lane_node(sd)

        result = validate_lane_run(run_id="run_lane", store_dir=sd)

        assert result["ok"] is True
        assert any(
            issue["code"] == "default_lane_membership"
            for issue in result["issues"]
        )


def test_persistent_lane_pointer_is_scoped_by_run(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".git").mkdir()
        monkeypatch.chdir(root)
        monkeypatch.setenv("ARCTX_HOME", str(root / "home"))
        monkeypatch.delenv("ARCTX_LANE_ID", raising=False)
        monkeypatch.delenv("ARCTX_WORK_SESSION_ID", raising=False)

        sd = _store_dir(td)
        run_init_command(
            requirement_id="req",
            target_type="task",
            target_id="a",
            run_id="run_a",
            store_dir=sd,
        )
        run_init_command(
            requirement_id="req",
            target_type="task",
            target_id="b",
            run_id="run_b",
            store_dir=sd,
        )

        lane_a = run_lane_create_command(
            name="math",
            run_id="run_a",
            user_id="alice",
            store_dir=sd,
        )
        lane_b = run_lane_create_command(
            name="empirical",
            run_id="run_b",
            user_id="alice",
            store_dir=sd,
        )
        run_lane_switch_command(
            name="math",
            run_id="run_a",
            user_id="alice",
            store_dir=sd,
            shell=False,
        )
        run_lane_switch_command(
            name="empirical",
            run_id="run_b",
            user_id="alice",
            store_dir=sd,
            shell=False,
        )

        assert (
            resolve_work_session_id_from_args(Namespace(run="run_a", work_session=None))
            == lane_a["lane_id"]
        )
        assert (
            resolve_work_session_id_from_args(Namespace(run="run_b", work_session=None))
            == lane_b["lane_id"]
        )
