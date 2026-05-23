"""Tests for stag git start / finish / status / diff / log commands.

Each test spins up a real git repository in a tmp_path fixture.
The JsonlRunStore is always placed inside <tmp_path>/runs/.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from stag.cli.commands.init import run_init_command
from stag.cli.commands.observe import run_observe_command
from stag.cli.commands.plan import run_plan_command
from stag.cli.commands.predict import run_predict_command
from stag.core.git.attach import attach_commits_to_output_transition
from stag.core.git.finish import git_finish_form_a, git_finish_form_b
from stag.core.git.session import (
    list_sessions,
    load_current_pointer,
    load_session,
    save_current_pointer,
    save_session,
)
from stag.core.git.start import git_start
from stag.core.schema.payloads import GitChangePayload
from stag.storage.jsonl import JsonlRunStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def git_repo(tmp_path):
    """Create a minimal git repository and return its root path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "symbolic-ref", "HEAD", "refs/heads/main"],
        cwd=str(repo), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=str(repo), check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=str(repo), check=True, capture_output=True,
    )
    # Initial commit so HEAD exists
    (repo / "README.md").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=str(repo), check=True, capture_output=True,
    )
    return repo


@pytest.fixture()
def stag_env(tmp_path, git_repo, monkeypatch):
    """Return (store_dir, run_id, run_dir, handle) with a plan ready to use.

    Monkeypatches CWD to git_repo so repo detection works without
    passing explicit repo_root_hint.
    """
    monkeypatch.chdir(git_repo)

    store_dir = str(tmp_path / "runs")
    run_id = "run_test"
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id=run_id,
        store_dir=store_dir,
    )
    it_id = run_plan_command(
        run_id=run_id,
        input_node_ids=["n_0000"],
        action_type="analysis",
        intent="do stuff",
        store_dir=store_dir,
    )["input_transition"]["input_transition_id"]

    store = JsonlRunStore(store_dir)
    handle = store.load_run(run_id)
    run_dir = store.run_path(run_id)

    return store_dir, run_id, run_dir, handle, it_id


def _make_commit(repo: Path, filename: str = "change.txt", msg: str = "a commit") -> str:
    """Write a file and commit; return the new HEAD sha."""
    (repo / filename).write_text("change", encoding="utf-8")
    subprocess.run(["git", "add", filename], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", msg], cwd=str(repo), check=True, capture_output=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# git start — golden path
# ---------------------------------------------------------------------------

def test_git_start_golden_path(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env

    result = git_start(handle, run_dir, it_id, user_id="alice")

    assert result["input_transition_id"] == it_id
    assert result["dirty"] is False
    assert result["warnings"] == []
    session_id = result["session_id"]
    assert session_id.startswith("gs_")

    # Session file written
    session = load_session(session_id, run_dir)
    assert session.input_transition_id == it_id
    assert session.started_by == "alice"
    assert session.is_open

    # current.json points to new session
    assert load_current_pointer(run_dir) == session_id


# ---------------------------------------------------------------------------
# git start — detached HEAD error
# ---------------------------------------------------------------------------

def test_git_start_detached_head_error(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    # Put repo into detached HEAD
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(git_repo), capture_output=True, text=True
    ).stdout.strip()
    subprocess.run(["git", "checkout", sha], cwd=str(git_repo), check=True, capture_output=True)

    with pytest.raises(ValueError, match="detached"):
        git_start(handle, run_dir, it_id, user_id="alice")


# ---------------------------------------------------------------------------
# git start — unknown IT error
# ---------------------------------------------------------------------------

def test_git_start_unknown_it_error(stag_env):
    store_dir, run_id, run_dir, handle, it_id = stag_env

    with pytest.raises(KeyError):
        git_start(handle, run_dir, "it_9999", user_id="alice")


# ---------------------------------------------------------------------------
# git start — cut IT error
# ---------------------------------------------------------------------------

def test_git_start_cut_it_error(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env

    store = JsonlRunStore(store_dir)
    # Cut the IT via the cut API
    handle.cut(it_id, target_kind="input_transition", reason="test")
    store.save_run(handle)

    # Reload handle from disk to get fresh state
    fresh_handle = store.load_run(run_id)
    with pytest.raises(ValueError, match="inactive"):
        git_start(fresh_handle, run_dir, it_id, user_id="alice")


# ---------------------------------------------------------------------------
# git start — dirty working tree warning
# ---------------------------------------------------------------------------

def test_git_start_dirty_warning(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    # Make the repo dirty (tracked file modified but not committed)
    (git_repo / "README.md").write_text("modified", encoding="utf-8")

    result = git_start(handle, run_dir, it_id, user_id="alice")
    assert result["dirty"] is True
    assert any("dirty" in w.lower() or "uncommitted" in w.lower() for w in result["warnings"])


# ---------------------------------------------------------------------------
# git finish form A — golden path
# ---------------------------------------------------------------------------

def test_git_finish_form_a_golden_path(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    # Start
    start_result = git_start(handle, run_dir, it_id, user_id="alice")
    session_id = start_result["session_id"]
    store.save_run(handle)

    # Make a commit in the repo
    _make_commit(git_repo, "feature.py", "Add feature")

    # Reload handle (counters updated on disk by save_run)
    handle = store.load_run(run_id)

    result = git_finish_form_a(
        handle,
        run_dir,
        session_id,
        status="completed",
        summary="Feature done",
        user_id="alice",
    )

    assert "output_transition_id" in result["created"]
    assert result["created"]["git_change_payload_id"].startswith("pl_")
    assert result["git"]["commits"] == 1
    assert result["git"]["files_changed"] == 1

    store.save_run(handle)

    # Verify payload in loaded handle
    fresh = store.load_run(run_id)
    ot_id = result["created"]["output_transition_id"]
    gcps = fresh.run_graph.payloads_for_output_transition(ot_id, payload_type="git_change")
    assert len(gcps) == 1
    gcp = gcps[0]
    assert isinstance(gcp, GitChangePayload)
    assert gcp.branch == "main"
    assert len(gcp.commits) == 1
    assert len(gcp.commit_log) == 1
    assert gcp.patch_artifact is not None

    # Session should be closed
    session = load_session(session_id, run_dir)
    assert not session.is_open
    assert session.output_transition_id == ot_id

    # current.json should be cleared
    assert load_current_pointer(run_dir) is None


# ---------------------------------------------------------------------------
# git attach — explicit commit list
# ---------------------------------------------------------------------------

def test_git_attach_commits_to_existing_output_transition(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    ot = run_observe_command(
        run_id=run_id,
        input_transition_id=it_id,
        status="completed",
        artifacts=None,
        raw_outputs=None,
        logs=None,
        metrics=None,
        errors=None,
        store_dir=store_dir,
    )["output_transition"]
    commit = _make_commit(git_repo, "explicit.py", "Explicit commit")

    handle = store.load_run(run_id)
    result = attach_commits_to_output_transition(
        handle,
        run_dir,
        ot["output_transition_id"],
        (commit[:8],),
        user_id="alice",
    )
    assert result["linked"]["output_transition_id"] == ot["output_transition_id"]
    assert result["git"]["commits"] == [commit]
    assert result["git"]["files_changed"] == 1
    store.save_run(handle)

    fresh = store.load_run(run_id)
    gcps = fresh.run_graph.payloads_for_output_transition(
        ot["output_transition_id"], payload_type="git_change"
    )
    assert len(gcps) == 1
    gcp = gcps[0]
    assert isinstance(gcp, GitChangePayload)
    assert gcp.commits == (commit,)
    assert len(gcp.commit_log) == 1
    assert gcp.commit_log[0].sha == commit
    assert gcp.metadata["attached_by"] == "alice"
    assert gcp.patch_artifact is not None


# ---------------------------------------------------------------------------
# git finish form A — with matched-prediction
# ---------------------------------------------------------------------------

def test_git_finish_form_a_matched_prediction(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    # Create a prediction first
    from stag.cli.commands.predict import run_predict_command
    pred_result = run_predict_command(
        run_id=run_id,
        input_transition_id=it_id,
        max_outcomes=1,
        store_dir=store_dir,
    )
    pred_ot_id = pred_result["output_transitions"][0]["output_transition_id"]

    handle = store.load_run(run_id)
    start_result = git_start(handle, run_dir, it_id, user_id="alice")
    session_id = start_result["session_id"]
    store.save_run(handle)

    _make_commit(git_repo, "pred_feature.py", "Add predicted feature")
    handle = store.load_run(run_id)

    result = git_finish_form_a(
        handle,
        run_dir,
        session_id,
        status="completed",
        matched_prediction_output_id=pred_ot_id,
        user_id="alice",
    )

    assert result["linked"]["matched_prediction_output_id"] == pred_ot_id
    store.save_run(handle)


# ---------------------------------------------------------------------------
# git finish form A — duplicate observation warning
# ---------------------------------------------------------------------------

def test_git_finish_form_a_duplicate_observation_warning(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    # First observe (without git session)
    run_observe_command(
        run_id=run_id,
        input_transition_id=it_id,
        status="completed",
        artifacts=None, raw_outputs=None, logs=None, metrics=None, errors=None,
        store_dir=store_dir,
    )

    handle = store.load_run(run_id)
    start_result = git_start(handle, run_dir, it_id, user_id="alice")
    session_id = start_result["session_id"]
    store.save_run(handle)

    _make_commit(git_repo)
    handle = store.load_run(run_id)

    result = git_finish_form_a(handle, run_dir, session_id, user_id="alice")
    assert any("already has observed" in w or "already" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# git finish form B — golden path
# ---------------------------------------------------------------------------

def test_git_finish_form_b_golden_path(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    # Start session
    start_result = git_start(handle, run_dir, it_id, user_id="alice")
    session_id = start_result["session_id"]
    store.save_run(handle)

    # Observe separately
    obs = run_observe_command(
        run_id=run_id,
        input_transition_id=it_id,
        status="completed",
        artifacts=None, raw_outputs=None, logs=None, metrics=None, errors=None,
        store_dir=store_dir,
    )
    ot_id = obs["output_transition"]["output_transition_id"]

    _make_commit(git_repo)
    handle = store.load_run(run_id)

    result = git_finish_form_b(
        handle,
        run_dir,
        session_id,
        output_transition_id=ot_id,
        user_id="alice",
    )

    assert result["created"]["git_change_payload_id"].startswith("pl_")
    assert result["created"]["output_transition_id"] is None

    store.save_run(handle)
    fresh = store.load_run(run_id)
    gcps = fresh.run_graph.payloads_for_output_transition(ot_id, payload_type="git_change")
    assert len(gcps) == 1


# ---------------------------------------------------------------------------
# git finish form B — duplicate GitChangePayload warning
# ---------------------------------------------------------------------------

def test_git_finish_form_b_duplicate_gcp_warning(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    # Observe
    obs = run_observe_command(
        run_id=run_id,
        input_transition_id=it_id,
        status="completed",
        artifacts=None, raw_outputs=None, logs=None, metrics=None, errors=None,
        store_dir=store_dir,
    )
    ot_id = obs["output_transition"]["output_transition_id"]
    _make_commit(git_repo)

    # First git session and finish
    handle = store.load_run(run_id)
    s1 = git_start(handle, run_dir, it_id, user_id="alice")
    store.save_run(handle)
    handle = store.load_run(run_id)
    git_finish_form_b(handle, run_dir, s1["session_id"], output_transition_id=ot_id)
    store.save_run(handle)

    # Second git session and finish (duplicate GCP)
    _make_commit(git_repo, "extra.txt", "extra commit")
    handle = store.load_run(run_id)
    s2 = git_start(handle, run_dir, it_id, user_id="alice")
    store.save_run(handle)
    handle = store.load_run(run_id)
    result = git_finish_form_b(handle, run_dir, s2["session_id"], output_transition_id=ot_id)

    assert any("already has" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# git finish — branch switch error
# ---------------------------------------------------------------------------

def test_git_finish_branch_switch_error(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    start_result = git_start(handle, run_dir, it_id, user_id="alice")
    session_id = start_result["session_id"]
    store.save_run(handle)

    # Switch branch
    subprocess.run(
        ["git", "checkout", "-b", "other"],
        cwd=str(git_repo), check=True, capture_output=True,
    )

    handle = store.load_run(run_id)
    with pytest.raises(ValueError, match="branch"):
        git_finish_form_a(handle, run_dir, session_id, user_id="alice")


# ---------------------------------------------------------------------------
# git finish — dirty working tree error
# ---------------------------------------------------------------------------

def test_git_finish_dirty_error(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    start_result = git_start(handle, run_dir, it_id, user_id="alice")
    session_id = start_result["session_id"]
    store.save_run(handle)

    # Make repo dirty (tracked file)
    (git_repo / "README.md").write_text("dirty!", encoding="utf-8")

    handle = store.load_run(run_id)
    with pytest.raises(ValueError, match="dirty|tracked"):
        git_finish_form_a(handle, run_dir, session_id, user_id="alice")


# ---------------------------------------------------------------------------
# git finish — untracked files are OK
# ---------------------------------------------------------------------------

def test_git_finish_untracked_files_allowed(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    start_result = git_start(handle, run_dir, it_id, user_id="alice")
    session_id = start_result["session_id"]
    store.save_run(handle)

    _make_commit(git_repo, "feature.py")
    # Add an untracked file (not staged)
    (git_repo / "untracked.txt").write_text("untracked", encoding="utf-8")

    handle = store.load_run(run_id)
    # Should not raise
    result = git_finish_form_a(handle, run_dir, session_id, user_id="alice")
    assert result["created"]["output_transition_id"] is not None


# ---------------------------------------------------------------------------
# empty diff warning
# ---------------------------------------------------------------------------

def test_git_finish_empty_diff_warning(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    start_result = git_start(handle, run_dir, it_id, user_id="alice")
    session_id = start_result["session_id"]
    store.save_run(handle)

    # No commits between start and finish → empty diff
    handle = store.load_run(run_id)
    result = git_finish_form_a(handle, run_dir, session_id, user_id="alice")
    assert any("empty" in w.lower() or "no commits" in w.lower() for w in result["warnings"])


# ---------------------------------------------------------------------------
# parallel session warning
# ---------------------------------------------------------------------------

def test_git_start_parallel_session_warning(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    # First session
    s1 = git_start(handle, run_dir, it_id, user_id="alice")
    store.save_run(handle)

    # Second session on same IT
    handle = store.load_run(run_id)
    s2 = git_start(handle, run_dir, it_id, user_id="alice")
    assert any("open GitSession" in w or "parallel" in w.lower() for w in s2["warnings"])


# ---------------------------------------------------------------------------
# current.json cleanup
# ---------------------------------------------------------------------------

def test_git_finish_clears_current_pointer(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    start_result = git_start(handle, run_dir, it_id, user_id="alice")
    session_id = start_result["session_id"]
    store.save_run(handle)

    assert load_current_pointer(run_dir) == session_id

    _make_commit(git_repo)
    handle = store.load_run(run_id)
    git_finish_form_a(handle, run_dir, session_id, user_id="alice")

    assert load_current_pointer(run_dir) is None


def test_git_finish_does_not_clear_different_current_pointer(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    s1 = git_start(handle, run_dir, it_id, user_id="alice")
    session_id_1 = s1["session_id"]
    store.save_run(handle)

    handle = store.load_run(run_id)
    s2 = git_start(handle, run_dir, it_id, user_id="alice")
    session_id_2 = s2["session_id"]
    store.save_run(handle)

    # current.json points to s2 (the last started)
    assert load_current_pointer(run_dir) == session_id_2

    _make_commit(git_repo)
    handle = store.load_run(run_id)
    # Finish s1 (not the current pointer)
    git_finish_form_a(handle, run_dir, session_id_1, user_id="alice")

    # current.json should still point to s2
    assert load_current_pointer(run_dir) == session_id_2


# ---------------------------------------------------------------------------
# form B — matched-prediction reject
# ---------------------------------------------------------------------------

def test_git_finish_cli_form_b_rejects_matched_prediction(stag_env, git_repo, capsys):
    """form B via CLI must reject --matched-prediction."""
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    obs = run_observe_command(
        run_id=run_id,
        input_transition_id=it_id,
        status="completed",
        artifacts=None, raw_outputs=None, logs=None, metrics=None, errors=None,
        store_dir=store_dir,
    )
    ot_id = obs["output_transition"]["output_transition_id"]

    handle = store.load_run(run_id)
    s1 = git_start(handle, run_dir, it_id)
    store.save_run(handle)
    _make_commit(git_repo)

    # The CLI layer enforces rejection of --matched-prediction in form B
    from stag.cli.main import main as cli_main
    import sys

    ret = cli_main([
        "git", "finish", s1["session_id"],
        "--output-transition", ot_id,
        "--matched-prediction", "ot_9999",
        "--run", run_id,
        "--store-dir", store_dir,
    ])
    assert ret != 0
    captured = capsys.readouterr()
    assert "--matched-prediction" in captured.err


# ---------------------------------------------------------------------------
# form B — ResultPayload 変更系 options reject
# ---------------------------------------------------------------------------

def test_git_finish_cli_form_b_rejects_status_option(stag_env, git_repo, capsys):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    obs = run_observe_command(
        run_id=run_id,
        input_transition_id=it_id,
        status="completed",
        artifacts=None, raw_outputs=None, logs=None, metrics=None, errors=None,
        store_dir=store_dir,
    )
    ot_id = obs["output_transition"]["output_transition_id"]

    handle = store.load_run(run_id)
    s1 = git_start(handle, run_dir, it_id)
    store.save_run(handle)
    _make_commit(git_repo)

    from stag.cli.main import main as cli_main

    ret = cli_main([
        "git", "finish", s1["session_id"],
        "--output-transition", ot_id,
        "--status", "failed",  # form B should reject this
        "--run", run_id,
        "--store-dir", store_dir,
    ])
    assert ret != 0
    captured = capsys.readouterr()
    assert "--status" in captured.err


# ---------------------------------------------------------------------------
# form B — Prediction-only OT reject
# ---------------------------------------------------------------------------

def test_git_finish_form_b_rejects_prediction_only_ot(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    # Create prediction OT
    from stag.cli.commands.predict import run_predict_command
    pred_result = run_predict_command(
        run_id=run_id,
        input_transition_id=it_id,
        max_outcomes=1,
        store_dir=store_dir,
    )
    pred_ot_id = pred_result["output_transitions"][0]["output_transition_id"]

    handle = store.load_run(run_id)
    s1 = git_start(handle, run_dir, it_id)
    store.save_run(handle)
    _make_commit(git_repo)
    handle = store.load_run(run_id)

    with pytest.raises(ValueError, match="ResultPayload|result"):
        git_finish_form_b(handle, run_dir, s1["session_id"], output_transition_id=pred_ot_id)


# ---------------------------------------------------------------------------
# form B — OT belongs to different IT
# ---------------------------------------------------------------------------

def test_git_finish_form_b_rejects_wrong_it(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    # Create a second plan + observe
    it2_id = run_plan_command(
        run_id=run_id,
        input_node_ids=["n_0000"],
        action_type="analysis",
        intent="second plan",
        store_dir=store_dir,
    )["input_transition"]["input_transition_id"]
    obs2 = run_observe_command(
        run_id=run_id,
        input_transition_id=it2_id,
        status="completed",
        artifacts=None, raw_outputs=None, logs=None, metrics=None, errors=None,
        store_dir=store_dir,
    )
    ot2_id = obs2["output_transition"]["output_transition_id"]

    handle = store.load_run(run_id)
    s1 = git_start(handle, run_dir, it_id)  # session is on it_id
    store.save_run(handle)
    _make_commit(git_repo)
    handle = store.load_run(run_id)

    with pytest.raises(ValueError, match="input_transition"):
        git_finish_form_b(handle, run_dir, s1["session_id"], output_transition_id=ot2_id)


# ---------------------------------------------------------------------------
# Payload serialization round-trip
# ---------------------------------------------------------------------------

def test_git_change_payload_roundtrip(stag_env, git_repo):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    s1 = git_start(handle, run_dir, it_id)
    store.save_run(handle)
    _make_commit(git_repo, "rtrip.py", "roundtrip commit")

    handle = store.load_run(run_id)
    git_finish_form_a(handle, run_dir, s1["session_id"], status="completed")
    store.save_run(handle)

    fresh = store.load_run(run_id)
    gcps = [
        p for p in fresh.run_graph.payloads.values()
        if isinstance(p, GitChangePayload)
    ]
    assert len(gcps) == 1
    gcp = gcps[0]
    d = gcp.to_dict()
    assert d["payload_type"] == "git_change"
    assert d["target_kind"] == "output_transition"
    assert len(d["commit_log"]) == 1
    assert len(d["commits"]) == 1

    from stag.core.schema.payloads import payload_from_dict
    restored = payload_from_dict(d)
    assert isinstance(restored, GitChangePayload)
    assert restored.branch == gcp.branch
    assert restored.base_commit == gcp.base_commit
    assert restored.commits == gcp.commits


# ---------------------------------------------------------------------------
# CLI E2E — status / diff / log
# ---------------------------------------------------------------------------

def test_git_status_cli_e2e(stag_env, git_repo, capsys):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    s1 = git_start(handle, run_dir, it_id)
    store.save_run(handle)

    from stag.cli.main import main as cli_main
    ret = cli_main([
        "git", "status",
        "--run", run_id,
        "--store-dir", store_dir,
    ])
    assert ret == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["run_id"] == run_id
    assert payload["git"]["repo_root"]
    assert payload["git"]["branch"] == "main"
    assert any(s["session_id"] == s1["session_id"] for s in payload["open_sessions"])
    assert payload["latest_git_change_payload"] is None


def test_git_diff_cli_e2e_session(stag_env, git_repo, capsys):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    s1 = git_start(handle, run_dir, it_id)
    store.save_run(handle)
    _make_commit(git_repo, "diff_test.py", "diff session")

    from stag.cli.main import main as cli_main
    ret = cli_main([
        "git", "diff", s1["session_id"],
        "--run", run_id,
        "--store-dir", store_dir,
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "diff_test.py" in captured.out


def test_git_diff_cli_e2e_output_transition(stag_env, git_repo, capsys):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    s1 = git_start(handle, run_dir, it_id)
    store.save_run(handle)
    _make_commit(git_repo, "diff_ot.py", "diff via OT")

    handle = store.load_run(run_id)
    res = git_finish_form_a(handle, run_dir, s1["session_id"], status="completed")
    store.save_run(handle)
    ot_id = res["created"]["output_transition_id"]

    from stag.cli.main import main as cli_main
    ret = cli_main([
        "git", "diff", "--output-transition", ot_id,
        "--run", run_id,
        "--store-dir", store_dir,
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "diff_ot.py" in captured.out


def test_git_log_cli_e2e_session(stag_env, git_repo, capsys):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    s1 = git_start(handle, run_dir, it_id)
    store.save_run(handle)
    _make_commit(git_repo, "log_test.py", "log session entry")

    from stag.cli.main import main as cli_main
    ret = cli_main([
        "git", "log", s1["session_id"],
        "--run", run_id,
        "--store-dir", store_dir,
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "log session entry" in captured.out


def test_git_log_cli_e2e_output_transition(stag_env, git_repo, capsys):
    store_dir, run_id, run_dir, handle, it_id = stag_env
    store = JsonlRunStore(store_dir)

    s1 = git_start(handle, run_dir, it_id)
    store.save_run(handle)
    _make_commit(git_repo, "log_ot.py", "log via OT")

    handle = store.load_run(run_id)
    res = git_finish_form_a(handle, run_dir, s1["session_id"], status="completed")
    store.save_run(handle)
    ot_id = res["created"]["output_transition_id"]

    from stag.cli.main import main as cli_main
    ret = cli_main([
        "git", "log", "--output-transition", ot_id,
        "--run", run_id,
        "--store-dir", store_dir,
    ])
    assert ret == 0
    captured = capsys.readouterr()
    assert "log via OT" in captured.out
