"""`arctx add --commit` records the step and the commit it stands for, together.

arctx does not make commits. The user does, then names the sha here. The point
of doing it in one command is that there is exactly one mechanism tracking lane
position -- `arctx add`'s. The removed `arctx git commit` had its own, and the
two went out of sync: a commit got made and not recorded, or recorded under the
wrong parent.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.context import resolve_store


def _repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (
        ["git", "init", "-q", "."],
        ["git", "config", "user.email", "a@b"],
        ["git", "config", "user.name", "a"],
    ):
        subprocess.run(cmd, cwd=str(repo), capture_output=True, check=True)
    return repo


def _commit(repo, text, message):
    (repo / "f.txt").write_text(text)
    subprocess.run(["git", "add", "f.txt"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", message], cwd=str(repo), capture_output=True, check=True
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()


def _init(tmp_path, monkeypatch):
    repo = _repo(tmp_path)
    monkeypatch.chdir(repo)
    store_dir = str(tmp_path / "home" / "runs")
    run_init_command(
        requirement_id="r",
        target_type="task",
        target_id="t",
        run_id="ac",
        store_dir=store_dir,
        extensions=["git"],
    )
    return repo, store_dir


def _add(store_dir, **kw):
    base = dict(
        run_id="ac",
        input_node_ids=None,
        title=None,
        payload_kind="commit",
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=store_dir,
        user_id="u",
        lane_id="L",
    )
    base.update(kw)
    return run_add_step_command(**base)


def test_add_commit_records_a_git_change_on_the_new_step(tmp_path, monkeypatch):
    repo, store_dir = _init(tmp_path, monkeypatch)
    sha = _commit(repo, "x\n", "baseline")

    result = _add(store_dir, title="baseline", commits=["HEAD"])
    step = result["step"]

    assert "git_change" in step
    handle = resolve_store(store_dir).load_run("ac")
    payloads = handle.run_graph.payloads_for_step(step["step_id"], payload_type="git_change")
    assert len(payloads) == 1
    assert payloads[0].head_commit == sha


def test_the_second_commit_chains_off_the_lane_frontier(tmp_path, monkeypatch):
    repo, store_dir = _init(tmp_path, monkeypatch)
    _commit(repo, "x\n", "baseline")
    first = _add(store_dir, title="baseline", commits=["HEAD"])["step"]
    _commit(repo, "x\ny\n", "second")
    second = _add(store_dir, title="second", commits=["HEAD"])["step"]

    # One mechanism: the second step takes its input from the first's output.
    assert second["input_node_ids"] == [first["output_node_id"]]


def test_add_without_commit_is_unchanged(tmp_path, monkeypatch):
    _repo_, store_dir = _init(tmp_path, monkeypatch)
    step = _add(store_dir, title="no git here")["step"]
    assert "git_change" not in step


def test_an_unresolvable_ref_is_refused(tmp_path, monkeypatch):
    repo, store_dir = _init(tmp_path, monkeypatch)
    _commit(repo, "x\n", "baseline")
    with pytest.raises((ValueError, KeyError)):
        _add(store_dir, title="bad", commits=["no-such-ref"])
