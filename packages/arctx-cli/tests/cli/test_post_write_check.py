"""Tests for the shared post-write lane-consistency check.

``warn_if_invalid`` runs after write commands succeed (see ``arctx_cli.
post_write_check``). It is deliberately read-only and non-blocking by
default; ``ARCTX_VALIDATE`` controls strictness.
"""

from __future__ import annotations

from pathlib import Path

import arctx.core.lanes as lanes_module
from arctx.core.lanes import LaneValidationIssue

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.lane import run_lane_create_command
from arctx_cli.context import resolve_store
from arctx_cli.post_write_check import warn_if_invalid


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init(td: str, run_id: str = "run_pwc") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(td),
    )


def _seed_step(sd: str, run_id: str, parent: str) -> None:
    """Add one step in a proper (non-default) lane — no validation issues."""
    lane = run_lane_create_command(
        name="work", run_id=run_id, user_id="alice", store_dir=sd
    )
    run_add_step_command(
        run_id=run_id,
        input_node_ids=[parent],
        title="s1",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=sd,
        user_id="alice",
        lane_id=lane["lane_id"],
    )


def test_warn_if_invalid_no_issues_is_silent(tmp_path, capsys):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    _seed_step(sd, "run_pwc", init["root_node_id"])

    store = resolve_store(sd)
    handle = store.load_run("run_pwc")

    rc = warn_if_invalid(handle, sd, command_name="add")

    assert rc == 0
    captured = capsys.readouterr()
    assert captured.err == ""


def test_warn_if_invalid_accepts_run_id_string(tmp_path, capsys):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    _seed_step(sd, "run_pwc", init["root_node_id"])

    rc = warn_if_invalid("run_pwc", sd, command_name="add")

    assert rc == 0
    assert capsys.readouterr().err == ""


def test_warn_if_invalid_reports_issues_on_stderr(tmp_path, capsys, monkeypatch):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    _seed_step(sd, "run_pwc", init["root_node_id"])

    fake_issues = (
        LaneValidationIssue(
            code="fake_issue",
            severity="warning",
            message="something looks off",
        ),
    )
    monkeypatch.setattr(lanes_module, "validate_lanes", lambda *a, **k: fake_issues)

    rc = warn_if_invalid("run_pwc", sd, command_name="add")

    assert rc == 0  # default mode never fails the exit code
    err = capsys.readouterr().err
    assert "arctx: warning: run 'run_pwc' has 1 consistency issue(s) after add:" in err
    assert "fake_issue: something looks off" in err
    assert "hint: run 'arctx lane validate' for details" in err
    # `lane adopt` is gone; membership is constructive, so the hint points at
    # switching lanes, re-parenting, or cutting instead.
    assert "arctx lane adopt" not in err
    for fix in ("arctx lane switch <LANE>", "arctx reparent", "arctx cut <ID>"):
        assert fix in err


def test_warn_if_invalid_skips_when_validate_off(tmp_path, capsys, monkeypatch):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    _seed_step(sd, "run_pwc", init["root_node_id"])

    def _boom(*_a, **_k):
        raise AssertionError("validate_lanes must not run when ARCTX_VALIDATE=off")

    monkeypatch.setattr(lanes_module, "validate_lanes", _boom)
    monkeypatch.setenv("ARCTX_VALIDATE", "off")

    rc = warn_if_invalid("run_pwc", sd, command_name="add")

    assert rc == 0
    assert capsys.readouterr().err == ""


def test_warn_if_invalid_strict_mode_returns_nonzero(tmp_path, capsys, monkeypatch):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    _seed_step(sd, "run_pwc", init["root_node_id"])

    fake_issues = (
        LaneValidationIssue(code="a", severity="error", message="m1"),
        LaneValidationIssue(code="b", severity="warning", message="m2"),
    )
    monkeypatch.setattr(lanes_module, "validate_lanes", lambda *a, **k: fake_issues)
    monkeypatch.setenv("ARCTX_VALIDATE", "strict")

    rc = warn_if_invalid("run_pwc", sd, command_name="cut")

    assert rc == 2
    assert "has 2 consistency issue(s) after cut" in capsys.readouterr().err


def test_warn_if_invalid_swallows_validation_exceptions(tmp_path, capsys, monkeypatch):
    td = str(tmp_path)
    init = _init(td)
    sd = _store_dir(td)
    _seed_step(sd, "run_pwc", init["root_node_id"])

    def _boom(*_a, **_k):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(lanes_module, "validate_lanes", _boom)

    rc = warn_if_invalid("run_pwc", sd, command_name="add")

    assert rc == 0
    err = capsys.readouterr().err
    assert "arctx: warning: post-write validation failed: kaboom" in err
