"""Tests for file-backed local/shared sync commands."""

from __future__ import annotations

import json

from stag.cli.commands.anchor import run_anchor_command
from stag.cli.commands.init import run_init_command
from stag.cli.commands.plan import run_plan_command
from stag.cli.commands.sync import (
    run_sync_init_command,
    run_sync_pull_command,
    run_sync_push_command,
    run_sync_status_command,
)
from stag.cli.context import resolve_store
from stag.core.run.dump import DumpOptions, dump


def _init(store_dir: str, run_id: str) -> None:
    run_init_command(
        requirement_id="req",
        target_type="task",
        target_id="target",
        run_id=run_id,
        store_dir=store_dir,
    )


def test_local_shared_sync_push_pull_round_trip(tmp_path):
    store_dir = str(tmp_path / "runs")
    remote_dir = str(tmp_path / "remotes")
    _init(store_dir, "local_a")
    _init(store_dir, "local_b")

    anchor = run_anchor_command(
        run_id="local_a",
        from_node_id="n_0000",
        label="common benchmark setup",
        store_dir=store_dir,
    )["anchor"]

    init = run_sync_init_command(
        run_id="local_a",
        shared_run_id="sr_demo",
        store_dir=store_dir,
        remote_dir=remote_dir,
        workspace_id="mbp",
        actor_id="takumi",
    )
    assert init["shared_run_id"] == "sr_demo"

    before = run_sync_status_command(
        run_id="local_a",
        store_dir=store_dir,
        shared_run_id="sr_demo",
        remote_dir=remote_dir,
    )
    assert before["unpushed_records"] == 7
    assert before["unpulled_records"] == 0

    pushed = run_sync_push_command(
        run_id="local_a",
        store_dir=store_dir,
        shared_run_id="sr_demo",
        remote_dir=remote_dir,
        workspace_id="mbp",
        actor_id="takumi",
    )
    assert pushed["pushed_records"] == 7
    assert pushed["pushed_batches"] == 2

    records_path = tmp_path / "remotes" / "local-shared" / "runs" / "sr_demo" / "records.jsonl"
    batches = [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert [batch["operation"] for batch in batches] == ["seed", "anchor"]
    assert all("batch_id" in batch for batch in batches)
    assert all("actor" in batch for batch in batches)
    assert all("origin" in batch for batch in batches)
    assert len(batches[1]["records"]) == 5

    idmap_a = tmp_path / "runs" / "local_a" / "idmap.jsonl"
    assert len(idmap_a.read_text(encoding="utf-8").splitlines()) == 7

    pulled = run_sync_pull_command(
        run_id="local_b",
        store_dir=store_dir,
        shared_run_id="sr_demo",
        remote_dir=remote_dir,
    )
    assert pulled["pulled_records"] == 5
    assert pulled["pulled_batches"] == 2
    idmap_b = tmp_path / "runs" / "local_b" / "idmap.jsonl"
    assert len(idmap_b.read_text(encoding="utf-8").splitlines()) == 7

    handle = resolve_store(store_dir).load_run("local_b")
    rendered = dump(handle, "outline", DumpOptions())
    assert "anchor=common benchmark setup" in rendered

    it = run_plan_command(
        run_id="local_b",
        input_node_ids=[anchor["node_id"]],
        action_type="verification",
        intent="run variant B",
        store_dir=store_dir,
    )["input_transition"]
    assert it["input_transition_id"] == "it_0002"
    assert it["input_node_ids"] == [anchor["node_id"]]


def test_sync_status_uses_saved_config(tmp_path):
    store_dir = str(tmp_path / "runs")
    remote_dir = str(tmp_path / "remotes")
    _init(store_dir, "local_a")

    run_sync_init_command(
        run_id="local_a",
        shared_run_id="sr_demo",
        store_dir=store_dir,
        remote_dir=remote_dir,
        workspace_id="mbp",
        actor_id="takumi",
    )
    status = run_sync_status_command(run_id="local_a", store_dir=store_dir)
    assert status["remote"] == "local-shared"
    assert status["shared_run_id"] == "sr_demo"
