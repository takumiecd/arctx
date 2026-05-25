from stag.core.cuts import (
    cut_node_ids,
    cut_transition_ids,
    inactive_node_ids,
    inactive_transition_ids,
    is_active_node,
    is_inactive_transition,
)
from stag.core.run_graph import RunGraph
from stag.core.schema.graph import Edge, Node, Transition
from stag.core.schema.payloads import CutPayload


def _graph() -> RunGraph:
    graph = RunGraph()
    for node_id in ("n_a", "n_b", "n_c"):
        graph.add_node(Node(node_id=node_id))
    for transition_id in ("t_1", "t_2"):
        graph.add_transition(Transition(transition_id=transition_id))
    graph.add_edge(Edge("e_1", "node", "n_a", "transition", "t_1"))
    graph.add_edge(Edge("e_2", "transition", "t_1", "node", "n_b"))
    graph.add_edge(Edge("e_3", "node", "n_b", "transition", "t_2"))
    graph.add_edge(Edge("e_4", "transition", "t_2", "node", "n_c"))
    return graph


def test_transition_cut_marks_downstream_inactive():
    graph = _graph()
    graph.attach_payload(
        CutPayload("pl_cut", target_kind="transition", target_id="t_1", cut_at="now")
    )

    assert cut_transition_ids(graph) == {"t_1"}
    assert inactive_transition_ids(graph) == {"t_1", "t_2"}
    assert inactive_node_ids(graph) == {"n_b", "n_c"}
    assert is_inactive_transition(graph, "t_1")
    assert not is_active_node(graph, "n_b")


def test_node_cut_marks_downstream_inactive():
    graph = _graph()
    graph.attach_payload(CutPayload("pl_cut", target_kind="node", target_id="n_b", cut_at="now"))

    assert cut_node_ids(graph) == {"n_b"}
    assert inactive_transition_ids(graph) == {"t_2"}
    assert inactive_node_ids(graph) == {"n_b", "n_c"}
    assert is_active_node(graph, "n_a")
