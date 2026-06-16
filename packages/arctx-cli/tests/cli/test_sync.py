"""CLI sync: remote add / push / pull across two local stores sharing a remote."""

from __future__ import annotations

import tempfile
from pathlib import Path

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.sync_cmd import (
    run_pull_command,
    run_push_command,
    run_remote_add_command,
)
from arctx_cli.context import resolve_store


def _init(sd):
    run_init_command(requirement_id="r", target_type="task", target_id="t",
                     run_id="proj", store_dir=sd)


def test_remote_push_pull_roundtrip():
    with tempfile.TemporaryDirectory() as prod, tempfile.TemporaryDirectory() as cons, \
            tempfile.TemporaryDirectory() as shared:
        psd, csd = str(Path(prod) / "runs"), str(Path(cons) / "runs")
        remote = str(Path(shared) / "remotes")

        # producer: a step, register remote, push
        _init(psd)
        root = resolve_store(psd).load_run("proj").root_node_id
        run_add_step_command(run_id="proj", input_node_ids=[root], title="alice work",
                             payload_kind=None, payload_type="step_payload",
                             field_data={}, json_data={}, store_dir=psd)
        run_remote_add_command(run_id="proj", name="origin", remote_dir=remote,
                               shared_run_id=None, store_dir=psd, user_id="alice",
                               work_session_id="ws")
        pushed = run_push_command(run_id="proj", store_dir=psd)
        assert pushed["pushed_records"] >= 3

        # consumer: separate store, same remote + run id, pull
        _init(csd)
        run_remote_add_command(run_id="proj", name="origin", remote_dir=remote,
                               shared_run_id=None, store_dir=csd, user_id="bob",
                               work_session_id="ws")
        res = run_pull_command(run_id="proj", store_dir=csd)
        assert res["pulled_records"] >= 3

        reloaded = resolve_store(csd).load_run("proj")
        assert len(reloaded.run_graph.steps) == 1

        # pull again: union is idempotent.
        assert run_pull_command(run_id="proj", store_dir=csd)["pulled_records"] == 0
