"""Smoke tests for the new CLI: init, list, step, cut, dump."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from arctx_cli.commands.cut import run_cut_command
from arctx_cli.commands.dump import run_dump_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.list import run_list_command
from arctx_cli.commands.payload import run_payload_add_command, run_payload_list_command
from arctx_cli.commands.step import run_step_command

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
# arctx init
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
# arctx list
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
# arctx step
# ---------------------------------------------------------------------------


def test_step_creates_step():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        root_id = result["root_node_id"]
        tr_result = run_step_command(
            run_id="test_run",
            input_node_ids=[root_id],
            payload_type="suggestion",
            content={"proposal": "try lr=0.01"},
            store_dir=_store_dir(td),
        )
        t = tr_result["step"]
        assert t["step_id"].startswith("t_")
        assert t["output_node_id"].startswith("n_")


def test_step_always_creates_one_output_node():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        root_id = result["root_node_id"]
        tr_result = run_step_command(
            run_id="test_run",
            input_node_ids=[root_id],
            payload_type="suggestion",
            content={},
            store_dir=_store_dir(td),
        )
        assert tr_result["step"]["output_node_id"].startswith("n_")


def test_step_unknown_run_raises():
    with tempfile.TemporaryDirectory() as td:
        with pytest.raises(KeyError, match="unknown run_id"):
            run_step_command(
                run_id="no_such_run",
                input_node_ids=["n_x"],
                payload_type="experiment",
                content={},
                store_dir=_store_dir(td),
            )


# ---------------------------------------------------------------------------
# arctx cut
# ---------------------------------------------------------------------------


def test_cut_node():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        root_id = result["root_node_id"]
        tr_result = run_step_command(
            run_id="test_run",
            input_node_ids=[root_id],
            payload_type="suggestion",
            content={},
            store_dir=_store_dir(td),
        )
        output_node_id = tr_result["step"]["output_node_id"]
        cut_result = run_cut_command(
            run_id="test_run",
            target_id=output_node_id,
            target_kind="node",
            reason="not useful",
            store_dir=_store_dir(td),
        )
        assert cut_result["cut"]["target_kind"] == "node"
        assert cut_result["cut"]["target_id"] == output_node_id


def test_payload_add_and_list_node_payload():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        root_id = result["root_node_id"]
        add_result = run_payload_add_command(
            run_id="test_run",
            target_kind="node",
            target_id=root_id,
            payload_type="node_payload",
            field_data={"type": "note", "text": "hello"},
            json_data={},
            store_dir=_store_dir(td),
        )
        assert add_result["payload"]["payload_type"] == "node_payload"
        listed = run_payload_list_command(
            run_id="test_run",
            target_kind="node",
            target_id=root_id,
            store_dir=_store_dir(td),
        )
        assert listed["payloads"][0]["content"]["text"] == "hello"


def test_payload_add_and_list_diagram_payload():
    with tempfile.TemporaryDirectory() as td:
        result = run_init_command(
            requirement_id="req1",
            target_type="task",
            target_id="t",
            run_id="test_run",
            store_dir=_store_dir(td),
            extensions=["diagram"],
            extension_options={},
        )
        root_id = result["root_node_id"]
        add_result = run_payload_add_command(
            run_id="test_run",
            target_kind="node",
            target_id=root_id,
            payload_type="diagram",
            field_data={},
            json_data={
                "title": "retry loop",
                "format": "nodes_edges",
                "nodes": [{"id": "fetch"}, {"id": "retry"}],
                "edges": [
                    {"from": "fetch", "to": "retry"},
                    {"from": "retry", "to": "fetch"},
                ],
            },
            store_dir=_store_dir(td),
        )

        assert add_result["payload"]["payload_type"] == "diagram"
        assert add_result["payload"]["edges"][1]["to"] == "fetch"
        listed = run_payload_list_command(
            run_id="test_run",
            target_kind="node",
            target_id=root_id,
            store_dir=_store_dir(td),
        )
        assert listed["payloads"][0]["title"] == "retry loop"


# ---------------------------------------------------------------------------
# arctx dump
# ---------------------------------------------------------------------------


def test_dump_outline():
    with tempfile.TemporaryDirectory() as td:
        result = _init(td)
        root_id = result["root_node_id"]
        run_step_command(
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
        run_step_command(
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
