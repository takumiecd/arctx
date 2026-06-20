"""Tests for the ``lane`` CLI command (switch-by-name, open membership)."""

from __future__ import annotations

import tempfile
from argparse import Namespace
from pathlib import Path

from arctx_cli.context import resolve_work_session_id_from_args
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.lane import list_lanes, run_lane_switch_command


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


def test_switch_creates_named_lane_and_is_idempotent_by_name():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        sd = _store_dir(td)
        # alice switches to a new lane (shell mode: no git repo needed).
        r1 = run_lane_switch_command(
            name="geometry", run_id="run_lane", user_id="alice",
            store_dir=sd, shell=True,
        )
        assert r1["created"] is True
        assert r1["name"] == "geometry"
        assert r1["export"].startswith("export ARCTX_WORK_SESSION_ID=")

        # bob switches to the SAME named lane — open membership: resolves the
        # existing lane (not a new one), no error.
        r2 = run_lane_switch_command(
            name="geometry", run_id="run_lane", user_id="bob",
            store_dir=sd, shell=True,
        )
        assert r2["created"] is False
        assert r2["lane_id"] == r1["lane_id"]

        lanes = list_lanes(run_id="run_lane", store_dir=sd)
        assert len(lanes) == 1
        assert lanes[0]["name"] == "geometry"
        assert lanes[0]["created_by"] == "alice"  # creator recorded, not a lock


def test_persistent_lane_pointer_is_scoped_by_run(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / ".git").mkdir()
        monkeypatch.chdir(root)
        monkeypatch.setenv("ARCTX_HOME", str(root / "home"))
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

        lane_a = run_lane_switch_command(
            name="math",
            run_id="run_a",
            user_id="alice",
            store_dir=sd,
            shell=False,
        )
        lane_b = run_lane_switch_command(
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
