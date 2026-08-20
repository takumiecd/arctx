"""Tests for `arctx topic` / `arctx topics`."""

from __future__ import annotations

from pathlib import Path

import pytest

from arctx_cli.commands.add import run_add_step_command
from arctx_cli.commands.init import run_init_command
from arctx_cli.commands.topic import (
    run_topic_summarize_command,
    run_topic_tag_command,
)
from arctx_cli.context import resolve_store

from arctx.core.topics import topic_view


def _store_dir(td) -> str:
    return str(Path(td) / "runs")


def _init(td) -> dict:
    return run_init_command(
        requirement_id="req1",
        target_type="task",
        target_id="t",
        run_id="run_topic",
        store_dir=_store_dir(td),
    )


def _add(td, from_node, title="work") -> dict:
    return run_add_step_command(
        run_id="run_topic",
        input_node_ids=[from_node],
        title=title,
        payload_kind=None,
        payload_type="step_payload",
        field_data={},
        json_data={},
        store_dir=_store_dir(td),
    )["step"]


def _graph(td):
    return resolve_store(_store_dir(td)).load_run("run_topic").run_graph


def test_tag_records_and_view_islands(tmp_path):
    init = _init(tmp_path)
    a = _add(tmp_path, init["root_node_id"])
    b = _add(tmp_path, init["root_node_id"])

    result = run_topic_tag_command(
        run_id="run_topic",
        name="gather",
        record_ids=[a["output_node_id"], b["id"]],
        note="promising",
        store_dir=_store_dir(tmp_path),
    )
    assert result["tagged"] == [a["output_node_id"], b["id"]]

    view = topic_view(_graph(tmp_path), "gather")
    assert {r.record_id for r in view.records} == {a["output_node_id"], b["id"]}
    assert {r.kind for r in view.records} == {"node", "step"}
    # Sibling branches share an ancestor but neither derives from the other:
    # two islands — the join-candidate signal.
    assert len(view.islands) == 2


def test_tag_unknown_record_is_rejected(tmp_path):
    _init(tmp_path)
    with pytest.raises(KeyError):
        run_topic_tag_command(
            run_id="run_topic",
            name="gather",
            record_ids=["n_missing"],
            note=None,
            store_dir=_store_dir(tmp_path),
        )


def test_summarize_latest_wins_and_sources_checked(tmp_path):
    init = _init(tmp_path)
    a = _add(tmp_path, init["root_node_id"])

    run_topic_summarize_command(
        run_id="run_topic",
        name="tile",
        text="old belief",
        sources=None,
        on_node=a["output_node_id"],
        store_dir=_store_dir(tmp_path),
    )
    run_topic_summarize_command(
        run_id="run_topic",
        name="tile",
        text="new belief",
        sources=[a["id"]],
        on_node=a["output_node_id"],
        store_dir=_store_dir(tmp_path),
    )
    view = topic_view(_graph(tmp_path), "tile")
    assert view.summary.text == "new belief"
    assert view.summary.sources == (a["id"],)

    with pytest.raises(KeyError, match="unknown --source"):
        run_topic_summarize_command(
            run_id="run_topic",
            name="tile",
            text="x",
            sources=["n_nope"],
            on_node=a["output_node_id"],
            store_dir=_store_dir(tmp_path),
        )
