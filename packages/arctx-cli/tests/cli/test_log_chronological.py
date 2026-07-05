"""Tests for the chronological ``arctx log`` view (work-event driven).

Covers: default chronological order, ``--lanes`` phase timeline, ``--outline``
passthrough to the previous dump-based view, and the no-work-events fallback
for runs written without lane/user attribution (older data or writes that
never passed ``user_id``/``lane_id``).
"""

from __future__ import annotations

from pathlib import Path

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.attach import run_attach_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.lane import run_lane_close_command, run_lane_create_command
from arctx_cli.commands.log import run_log_command


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init(td: str, run_id: str = "run_log") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(td),
    )


def _add_step(td: str, run_id: str, parent: str, title: str, *, user_id=None, lane_id=None) -> dict:
    return run_add_step_command(
        run_id=run_id,
        input_node_ids=[parent],
        title=title,
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=_store_dir(td),
        user_id=user_id,
        lane_id=lane_id,
    )["step"]


def test_chronological_log_is_oldest_first_with_titles(tmp_path):
    td = str(tmp_path)
    run_id = "run_log"
    init = _init(td, run_id)
    lane = run_lane_create_command(
        name="phase-a", run_id=run_id, user_id="alice", store_dir=_store_dir(td)
    )
    lane_id = lane["lane_id"]

    n1 = _add_step(
        td, run_id, init["root_node_id"], "first idea", user_id="alice", lane_id=lane_id
    )["output_node_id"]
    _add_step(td, run_id, n1, "second idea", user_id="alice", lane_id=lane_id)

    result = run_log_command(
        run_id=run_id,
        from_node_id=None,
        to_node_id=None,
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
    )
    log_text = result["log"]
    first_pos = log_text.index("first idea")
    second_pos = log_text.index("second idea")
    assert first_pos < second_pos, "chronological log must list events oldest first"
    assert "phase-a" in log_text
    assert "alice" in log_text


def test_chronological_log_reverse_and_limit(tmp_path):
    td = str(tmp_path)
    run_id = "run_log"
    init = _init(td, run_id)
    lane = run_lane_create_command(
        name="phase-a", run_id=run_id, user_id="alice", store_dir=_store_dir(td)
    )
    lane_id = lane["lane_id"]

    n1 = _add_step(
        td, run_id, init["root_node_id"], "first idea", user_id="alice", lane_id=lane_id
    )["output_node_id"]
    _add_step(td, run_id, n1, "second idea", user_id="alice", lane_id=lane_id)

    result = run_log_command(
        run_id=run_id,
        from_node_id=None,
        to_node_id=None,
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
        reverse=True,
    )
    log_text = result["log"]
    first_pos = log_text.index("first idea")
    second_pos = log_text.index("second idea")
    assert second_pos < first_pos, "--reverse must list events newest first"

    limited = run_log_command(
        run_id=run_id,
        from_node_id=None,
        to_node_id=None,
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
        limit=1,
    )["log"]
    assert "first idea" in limited
    assert "second idea" not in limited


def test_log_lanes_shows_phase_timeline_with_close_summary(tmp_path):
    td = str(tmp_path)
    run_id = "run_log"
    init = _init(td, run_id)
    lane = run_lane_create_command(
        name="phase-a", run_id=run_id, user_id="alice", store_dir=_store_dir(td)
    )
    lane_id = lane["lane_id"]
    _add_step(
        td, run_id, init["root_node_id"], "only step", user_id="alice", lane_id=lane_id
    )
    run_lane_close_command(
        name_or_id="phase-a",
        summary="phase-a concluded: it worked",
        node_ids=None,
        reason=None,
        run_id=run_id,
        user_id="alice",
        store_dir=_store_dir(td),
    )
    run_lane_create_command(
        name="phase-b", run_id=run_id, user_id="alice", store_dir=_store_dir(td)
    )

    result = run_log_command(
        run_id=run_id,
        from_node_id=None,
        to_node_id=None,
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
        lanes=True,
    )
    log_text = result["log"]
    assert "phase-a" in log_text
    assert "phase-a concluded" in log_text
    assert "phase-b" in log_text
    assert "open" in log_text
    assert "lanes=2" in log_text


def test_log_outline_passthrough_matches_previous_dump_view(tmp_path):
    td = str(tmp_path)
    run_id = "run_log"
    init = _init(td, run_id)
    _add_step(td, run_id, init["root_node_id"], "try cache")

    outline_result = run_log_command(
        run_id=run_id,
        from_node_id=None,
        to_node_id=None,
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
        outline=True,
    )
    assert "try cache" in outline_result["log"]
    assert "nodes=" in outline_result["log"]

    # --from still routes to the outline view even without --outline, since a
    # node-scoped view only makes sense as a spanning-tree walk.
    from_result = run_log_command(
        run_id=run_id,
        from_node_id=init["root_node_id"],
        to_node_id=None,
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
    )
    assert "try cache" in from_result["log"]


def test_log_to_still_returns_trace_history(tmp_path):
    td = str(tmp_path)
    run_id = "run_log"
    init = _init(td, run_id)
    step = _add_step(td, run_id, init["root_node_id"], "try cache")

    result = run_log_command(
        run_id=run_id,
        from_node_id=None,
        to_node_id=step["output_node_id"],
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
    )
    assert result["history"]["current_node_id"] == step["output_node_id"]
    assert init["root_node_id"] in result["history"]["past_node_ids"]


def test_chronological_log_falls_back_without_work_events(tmp_path):
    """Records added without user_id/lane_id create no WorkEvent rows.

    ``record_work_event`` is a no-op unless both ``user_id`` and ``lane_id``
    are given (see ``RunHandle.record_work_event``), so this reproduces the
    "older run with no chronology" case without needing to hand-craft a
    pre-work-event storage fixture.
    """
    td = str(tmp_path)
    run_id = "run_log"
    init = _init(td, run_id)
    _add_step(td, run_id, init["root_node_id"], "untracked step")

    result = run_log_command(
        run_id=run_id,
        from_node_id=None,
        to_node_id=None,
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
    )
    log_text = result["log"]
    assert "no work events recorded" in log_text
    assert "untracked step" in log_text
