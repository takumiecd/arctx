"""Gate-type PR: propose / accept (guarded merge) / reject (cut)."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.pr import (
    list_proposals,
    run_accept_command,
    run_propose_command,
    run_reject_command,
)


def _sd(td):
    return str(Path(td) / "runs")


def _setup(td):
    """Init a run; return (store_dir, root, source_tip, target_tip)."""
    sd = _sd(td)
    init = run_init_command(requirement_id="r", target_type="task", target_id="t",
                            run_id="run_pr", store_dir=sd)
    root = init["root_node_id"]
    # main line: root -> target_tip
    target = run_add_step_command(
        run_id="run_pr", input_node_ids=[root], title="main work", payload_kind=None,
        payload_type="step_payload", field_data={}, json_data={}, store_dir=sd,
    )["step"]["output_node_id"]
    # proposal branch: root -> source_tip (sibling off root)
    source = run_add_step_command(
        run_id="run_pr", input_node_ids=[root], title="explore", payload_kind=None,
        payload_type="step_payload", field_data={}, json_data={}, store_dir=sd,
    )["step"]["output_node_id"]
    return sd, root, source, target


def test_propose_then_accept_merges():
    with tempfile.TemporaryDirectory() as td:
        sd, root, source, target = _setup(td)
        run_propose_command(run_id="run_pr", source_node=source, target_node=target,
                            title=None, store_dir=sd)
        props = list_proposals(run_id="run_pr", store_dir=sd)
        assert props == [{"source": source, "target": target, "status": "open"}]

        res = run_accept_command(run_id="run_pr", source_node=source, title=None,
                                 store_dir=sd)
        assert res["accepted"] == source
        assert res["merged_node"]
        # status flips to accepted
        assert list_proposals(run_id="run_pr", store_dir=sd)[0]["status"] == "accepted"


def test_reject_is_a_cut_kept_in_graph():
    with tempfile.TemporaryDirectory() as td:
        sd, root, source, target = _setup(td)
        run_propose_command(run_id="run_pr", source_node=source, target_node=target,
                            title=None, store_dir=sd)
        run_reject_command(run_id="run_pr", source_node=source,
                           reason="not smooth at scale", store_dir=sd)
        # still in the graph, status rejected (the source node is cut)
        assert list_proposals(run_id="run_pr", store_dir=sd)[0]["status"] == "rejected"


def test_accept_refused_when_base_cut():
    """If the source was cut (rejected), accepting it is refused, not corrupting."""
    with tempfile.TemporaryDirectory() as td:
        sd, root, source, target = _setup(td)
        run_propose_command(run_id="run_pr", source_node=source, target_node=target,
                            title=None, store_dir=sd)
        run_reject_command(run_id="run_pr", source_node=source, reason="no",
                           store_dir=sd)
        with pytest.raises(ValueError, match="accept refused|cut"):
            run_accept_command(run_id="run_pr", source_node=source, title=None,
                               store_dir=sd)


def test_accept_refused_when_target_advanced():
    """If the target tip moved since the proposal, accept refuses → rebase."""
    with tempfile.TemporaryDirectory() as td:
        sd, root, source, target = _setup(td)
        run_propose_command(run_id="run_pr", source_node=source, target_node=target,
                            title=None, store_dir=sd)
        # someone advances the target line past `target`
        run_add_step_command(
            run_id="run_pr", input_node_ids=[target], title="main moved",
            payload_kind=None, payload_type="step_payload", field_data={},
            json_data={}, store_dir=sd,
        )
        with pytest.raises(ValueError, match="advanced|rebase"):
            run_accept_command(run_id="run_pr", source_node=source, title=None,
                               store_dir=sd)
