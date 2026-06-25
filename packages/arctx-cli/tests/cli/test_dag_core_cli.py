"""Tests for the DAG core redesign CLI surface."""

from __future__ import annotations

from pathlib import Path

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.attach import run_attach_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.log import run_log_command
from arctx_cli.commands.show import run_show_record_command
from arctx_cli.context import resolve_store


def _store_dir(td: str) -> str:
    return str(Path(td) / "runs")


def _init(td: str, run_id: str = "run_dag_core") -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id=run_id,
        store_dir=_store_dir(td),
    )


def test_add_step_wraps_step_as_step(tmp_path):
    td = str(tmp_path)
    init = _init(td)

    result = run_add_step_command(
        run_id="run_dag_core",
        input_node_ids=[init["root_node_id"]],
        title="try new design",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=_store_dir(td),
    )

    step = result["step"]
    assert step["kind"] == "step"
    assert step["id"].startswith("t_")
    assert step["input_node_ids"] == [init["root_node_id"]]
    assert step["output_node_id"].startswith("n_")


def test_attach_infers_node_or_step_target(tmp_path):
    td = str(tmp_path)
    init = _init(td)
    step = run_add_step_command(
        run_id="run_dag_core",
        input_node_ids=[init["root_node_id"]],
        title="step",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=_store_dir(td),
    )["step"]

    node_payload = run_attach_command(
        run_id="run_dag_core",
        target_id=init["root_node_id"],
        payload_kind="note",
        payload_type=None,
        field_data={"text": "root note"},
        json_data={},
        store_dir=_store_dir(td),
    )["payload"]
    step_payload = run_attach_command(
        run_id="run_dag_core",
        target_id=step["id"],
        payload_kind="result",
        payload_type=None,
        field_data={"score": 0.91},
        json_data={},
        store_dir=_store_dir(td),
    )["payload"]

    assert node_payload["target_kind"] == "node"
    assert node_payload["type"] == "note"
    assert step_payload["target_kind"] == "step"
    assert step_payload["type"] == "result"


def test_show_record_uses_step_vocabulary(tmp_path):
    td = str(tmp_path)
    init = _init(td)
    step = run_add_step_command(
        run_id="run_dag_core",
        input_node_ids=[init["root_node_id"]],
        title="step",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=_store_dir(td),
    )["step"]

    shown = run_show_record_command(
        run_id="run_dag_core",
        record_id=step["id"],
        store_dir=_store_dir(td),
    )

    assert shown["kind"] == "step"
    assert shown["step"]["step_id"] == step["id"]
    assert shown["active"] is True


def test_log_from_renders_step_title(tmp_path):
    td = str(tmp_path)
    init = _init(td)
    run_add_step_command(
        run_id="run_dag_core",
        input_node_ids=[init["root_node_id"]],
        title="try cache",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=_store_dir(td),
    )

    result = run_log_command(
        run_id="run_dag_core",
        from_node_id=init["root_node_id"],
        to_node_id=None,
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
    )

    assert "try cache" in result["log"]


def test_log_to_returns_trace_context(tmp_path):
    td = str(tmp_path)
    init = _init(td)
    step = run_add_step_command(
        run_id="run_dag_core",
        input_node_ids=[init["root_node_id"]],
        title="try cache",
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=_store_dir(td),
    )["step"]

    result = run_log_command(
        run_id="run_dag_core",
        from_node_id=None,
        to_node_id=step["output_node_id"],
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
    )

    assert result["history"]["current_node_id"] == step["output_node_id"]
    assert init["root_node_id"] in result["history"]["past_node_ids"]


def test_attach_summary_then_log_from_summary_truncates(tmp_path):
    td = str(tmp_path)
    init = _init(td)

    def _step(parent: str, title: str) -> dict:
        return run_add_step_command(
            run_id="run_dag_core",
            input_node_ids=[parent],
            title=title,
            payload_kind=None,
            payload_type="step_payload",
            field_data={},
            json_data={},
            store_dir=_store_dir(td),
        )["step"]

    n1 = _step(init["root_node_id"], "s1")["output_node_id"]
    n2 = _step(n1, "s2")["output_node_id"]
    n3 = _step(n2, "s3")["output_node_id"]

    # Write a summary via the generic attach surface (--payload-type summary).
    summary = run_attach_command(
        run_id="run_dag_core",
        target_id=n2,
        payload_kind="summary",
        payload_type="summary",
        field_data={"text": "context up to n2"},
        json_data={},
        store_dir=_store_dir(td),
    )["payload"]
    assert summary["payload_type"] == "summary"
    assert summary["text"] == "context up to n2"

    full = run_log_command(
        run_id="run_dag_core",
        from_node_id=None,
        to_node_id=n3,
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
    )
    assert init["root_node_id"] in full["history"]["past_node_ids"]

    pruned = run_log_command(
        run_id="run_dag_core",
        from_node_id=None,
        to_node_id=n3,
        depth=None,
        full_payloads=False,
        store_dir=_store_dir(td),
        stop_at_summary=True,
    )
    past = pruned["history"]["past_node_ids"]
    assert n2 in past
    assert n1 not in past
    assert init["root_node_id"] not in past
    assert summary["payload_id"] in pruned["history"]["payload_ids"]
