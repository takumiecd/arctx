"""Tests for read-time lineage queries (arctx.core.lineage)."""

from __future__ import annotations

from arctx import init
from arctx.core.lineage import history_nodes, is_visible_from, relationship
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement


def _req() -> Requirement:
    return Requirement(requirement_id="r", target_type="task", target_id="t")


def _sp() -> StepPayload:
    return StepPayload(payload_id="_", target_id="_", type="experiment")


def _build():
    """Build:

        root --t1--> n1 --t3--> n3
        root --t2--> n2          (sibling branch)
    """
    run = init(_req())
    root = run.root_node_id
    t1 = run.add_step([root], _sp())
    n1 = t1.output_node_id
    t2 = run.add_step([root], _sp())
    n2 = t2.output_node_id
    t3 = run.add_step([n1], _sp())
    n3 = t3.output_node_id
    return run, root, n1, n2, n3, t1.step_id, t2.step_id, t3.step_id


class TestRelationshipNodes:
    def test_ancestor_and_descendant(self):
        run, root, n1, _n2, n3, *_ = _build()
        g = run.run_graph
        assert relationship(g, ("node", n1), ("node", n3)) == "ancestor"
        assert relationship(g, ("node", n3), ("node", n1)) == "descendant"
        assert relationship(g, ("node", root), ("node", n3)) == "ancestor"

    def test_same(self):
        run, _root, n1, *_ = _build()
        assert relationship(run.run_graph, ("node", n1), ("node", n1)) == "same"

    def test_siblings_unrelated(self):
        run, _root, n1, n2, *_ = _build()
        assert relationship(run.run_graph, ("node", n1), ("node", n2)) == "unrelated"


class TestRelationshipSteps:
    def test_step_is_ancestor_of_its_output_and_downstream(self):
        run, _root, n1, _n2, n3, t1, _t2, _t3 = _build()
        g = run.run_graph
        assert relationship(g, ("step", t1), ("node", n1)) == "ancestor"
        assert relationship(g, ("step", t1), ("node", n3)) == "ancestor"

    def test_node_visible_to_consuming_step(self):
        run, _root, n1, _n2, _n3, _t1, _t2, t3 = _build()
        # n1 is an input of t3 -> n1 is an ancestor of t3
        assert relationship(run.run_graph, ("node", n1), ("step", t3)) == "ancestor"

    def test_step_to_step(self):
        run, _root, _n1, _n2, _n3, t1, t2, t3 = _build()
        g = run.run_graph
        assert relationship(g, ("step", t1), ("step", t3)) == "ancestor"
        assert relationship(g, ("step", t3), ("step", t1)) == "descendant"
        assert relationship(g, ("step", t1), ("step", t2)) == "unrelated"


class TestVisibility:
    def test_parents_visible_children_not(self):
        run, root, n1, n2, n3, *_ = _build()
        g = run.run_graph
        # From n3: ancestor (n1, root) and self visible; sibling/child not.
        assert is_visible_from(g, ("node", n1), ("node", n3)) is True
        assert is_visible_from(g, ("node", root), ("node", n3)) is True
        assert is_visible_from(g, ("node", n3), ("node", n3)) is True
        assert is_visible_from(g, ("node", n3), ("node", n1)) is False  # child
        assert is_visible_from(g, ("node", n2), ("node", n3)) is False  # sibling

    def test_join_makes_both_parents_visible(self):
        run, _root, n1, n2, _n3, *_ = _build()
        join = run.add_step([n1, n2], _sp())
        n_join = join.output_node_id
        g = run.run_graph
        assert is_visible_from(g, ("node", n1), ("node", n_join)) is True
        assert is_visible_from(g, ("node", n2), ("node", n_join)) is True


class TestHistoryNodes:
    def test_node_history_inclusive(self):
        run, root, n1, _n2, n3, *_ = _build()
        assert history_nodes(run.run_graph, ("node", n3)) == {n3, n1, root}

    def test_step_history_excludes_own_output(self):
        run, root, n1, _n2, _n3, _t1, _t2, t3 = _build()
        # t3 consumes n1; it sees n1 and root but not its own output n3.
        assert history_nodes(run.run_graph, ("step", t3)) == {n1, root}
