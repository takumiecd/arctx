"""`arctx dump` must survive a run that is merely long.

The outline renderer was a mutual recursion between its node and step
emitters, costing two Python frames per step. A linear chain -- the exact
shape a long agent loop produces -- hit the interpreter's recursion limit at
roughly 495 steps, and `arctx dump` died with "maximum recursion depth
exceeded" instead of printing the run. The renderer walks an explicit stack
now, so depth is bounded by memory.
"""

from __future__ import annotations

import sys

from arctx import init
from arctx.core.run.dump import DumpOptions, render_mermaid, render_outline
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement


def _chain(length: int):
    handle = init(Requirement(requirement_id="r", target_type="task", target_id="t"))
    tip = handle.root_node_id
    for i in range(length):
        step = handle.add_step(
            [tip],
            StepPayload(payload_id="_", target_id="_", type="experiment",
                        content={"note": f"step {i}"}),
        )
        tip = step.output_node_id
    return handle


def test_outline_renders_a_chain_deeper_than_the_recursion_limit():
    depth = sys.getrecursionlimit() * 2  # 2000 by default -- 4x the old ceiling
    handle = _chain(depth)

    out = render_outline(handle, DumpOptions())

    assert f"steps={depth}" in out
    # Every step is rendered exactly once, so the tail must be present.
    last_step = list(handle.run_graph.steps)[-1]
    assert last_step in out


def test_mermaid_renders_the_same_chain():
    depth = sys.getrecursionlimit() * 2
    handle = _chain(depth)
    out = render_mermaid(handle, DumpOptions())
    assert out.startswith("```mermaid")
    # Mermaid labels edges, so it carries node ids rather than step ids.
    assert list(handle.run_graph.nodes)[-1] in out


def test_depth_limit_still_truncates_the_walk():
    handle = _chain(1200)
    out = render_outline(handle, DumpOptions(depth=3))
    # `--depth` bounds the tree walk. Everything it did not reach is listed
    # under `orphans:`, so the bound applies to the tree, not the whole file.
    tree = out.split("orphans:")[0]
    assert len(tree.splitlines()) < 20
