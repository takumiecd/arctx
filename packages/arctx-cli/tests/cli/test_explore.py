"""CLI coverage for summary-first Lane DAG exploration."""

from __future__ import annotations

from arctx_cli.commands.attach import run_attach_command
from arctx_cli.commands.explore import run_explore_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.lane import run_lane_create_command, run_lane_payload_command
from arctx_cli.main import main


def _init(tmp_path):
    store_dir = str(tmp_path / "runs")
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id="run_explore",
        store_dir=store_dir,
    )
    return store_dir


def test_explore_starts_at_roots_and_expands_one_level(tmp_path):
    store_dir = _init(tmp_path)
    parent = run_lane_create_command(
        name="research",
        summary="investigating authentication",
        purpose="choose an approach",
        run_id="run_explore",
        user_id="alice",
        store_dir=store_dir,
    )
    child = run_lane_create_command(
        name="oauth",
        summary="PKCE looks promising",
        parent_lane_ids=[parent["lane_id"]],
        run_id="run_explore",
        user_id="alice",
        store_dir=store_dir,
    )

    result = run_explore_command(
        run_id="run_explore", store_dir=store_dir, depth=1
    )

    assert [lane["lane_id"] for lane in result["lanes"]] == [parent["lane_id"]]
    assert result["lanes"][0]["children"][0]["lane_id"] == child["lane_id"]
    assert (
        result["lanes"][0]["children"][0]["current_values"]["summary"]["content"]["text"]
        == "PKCE looks promising"
    )


def test_lane_summary_update_is_projected_as_current(tmp_path):
    store_dir = _init(tmp_path)
    lane = run_lane_create_command(
        name="research",
        summary="starting",
        run_id="run_explore",
        user_id="alice",
        store_dir=store_dir,
    )
    run_lane_payload_command(
        name_or_id=lane["lane_id"],
        type="summary",
        text="current state",
        run_id="run_explore",
        user_id="alice",
        store_dir=store_dir,
    )

    item = run_explore_command(
        run_id="run_explore", store_dir=store_dir, depth=0
    )["lanes"][0]
    assert item["current_values"]["summary"]["content"]["text"] == "current state"


def test_public_lane_create_requires_summary(tmp_path, capsys):
    store_dir = _init(tmp_path)
    rc = main(
        ["lane", "create", "missing", "--run", "run_explore", "--store-dir", store_dir]
    )
    assert rc == 2
    assert "requires --summary" in capsys.readouterr().err


def test_generic_attach_resolves_lane_target(tmp_path):
    store_dir = _init(tmp_path)
    lane = run_lane_create_command(
        name="research",
        summary="starting",
        run_id="run_explore",
        user_id="alice",
        store_dir=store_dir,
    )
    attached = run_attach_command(
        run_id="run_explore",
        target_id=lane["lane_id"],
        payload_kind="decision",
        payload_type=None,
        field_data={"text": "use PKCE"},
        json_data={},
        store_dir=store_dir,
        user_id="alice",
    )

    assert attached["payload"]["target_kind"] == "lane"
    item = run_explore_command(
        run_id="run_explore", store_dir=store_dir, depth=0
    )["lanes"][0]
    assert item["collections"]["decision"][0]["content"]["text"] == "use PKCE"
