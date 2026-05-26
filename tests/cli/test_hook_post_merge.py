"""Tests for stag hook post-merge functionality."""

from __future__ import annotations

from pathlib import Path

import pytest

from stag.cli.commands.init import run_init_command
from stag.cli.commands.hook import run_hook_install, run_hook_post_merge
from stag.cli.context import resolve_store


def _store_dir(tmp_path: Path) -> str:
    return str(tmp_path / "stag_home" / "runs")


def _init_stag(tmp_path: Path, run_id: str = "run_pm_test") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(tmp_path),
        no_hooks=True,
    )


class TestHookInstallPostMerge:
    def test_install_creates_post_merge_hook(self, tmp_path):
        """run_hook_install should create post-merge hook alongside post-rewrite."""
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)

        result = run_hook_install(repo_path=repo, force=False)
        assert result["status"] == "installed"

        post_merge_path = repo / ".git" / "hooks" / "post-merge"
        assert post_merge_path.exists()
        assert "post-merge" in post_merge_path.read_text()
        # Must be executable.
        assert post_merge_path.stat().st_mode & 0o111

    def test_install_force_overwrites_post_merge(self, tmp_path):
        """--force should overwrite existing post-merge hook."""
        import subprocess
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=str(repo), capture_output=True, check=True)
        hooks_dir = repo / ".git" / "hooks"
        (hooks_dir / "post-merge").write_text("#!/bin/bash\necho old\n")

        result = run_hook_install(repo_path=repo, force=True)
        assert result["status"] == "installed"
        content = (hooks_dir / "post-merge").read_text()
        assert "stag hook post-merge" in content


class TestRunHookPostMerge:
    def test_skip_squash_merge(self, tmp_path):
        """Squash merges should be skipped."""
        _init_stag(tmp_path, run_id="run_pm_sq")
        result = run_hook_post_merge(
            run_id="run_pm_sq",
            store_dir=_store_dir(tmp_path),
            squash=True,
            head_sha="deadbeef",
        )
        assert result["action"] == "skip"
        assert "squash" in result["message"].lower()

    def test_skip_already_known_sha(self, tmp_path):
        """If HEAD sha is already in stag, action is skip."""
        from stag.cli.commands.commit import run_commit_command
        from stag.core.schema.work_helpers import make_session_pointer_event

        _init_stag(tmp_path, run_id="run_pm_known")
        sd = _store_dir(tmp_path)

        # Record a commit in stag with a known sha.
        r = run_commit_command(
            message="known",
            branch="main",
            run_id="run_pm_known",
            store_dir=sd,
            user_id="u",
            work_session_id="ws",
            dry_run=True,
            head_commit="sha_known_001",
        )

        result = run_hook_post_merge(
            run_id="run_pm_known",
            store_dir=sd,
            squash=False,
            head_sha="sha_known_001",
        )
        assert result["action"] == "skip"
        assert "already recorded" in result["message"]

    def test_adopt_merge_when_other_node_known(self, tmp_path):
        """When ^2 parent sha is already in stag, adopt creates multi-input transition."""
        from stag.cli.commands.commit import run_commit_command
        from stag.core.schema.payloads import MergePayload
        from stag.core.schema.work import WorkSession
        from stag.core.schema.work_helpers import make_session_pointer_event

        _init_stag(tmp_path, run_id="run_pm_adopt")
        sd = _store_dir(tmp_path)

        # Build two branches in stag.
        r_main = run_commit_command(
            message="main",
            branch="main",
            run_id="run_pm_adopt",
            store_dir=sd,
            user_id="u",
            work_session_id="ws_m",
            dry_run=True,
            head_commit="sha_main_adopt",
        )

        store = resolve_store(sd)
        handle = store.load_run("run_pm_adopt")
        root_id = handle.root_node_id
        handle.run_graph.add_work_session(
            WorkSession(work_session_id="ws_f", run_id=handle.run_id, user_id="u")
        )
        sp = make_session_pointer_event(
            event_id=handle._next_id("we"),
            run_id=handle.run_id,
            work_session_id="ws_f",
            user_id="u",
            current_node_ids=(root_id,),
            current_branch="feature",
        )
        handle.run_graph.add_work_event(sp)
        store.save_run(handle)

        r_feat = run_commit_command(
            message="feat",
            branch="feature",
            run_id="run_pm_adopt",
            store_dir=sd,
            user_id="u",
            work_session_id="ws_f",
            dry_run=True,
            head_commit="sha_feat_adopt",
        )

        # Simulate git post-merge hook with known ^2 parent sha.
        # We monkey-patch the subprocess call inside run_hook_post_merge by
        # providing head_sha and patching git calls.
        import unittest.mock as mock

        def _fake_run(cmd, **kw):
            class FakeResult:
                returncode = 0
                stdout = ""
                stderr = ""
            if "rev-parse" in cmd and "HEAD^2" in cmd:
                FakeResult.stdout = "sha_feat_adopt\n"
            elif "rev-parse" in cmd and "HEAD" in cmd:
                FakeResult.stdout = "sha_new_merge\n"
            return FakeResult()

        with mock.patch("subprocess.run", side_effect=_fake_run):
            result = run_hook_post_merge(
                run_id="run_pm_adopt",
                store_dir=sd,
                squash=False,
                head_sha="sha_new_merge",
                user_id="u",
                work_session_id="ws_m",
            )

        assert result["action"] == "adopted"
        assert result["transition_id"] is not None

        handle2 = resolve_store(sd).load_run("run_pm_adopt")
        t = handle2.run_graph.transitions[result["transition_id"]]
        assert len(t.input_node_ids) == 2

    def test_warn_when_cannot_load_run(self, tmp_path):
        """Returns warn if run cannot be loaded."""
        result = run_hook_post_merge(
            run_id="run_nonexistent",
            store_dir=_store_dir(tmp_path),
            squash=False,
            head_sha="deadbeef1234",
        )
        assert result["action"] == "warn"
