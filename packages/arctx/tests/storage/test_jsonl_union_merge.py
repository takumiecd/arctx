"""Loader guarantees for git ``merge=union`` jsonl files.

`.arctx/` is committed and `.gitattributes` gives `*.jsonl merge=union`, so a
merged working tree may contain duplicated lines in an order no single writer
produced. Loading must be idempotent (duplicates collapse) and independent of
line order (a step may be listed before the node it consumes).
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from arctx import init
from arctx.core.cuts import cut_node_ids
from arctx.core.schema.payloads import NodePayload, StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.storage._cache import cache_path
from arctx.storage.jsonl import JsonlRunStore

_JSONL_NAMES = (
    "nodes.jsonl",
    "steps.jsonl",
    "payloads.jsonl",
    "lanes.jsonl",
    "work_events.jsonl",
)


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _populated(run_id: str):
    """A run written the way the CLI writes one: every verb attributed."""
    kw = {"user_id": "u", "lane_id": "l"}
    run = init(_req(), run_id=run_id)
    t1 = run.add_step([run.root_node_id], StepPayload(payload_id="_", target_id="_", type="a"), **kw)
    n1 = t1.output_node_id
    t2 = run.add_step([n1], StepPayload(payload_id="_", target_id="_", type="b"), **kw)
    n2 = t2.output_node_id
    t3 = run.add_step([n1, n2], StepPayload(payload_id="_", target_id="_", type="join"), **kw)
    run.attach(
        run.root_node_id,
        NodePayload(payload_id="_", target_id="_", type="note", content={"text": "hi"}),
        **kw,
    )
    # cut then uncut then cut again: supersession depends on record order, so
    # this is the sharpest probe of order-independence.
    run.cut(n2, target_kind="node", **kw)
    run.uncut(n2, target_kind="node", **kw)
    run.cut(n2, target_kind="node", **kw)
    return run, n2


def _scramble(run_dir: Path, seed: int) -> None:
    """Shuffle every jsonl file's lines and duplicate a third of them."""
    rng = random.Random(seed)
    for name in _JSONL_NAMES:
        path = run_dir / name
        if not path.exists():
            continue
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        duplicated = lines + rng.sample(lines, k=max(1, len(lines) // 3))
        rng.shuffle(duplicated)
        path.write_text("".join(ln + "\n" for ln in duplicated), encoding="utf-8")
    # The pickle cache is keyed on row counts, but drop it explicitly so the
    # test exercises the full load path rather than a lucky cache hit.
    cache_path(run_dir).unlink(missing_ok=True)


def _snapshot(graph) -> dict:
    return {
        "nodes": [n.node_id for n in graph.nodes.values()],
        "steps": [(s.step_id, s.input_node_ids, s.output_node_id) for s in graph.steps.values()],
        "payloads": [(p.payload_id, p.payload_type, p.target_id) for p in graph.payloads.values()],
        "lanes": sorted(graph.lanes),
        "events": [e.event_id for e in graph.work_events],
        "by_input": {k: sorted(v) for k, v in graph.steps_by_input_node.items()},
        "by_output": {k: sorted(v) for k, v in graph.step_by_output_node.items()},
        "payloads_by_node": {k: sorted(v) for k, v in graph.payloads_by_node.items()},
        "payloads_by_step": {k: sorted(v) for k, v in graph.payloads_by_step.items()},
    }


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_shuffled_and_duplicated_jsonl_loads_identically(tmp_path, seed):
    run, _ = _populated("union")
    store = JsonlRunStore(tmp_path)
    store.save_run(run)
    baseline = _snapshot(store.load_run("union").run_graph)

    _scramble(store.run_path("union"), seed)
    loaded = store.load_run("union").run_graph

    assert _snapshot(loaded) == baseline


def test_duplicate_lines_do_not_duplicate_records(tmp_path):
    run, _ = _populated("dup")
    store = JsonlRunStore(tmp_path)
    store.save_run(run)
    run_dir = store.run_path("dup")

    for name in _JSONL_NAMES:
        path = run_dir / name
        text = path.read_text(encoding="utf-8")
        path.write_text(text + text, encoding="utf-8")
    cache_path(run_dir).unlink(missing_ok=True)

    loaded = store.load_run("dup").run_graph
    assert len(loaded.nodes) == len(run.run_graph.nodes)
    assert len(loaded.steps) == len(run.run_graph.steps)
    assert len(loaded.payloads) == len(run.run_graph.payloads)
    assert len(loaded.work_events) == len(run.run_graph.work_events)
    # Reverse indices must not gain duplicate entries either.
    for ids in loaded.steps_by_input_node.values():
        assert len(ids) == len(set(ids))
    for ids in loaded.payloads_by_node.values():
        assert len(ids) == len(set(ids))


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_cut_supersession_survives_shuffling(tmp_path, seed):
    """The last cut/uncut marker still wins after the lines are reordered."""
    run, cut_node = _populated("supersede")
    store = JsonlRunStore(tmp_path)
    store.save_run(run)
    _scramble(store.run_path("supersede"), seed)

    loaded = store.load_run("supersede").run_graph
    assert cut_node in cut_node_ids(loaded)


def test_step_lines_may_precede_their_node_lines(tmp_path):
    """Producer-before-consumer line order must not be required."""
    run, _ = _populated("reversed")
    store = JsonlRunStore(tmp_path)
    store.save_run(run)
    run_dir = store.run_path("reversed")

    for name in _JSONL_NAMES:
        path = run_dir / name
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        path.write_text("".join(ln + "\n" for ln in reversed(lines)), encoding="utf-8")
    cache_path(run_dir).unlink(missing_ok=True)

    loaded = store.load_run("reversed").run_graph
    assert _snapshot(loaded) == _snapshot(run.run_graph)


def test_save_run_normalises_duplicated_lines(tmp_path):
    """A write after a union merge rewrites the file without the duplicates."""
    run, _ = _populated("normalise")
    store = JsonlRunStore(tmp_path)
    store.save_run(run)
    run_dir = store.run_path("normalise")

    nodes_path = run_dir / "nodes.jsonl"
    original = nodes_path.read_text(encoding="utf-8")
    nodes_path.write_text(original + original, encoding="utf-8")

    store.save_run(run)
    assert nodes_path.read_text(encoding="utf-8").count("\n") == original.count("\n")
