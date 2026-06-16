"""Tests for the ``lane`` CLI command (open membership, named lanes)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.lane import _list_lanes
from arctx_cli.commands.work_session import run_work_session_start_command


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


def test_open_named_lane_and_share_across_actors():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        # alice opens a named lane.
        run_work_session_start_command(
            run_id="run_lane",
            work_session_id="lane_s",
            user_id="alice",
            store_dir=_store_dir(td),
            name="mips-scd",
        )
        # bob opens the SAME lane — open membership, no error, no duplicate.
        run_work_session_start_command(
            run_id="run_lane",
            work_session_id="lane_s",
            user_id="bob",
            store_dir=_store_dir(td),
        )

        lanes = _list_lanes(run_id="run_lane", store_dir=_store_dir(td))
        assert len(lanes) == 1
        assert lanes[0]["lane_id"] == "lane_s"
        assert lanes[0]["name"] == "mips-scd"
        assert lanes[0]["created_by"] == "alice"  # creator recorded, not a lock
