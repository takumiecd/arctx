"""arctx-native sync: push = record diff, pull = union (CRDT, idempotent).

Modeled on git's UX but simpler: no conflicts, no rewrite. Pull applies records
in dependency order (nodes -> steps -> payloads) and skips ones already present.
"""

from __future__ import annotations

import tempfile

import arctx
from arctx import Requirement, StepPayload
from arctx.core.sync.local import sync_pull, sync_push


def _run(run_id):
    return arctx.init(
        Requirement(requirement_id="r", target_type="t", target_id="t"), run_id=run_id
    )


def _push(handle, rd, actor):
    return sync_push(handle=handle, remote="origin", shared_run_id="shared",
                     remote_dir=rd, workspace_id="ws", actor_id=actor)


def _pull(handle, rd):
    return sync_pull(handle=handle, remote="origin", shared_run_id="shared", remote_dir=rd)


def test_push_pull_roundtrip_and_idempotent():
    rd = tempfile.mkdtemp()
    prod = _run("shared")
    prod.add_step([prod.root_node_id],
                  StepPayload(payload_id="", target_id="", type="explore",
                              content={"title": "x"}))
    _push(prod, rd, "alice")

    cons = _run("shared")
    res = _pull(cons, rd)
    assert res["pulled_records"] >= 3  # root + output node + step (+ payload)
    assert len(cons.run_graph.steps) == 1
    assert cons.run_graph.steps.keys() == prod.run_graph.steps.keys()

    # pull again: union is idempotent, nothing new applied.
    res2 = _pull(cons, rd)
    assert res2["pulled_records"] == 0


def test_pull_converges_two_producers():
    """Two actors push independent work to the same shared run; a puller unions."""
    rd = tempfile.mkdtemp()
    a = _run("shared")
    a.add_step([a.root_node_id], StepPayload(payload_id="", target_id="",
               type="explore", content={"title": "A"}))
    _push(a, rd, "alice")

    b = _run("shared")
    _pull(b, rd)  # b adopts the shared seed + A's work
    b.add_step([b.root_node_id], StepPayload(payload_id="", target_id="",
               type="explore", content={"title": "B"}))
    _push(b, rd, "bob")

    c = _run("shared")
    _pull(c, rd)
    # c sees both A's and B's steps — union converged.
    assert len(c.run_graph.steps) == 2
