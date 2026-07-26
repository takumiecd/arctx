"""Integration tests for ``arctx asset`` against real temporary git repos."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from arctx_cli.commands.asset import (
    run_asset_attach_command,
    run_asset_show_command,
)
from arctx_cli.commands.init import run_init_command
from arctx_cli.main import main


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, check=True)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _run(["git", "init", "-q"], path)
    _run(["git", "config", "user.email", "test@example.com"], path)
    _run(["git", "config", "user.name", "Test User"], path)
    (path / "notes.md").write_text("# hello\n", encoding="utf-8")
    (path / "bench").mkdir()
    (path / "bench" / "result.txt").write_text("score=0.9\n", encoding="utf-8")
    _run(["git", "add", "-A"], path)
    _run(["git", "commit", "-qm", "initial"], path)
    return path


@pytest.fixture
def env(tmp_path, monkeypatch):
    repo = _init_repo(tmp_path / "repo")
    store_dir = str(repo / ".arctx" / "runs")
    result = run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="asset_run",
        store_dir=store_dir,
    )
    monkeypatch.chdir(repo)
    return repo, store_dir, "asset_run", result["root_node_id"]


class TestAssetAttachCommand:
    def test_attaches_head_reference(self, env):
        repo, store_dir, run_id, root = env
        result = run_asset_attach_command(
            run_id=run_id,
            target_id=root,
            path="bench/result.txt",
            commit=None,
            title=None,
            store_dir=store_dir,
            user_id="alice",
            lane_id="lane_1",
        )
        payload = result["payload"]
        assert payload["payload_type"] == "asset"
        assert payload["path"] == "bench/result.txt"
        assert payload["target_kind"] == "node"
        assert result["kind"] == "blob"
        # No remote configured in the fixture, so the push warning fires.
        assert result["warning"] is not None

    def test_directory_and_explicit_commit(self, env):
        repo, store_dir, run_id, root = env
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(repo),
            capture_output=True, text=True, check=True,
        ).stdout.strip()

        result = run_asset_attach_command(
            run_id=run_id,
            target_id=root,
            path="bench",
            commit=head[:8],
            title="bench dir",
            store_dir=store_dir,
            user_id="alice",
            lane_id="lane_1",
        )
        assert result["kind"] == "tree"
        assert result["payload"]["commit"] == head
        assert result["payload"]["title"] == "bench dir"

    def test_step_target_kind_is_auto_resolved(self, env):
        from arctx_cli.commands.add import run_add_step_command

        repo, store_dir, run_id, root = env
        added = run_add_step_command(
            run_id=run_id,
            input_node_ids=[root],
            title="try something",
            payload_kind="try",
            payload_type="step_payload",
            field_data={},
            json_data={},
            store_dir=store_dir,
            user_id="alice",
            lane_id="lane_1",
        )
        step_id = added["step"]["step_id"]
        result = run_asset_attach_command(
            run_id=run_id, target_id=step_id, path="notes.md", commit=None,
            title=None, store_dir=store_dir, user_id="alice", lane_id="lane_1",
        )
        assert result["payload"]["target_kind"] == "step"
        assert result["payload"]["target_id"] == step_id

    def test_missing_path_exits_nonzero(self, env, capsys):
        repo, store_dir, run_id, root = env
        rc = main(["asset", "attach", root, "bench/nope.txt", "--run", run_id,
                   "--store-dir", store_dir])
        assert rc == 1
        assert "path not found" in capsys.readouterr().err

    def test_cli_prints_payload_and_warning(self, env, capsys):
        repo, store_dir, run_id, root = env
        rc = main(["asset", "attach", root, "notes.md", "--run", run_id,
                   "--store-dir", store_dir, "--user", "alice", "--lane", "lane_1"])
        assert rc == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["payload_type"] == "asset"
        assert "warning:" in captured.err


class TestAssetShowCommand:
    def test_found(self, env):
        repo, store_dir, run_id, root = env
        attached = run_asset_attach_command(
            run_id=run_id, target_id=root, path="notes.md", commit=None,
            title=None, store_dir=store_dir, user_id="alice", lane_id="lane_1",
        )
        view = run_asset_show_command(
            run_id=run_id,
            payload_id=attached["payload"]["payload_id"],
            store_dir=store_dir,
        )
        assert view["resolution"]["status"] == "found"
        assert view["resolution"]["kind"] == "blob"
        assert view["reference"].endswith(":notes.md")

    def test_missing_commit_is_diagnosable(self, env):
        from arctx.core.schema.payloads import AssetPayload
        from arctx_cli.context import resolve_store

        repo, store_dir, run_id, root = env
        store = resolve_store(store_dir)
        handle = store.load_run(run_id)
        broken = AssetPayload(
            payload_id=handle._next_id("pl"),
            target_id=root,
            target_kind="node",
            commit="0" * 40,
            path="notes.md",
        )
        handle.run_graph.attach_payload(broken)
        store.save_run(handle)

        view = run_asset_show_command(
            run_id=run_id, payload_id=broken.payload_id, store_dir=store_dir
        )
        assert view["resolution"]["status"] == "missing_commit"

    def test_missing_path_is_diagnosable(self, env):
        from arctx.core.schema.payloads import AssetPayload
        from arctx_cli.context import resolve_store

        repo, store_dir, run_id, root = env
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(repo),
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        store = resolve_store(store_dir)
        handle = store.load_run(run_id)
        broken = AssetPayload(
            payload_id=handle._next_id("pl"),
            target_id=root,
            target_kind="node",
            commit=head,
            path="does/not/exist.txt",
        )
        handle.run_graph.attach_payload(broken)
        store.save_run(handle)

        view = run_asset_show_command(
            run_id=run_id, payload_id=broken.payload_id, store_dir=store_dir
        )
        assert view["resolution"]["status"] == "missing_path"

    def test_non_asset_payload_is_rejected(self, env):
        repo, store_dir, run_id, root = env
        from arctx.core.schema.payloads import NodePayload
        from arctx_cli.context import resolve_store

        store = resolve_store(store_dir)
        handle = store.load_run(run_id)
        payload = handle.attach(root, NodePayload(payload_id="p", target_id=root, type="note"))
        store.save_run(handle)

        with pytest.raises(ValueError, match="not an asset"):
            run_asset_show_command(
                run_id=run_id, payload_id=payload.payload_id, store_dir=store_dir
            )
