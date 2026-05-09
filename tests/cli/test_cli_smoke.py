"""Smoke tests for the CLI commands."""

from __future__ import annotations

import tempfile

from optagent.cli.commands.init import run_init_command
from optagent.cli.commands.list import run_list_command
from optagent.cli.commands.note import run_note_command
from optagent.cli.commands.observe import run_observe_command
from optagent.cli.commands.plan import run_plan_command
from optagent.cli.commands.predict import run_predict_command
from optagent.cli.commands.rewind import run_rewind_command
from optagent.cli.commands.show import run_show_command
from optagent.cli.commands.trace import run_trace_command


def _init(td: str, rid: str = "rid") -> str:
    run_init_command(
        requirement_id="r",
        target_type="task",
        target_id="t",
        run_id=rid,
        store_dir=td,
    )
    return rid


def test_init_creates_run():
    with tempfile.TemporaryDirectory() as td:
        rid = _init(td)
        runs = run_list_command(store_dir=td)["runs"]
        assert any(r["run_id"] == rid for r in runs)


def test_full_observed_flow():
    with tempfile.TemporaryDirectory() as td:
        rid = _init(td)
        # note
        note = run_note_command(run_id=rid, node_id="n_0000", text="baseline", store_dir=td)["note"]
        assert note["text"] == "baseline"
        # plan
        it = run_plan_command(
            run_id=rid,
            input_node_ids=["n_0000"],
            action_type="analysis",
            intent="test",
            store_dir=td,
        )["input_transition"]
        it_id = it["input_transition_id"]
        # observe
        ot = run_observe_command(
            run_id=rid,
            input_transition_id=it_id,
            status="completed",
            artifacts=["a/b"],
            raw_outputs=None,
            logs=None,
            metrics={"score": 0.5},
            errors=None,
            store_dir=td,
        )["output_transition"]
        ot_id = ot["output_transition_id"]
        to_node = ot["to_node_id"]
        # trace
        history = run_trace_command(run_id=rid, from_node_id=to_node, depth=None, store_dir=td)["history"]
        assert ot_id in history["output_transition_ids"]
        assert it_id in history["input_transition_ids"]
        # show node
        node_view = run_show_command(
            run_id=rid, node_id="n_0000",
            input_transition_id=None, output_transition_id=None, payload_id=None,
            with_payloads=False, outputs=False,
            store_dir=td,
        )
        assert node_view["node"]["node_id"] == "n_0000"


def test_predict_flow():
    with tempfile.TemporaryDirectory() as td:
        rid = _init(td)
        it = run_plan_command(
            run_id=rid, input_node_ids=["n_0000"], action_type="analysis",
            intent="predict test", store_dir=td,
        )["input_transition"]
        it_id = it["input_transition_id"]
        predictions = run_predict_command(
            run_id=rid, input_transition_id=it_id, max_outcomes=2, store_dir=td,
        )["output_transitions"]
        assert len(predictions) == 2
        for p in predictions:
            assert p["input_transition_id"] == it_id


def test_rewind_input_transition():
    with tempfile.TemporaryDirectory() as td:
        rid = _init(td)
        it = run_plan_command(
            run_id=rid, input_node_ids=["n_0000"], action_type="analysis",
            intent="x", store_dir=td,
        )["input_transition"]
        it_id = it["input_transition_id"]
        cut = run_rewind_command(
            run_id=rid, target_id=it_id, target_kind="input_transition",
            reason="oops", store_dir=td,
        )["cut"]
        assert cut["target_id"] == it_id
        assert cut["target_kind"] == "input_transition"


def test_rewind_output_transition():
    with tempfile.TemporaryDirectory() as td:
        rid = _init(td)
        it = run_plan_command(
            run_id=rid, input_node_ids=["n_0000"], action_type="analysis",
            intent="x", store_dir=td,
        )["input_transition"]
        ot = run_observe_command(
            run_id=rid, input_transition_id=it["input_transition_id"],
            status="completed",
            artifacts=None, raw_outputs=None, logs=None, metrics=None, errors=None,
            store_dir=td,
        )["output_transition"]
        cut = run_rewind_command(
            run_id=rid, target_id=ot["output_transition_id"],
            target_kind="output_transition", reason="undo", store_dir=td,
        )["cut"]
        assert cut["target_kind"] == "output_transition"
