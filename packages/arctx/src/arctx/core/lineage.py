"""Read-time ancestry/lineage queries over a RunGraph.

Pure functions, in the same spirit as :mod:`arctx.core.cuts`: nothing is
stored, relationships are computed from the DAG on demand. A *target* is a
``(kind, id)`` pair where ``kind`` is ``"node"`` or ``"step"``. The four
combinations (node/node, step/step, node/step, step/node) are all handled
uniformly by reducing each record to node positions in the DAG.

The backbone is :meth:`RunGraph.ancestors_of`, which walks backwards through
the DAG via ``step_by_output_node``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from arctx.core.run_graph import RunGraph

Kind = Literal["node", "step"]
Target = tuple[Kind, str]
Relation = Literal["same", "ancestor", "descendant", "unrelated"]

__all__ = ["Target", "Relation", "history_nodes", "relationship", "is_visible_from"]


def _check(graph: "RunGraph", target: Target) -> None:
    kind, id_ = target
    if kind == "node":
        if id_ not in graph.nodes:
            raise KeyError(f"unknown node: {id_!r}")
    elif kind == "step":
        if id_ not in graph.steps:
            raise KeyError(f"unknown step: {id_!r}")
    else:
        raise ValueError(f"unknown target kind: {kind!r}")


def history_nodes(graph: "RunGraph", target: Target) -> set[str]:
    """Nodes the *target* can "see" looking backwards (inclusive of itself).

    - A node sees itself and all of its ancestors.
    - A step sees its input nodes and everything before them (but *not* its
      own output node, which lies after the step).
    """
    _check(graph, target)
    kind, id_ = target
    if kind == "node":
        return {id_} | graph.ancestors_of(id_)
    step = graph.steps[id_]
    seen: set[str] = set()
    for parent in step.input_node_ids:
        seen.add(parent)
        seen |= graph.ancestors_of(parent)
    return seen


def _effect_node(graph: "RunGraph", target: Target) -> str:
    """The node at which the target's result lands (its forward anchor)."""
    kind, id_ = target
    if kind == "node":
        return id_
    return graph.steps[id_].output_node_id


def relationship(graph: "RunGraph", a: Target, b: Target) -> Relation:
    """Classify how *a* relates to *b* in the DAG.

    ``"ancestor"`` means *a* lies in *b*'s backward history (a is before b);
    ``"descendant"`` means the reverse; ``"same"`` means identical records;
    ``"unrelated"`` means neither is in the other's history (siblings /
    concurrent branches).
    """
    _check(graph, a)
    _check(graph, b)
    if a == b:
        return "same"
    if _effect_node(graph, a) in history_nodes(graph, b):
        return "ancestor"
    if _effect_node(graph, b) in history_nodes(graph, a):
        return "descendant"
    return "unrelated"


def is_visible_from(graph: "RunGraph", target: Target, viewer: Target) -> bool:
    """Whether *target* may be referenced from *viewer*.

    True when *target* is an ancestor of *viewer* or the same record:
    a record can reference assets attached to its own history (parents), but
    not assets attached to its descendants (children).
    """
    return relationship(graph, target, viewer) in ("ancestor", "same")
