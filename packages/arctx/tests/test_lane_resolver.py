"""Lane resolution chain: explicit > env > <gitdir>/arctx-lane > config > default.

The file pointer is what lets `arctx lane <name>` persist across shells without
`eval`; the env var is the shell-local override for parallel work.
"""

from __future__ import annotations

from arctx.paths import find_repo_root, write_arctx_lane
from arctx.session import resolve_work_session_id


def _fake_repo(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path / "home"))
    monkeypatch.delenv("ARCTX_WORK_SESSION_ID", raising=False)
    monkeypatch.chdir(tmp_path)


def test_lane_resolved_from_file_pointer(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    write_arctx_lane(find_repo_root(), "lane_xyz")
    assert resolve_work_session_id(None) == "lane_xyz"


def test_lane_resolved_from_run_scoped_file_pointer(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    repo = find_repo_root()
    write_arctx_lane(repo, "lane_run_a", run_id="run_a")
    write_arctx_lane(repo, "lane_run_b", run_id="run_b")
    assert resolve_work_session_id(None, run_id="run_a") == "lane_run_a"
    assert resolve_work_session_id(None, run_id="run_b") == "lane_run_b"


def test_run_scoped_pointer_beats_legacy_file_pointer(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    repo = find_repo_root()
    write_arctx_lane(repo, "lane_legacy")
    write_arctx_lane(repo, "lane_run", run_id="run_x")
    assert resolve_work_session_id(None, run_id="run_x") == "lane_run"


def test_env_beats_file_pointer(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    write_arctx_lane(find_repo_root(), "lane_file", run_id="run_x")
    monkeypatch.setenv("ARCTX_WORK_SESSION_ID", "lane_env")
    assert resolve_work_session_id(None, run_id="run_x") == "lane_env"


def test_explicit_beats_everything(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)
    write_arctx_lane(find_repo_root(), "lane_file")
    monkeypatch.setenv("ARCTX_WORK_SESSION_ID", "lane_env")
    assert resolve_work_session_id("explicit") == "explicit"


def test_default_when_unset(tmp_path, monkeypatch):
    _fake_repo(tmp_path, monkeypatch)  # .git exists but no pointer written
    assert resolve_work_session_id(None) == "default"
