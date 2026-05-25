"""Smoke tests for the new CLI: init, list, transition, cut, dump."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from stag.cli.commands.init import run_init_command
from stag.cli.commands.list import run_list_command
from stag.cli.commands.transition import run_transition_command
from stag.cli.commands.cut import run_cut_command
from stag.cli.commands.dump import run_dump_command


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init(td: str, req_id: str = "req1", run_id: str = "test_run") -> dict:
    return run_init_command(
        requirement_id=req_id,
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(td),
    )


# ---------------------------------------------------------------------------
# stag init
# ---------------------------------------------------------------------------


def test_init_creates_run():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        assert result["run_id"] == "test_run"
        assert "root_node_id" in result
        run_dir = Path(td) / "runs" / "test_run"
        assert run_dir.exists()


def test_init_duplicate_raises():
    with tempfile.TemporaryDirectory() as td:
        _init(td)
        with pytest.raises(FileExistsError):
            _init(td)


# ---------------------------------------------------------------------------
# stag list
# ---------------------------------------------------------------------------


def test_list_runs():
    with tempfile.TemporaryDirectory() as td:
        _init(td, run_id="run_a")
        _init(td, req_id="req2", run_id="run_b")
        result = run_list_command(store_dir=_store_dir(td))
        ids = [r["run_id"] for r in result["runs"]]
        assert "run_a" in ids
        assert "run_b" in ids


# ---------------------------------------------------------------------------
# stag transition
# ---------------------------------------------------------------------------


def test_transition_creates_transition():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        root_id = result["root_node_id"]
        tr_result = run_transition_command(
            run_id="test_run",
            input_node_ids=[root_id],
            payload_type="suggestion",
            content={"proposal": "try lr=0.01"},
            max_outcomes=1,
            store_dir=_store_dir(td),
        )
        assert len(tr_result["transitions"]) == 1
        t = tr_result["transitions"][0]
        assert t["transition_id"].startswith("t_")
        assert t["output_node_id"].startswith("n_")


def test_transition_max_outcomes():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        root_id = result["root_node_id"]
        tr_result = run_transition_command(
            run_id="test_run",
            input_node_ids=[root_id],
            payload_type="suggestion",
            content={},
            max_outcomes=3,
            store_dir=_store_dir(td),
        )
        assert len(tr_result["transitions"]) == 3


def test_transition_unknown_run_raises():
    with tempfile.TemporaryDirectory() as td:
        with pytest.raises(KeyError, match="unknown run_id"):
            run_transition_command(
                run_id="no_such_run",
                input_node_ids=["n_x"],
                payload_type="experiment",
                content={},
                store_dir=_store_dir(td),
            )


# ---------------------------------------------------------------------------
# stag cut
# ---------------------------------------------------------------------------


def test_cut_node():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        root_id = result["root_node_id"]
        tr_result = run_transition_command(
            run_id="test_run",
            input_node_ids=[root_id],
            payload_type="suggestion",
            content={},
            store_dir=_store_dir(td),
        )
        output_node_id = tr_result["transitions"][0]["output_node_id"]
        cut_result = run_cut_command(
            run_id="test_run",
            target_id=output_node_id,
            target_kind="node",
            reason="not useful",
            store_dir=_store_dir(td),
        )
        assert cut_result["cut"]["target_kind"] == "node"
        assert cut_result["cut"]["target_id"] == output_node_id


# ---------------------------------------------------------------------------
# stag dump
# ---------------------------------------------------------------------------


def test_dump_outline():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        root_id = result["root_node_id"]
        run_transition_command(
            run_id="test_run",
            input_node_ids=[root_id],
            payload_type="experiment",
            content={},
            store_dir=_store_dir(td),
        )
        out = run_dump_command(
            run_id="test_run",
            fmt="outline",
            store_dir=_store_dir(td),
        )
        assert "test_run" in out
        assert root_id in out


def test_dump_mermaid():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        root_id = result["root_node_id"]
        run_transition_command(
            run_id="test_run",
            input_node_ids=[root_id],
            payload_type="experiment",
            content={},
            store_dir=_store_dir(td),
        )
        out = run_dump_command(
            run_id="test_run",
            fmt="mermaid",
            store_dir=_store_dir(td),
        )
        assert "```mermaid" in out
        assert "flowchart TD" in out
