"""Tests for RunHandle.command extension verbs."""

from __future__ import annotations

import sys

import arctx as arctx
from arctx.core.schema.requirements import Requirement
from arctx.core.schema.work_helpers import latest_session_pointer
from arctx.ext import attach_extensions
from arctx.ext.command.payloads import CommandRunPayload


def test_command_run_records_transition_payload_and_session_pointer(tmp_path):
    handle = attach_extensions(
        arctx.init(
            Requirement(requirement_id="req", target_type="task", target_id="target"),
            run_id="run_command",
        ),
        ["command"],
    )

    result = handle.command.run(
        command=[sys.executable, "-c", "print('ok')"],
        cwd=tmp_path,
        user_id="u1",
        work_session_id="s1",
    )

    transition = result["transition"]
    payload = result["payload"]
    assert transition.input_node_ids == (handle.root_node_id,)
    assert transition.output_node_id in handle.run_graph.nodes
    assert isinstance(payload, CommandRunPayload)
    assert payload.command[:2] == (sys.executable, "-c")
    assert payload.cwd == str(tmp_path.resolve())
    assert payload.exit_code == 0
    assert payload.stdout == "ok\n"

    pointer = latest_session_pointer(handle.run_graph, "s1")
    assert pointer is not None
    assert pointer.data["current_node_ids"] == [transition.output_node_id]
