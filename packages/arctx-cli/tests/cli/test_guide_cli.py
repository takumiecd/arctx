"""Tests for ``arctx guide``: lane resolution, --context, and fail-safe context errors."""

from __future__ import annotations

import json
from pathlib import Path

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.lane import run_lane_create_command, run_lane_switch_command
from arctx_cli.main import main


def _fake_git_repo(tmp_path: Path) -> Path:
    (tmp_path / ".git").mkdir()
    return tmp_path


def _arctx_home(tmp_path: Path) -> Path:
    return tmp_path / "arctx_home"


def _store_dir(tmp_path: Path) -> str:
    return str(_arctx_home(tmp_path) / "runs")


def _init(tmp_path: Path, run_id: str = "run_guide") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
    )


def test_guide_context_flag_omits_static_text(tmp_path, monkeypatch, capsys):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
    monkeypatch.chdir(repo)
    _init(tmp_path)

    rc = main(["guide", "--context", "--run", "run_guide", "--store-dir", _store_dir(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "## Current Context" in out
    assert "Run ID" in out
    assert "Current Lane" in out
    # Static guide sections must not appear in --context output.
    assert "# arctx Guide" not in out
    assert "Recommended Workflow" not in out
    assert "Parallel Experiment Strategy" not in out


def test_guide_full_output_still_includes_context(tmp_path, monkeypatch, capsys):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
    monkeypatch.chdir(repo)
    _init(tmp_path)

    rc = main(["guide", "--run", "run_guide", "--store-dir", _store_dir(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# arctx Guide" in out
    assert "## Current Context" in out
    assert "guide --context" in out  # static text mentions the new flag
    # The guide teaches the shared grammar plus the writing and reading sides.
    assert "One grammar, three bundles" in out
    assert "## Writing" in out
    assert "## Reading" in out
    for command in ("arctx lane create", "arctx add", "arctx lane close"):
        assert command in out
    for command in ("arctx explore --query", "arctx dump", "arctx show"):
        assert command in out
    assert "arctx reparent" in out
    assert "arctx lane summarize" in out


def test_guide_does_not_mention_deleted_surface(tmp_path, monkeypatch, capsys):
    """Hierarchy and custom sync are gone; the guide must not teach them."""
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
    monkeypatch.chdir(repo)
    _init(tmp_path)

    rc = main(["guide", "--run", "run_guide", "--store-dir", _store_dir(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    for gone in (
        "lane link",
        "lane unlink",
        "lane adopt",
        "arctx sync",
        "parent lane",
        "copy-assets",
        "ancestor",
    ):
        assert gone not in out, f"guide still references removed surface: {gone!r}"


def test_guide_context_reports_lane_purpose_and_current_summary(
    tmp_path, monkeypatch, capsys
):
    from arctx_cli.commands.lane import run_lane_summarize_command

    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
    monkeypatch.chdir(repo)
    init = _init(tmp_path)
    sd = _store_dir(tmp_path)

    lane = run_lane_create_command(
        name="work",
        run_id="run_guide",
        user_id="alice",
        store_dir=sd,
        purpose="find the slow kernel",
    )
    run_add_step_command(
        run_id="run_guide",
        input_node_ids=[init["root_node_id"]],
        title="s1",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=sd,
        user_id="alice",
        lane_id=lane["lane_id"],
    )
    run_lane_summarize_command(
        name_or_id="work",
        summary="Narrowed it to the reduction.\nMore detail below.",
        node_ids=None,
        run_id="run_guide",
        user_id="alice",
        store_dir=sd,
    )

    rc = main(
        ["guide", "--context", "--run", "run_guide", "--store-dir", sd, "--lane", "work"]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "`work` [open]" in out
    assert "purpose: find the slow kernel" in out
    # Collapsed to one line: the full text is one `arctx explore work` away.
    assert "current summary: Narrowed it to the reduction." in out
    assert "More detail below." not in out


def test_guide_context_omits_status_for_the_implicit_default_lane(
    tmp_path, monkeypatch, capsys
):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
    monkeypatch.chdir(repo)
    _init(tmp_path)

    rc = main(["guide", "--context", "--run", "run_guide", "--store-dir", _store_dir(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "**Current Lane**: `default`" in out
    assert "[unknown]" not in out


def test_guide_honors_arctx_lane_id_env_over_repo_pointer(tmp_path, monkeypatch, capsys):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
    monkeypatch.chdir(repo)
    _init(tmp_path)
    sd = _store_dir(tmp_path)

    lane_a = run_lane_create_command(
        name="lane-a", run_id="run_guide", user_id="alice", store_dir=sd
    )
    lane_b = run_lane_create_command(
        name="lane-b", run_id="run_guide", user_id="alice", store_dir=sd
    )
    # Persistent pointer -> lane-a.
    run_lane_switch_command(
        name="lane-a", run_id="run_guide", user_id="alice", store_dir=sd, shell=False
    )

    # A spawned child process gets ARCTX_LANE_ID=lane-b in its env; guide
    # must prefer that over the repo pointer.
    monkeypatch.setenv("ARCTX_LANE_ID", lane_b["lane_id"])
    rc = main(["guide", "--context", "--run", "run_guide", "--store-dir", sd])
    assert rc == 0
    out = capsys.readouterr().out
    assert "lane-b" in out
    assert "lane-a" not in out


def test_guide_reports_context_unavailable_note_without_crashing(tmp_path, monkeypatch, capsys):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
    monkeypatch.chdir(repo)
    _init(tmp_path)
    sd = _store_dir(tmp_path)

    # Corrupt the store so loading the run raises partway through.
    nodes_file = Path(sd) / "run_guide" / "nodes.jsonl"
    with nodes_file.open("a", encoding="utf-8") as fh:
        fh.write("not valid json{{{\n")

    rc = main(["guide", "--run", "run_guide", "--store-dir", sd])
    assert rc == 0  # fail-safe: guide never exits non-zero on broken context
    out = capsys.readouterr().out
    assert "context unavailable" in out
    # The note has to carry enough to act on. It used to be a bare
    # "JSONDecodeError"; now it names the file and points at the repair.
    assert "nodes.jsonl" in out
    assert "arctx doctor" in out


def test_guide_active_frontiers_listed_for_lane(tmp_path, monkeypatch, capsys):
    repo = _fake_git_repo(tmp_path)
    monkeypatch.setenv("ARCTX_HOME", str(_arctx_home(tmp_path)))
    monkeypatch.chdir(repo)
    init = _init(tmp_path)
    sd = _store_dir(tmp_path)

    lane = run_lane_create_command(
        name="work", run_id="run_guide", user_id="alice", store_dir=sd
    )
    step = run_add_step_command(
        run_id="run_guide",
        input_node_ids=[init["root_node_id"]],
        title="s1",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=sd,
        user_id="alice",
        lane_id=lane["lane_id"],
    )["step"]

    rc = main(
        [
            "guide", "--context",
            "--run", "run_guide", "--store-dir", sd, "--lane", lane["lane_id"],
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert step["output_node_id"] in out
    assert "Active Frontiers in Lane" in out
