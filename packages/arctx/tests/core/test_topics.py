"""Tests for derived topics (arctx.core.topics)."""

from __future__ import annotations

import arctx
from arctx.core.schema.payloads import NodePayload, StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.core.topics import (
    list_topics,
    topic_names,
    topic_summary_history,
    topic_view,
)


def _handle():
    return arctx.init(
        Requirement(requirement_id="r", target_type="task", target_id="t"),
        run_id="run_topics",
    )


def _step(handle, from_node, title="work"):
    return handle.add_step(
        [from_node], StepPayload(payload_id="_", target_id="_", type="step", content={"title": title})
    )


def _tag(handle, record_id, topic, *, kind="node", note=None):
    content = {"topic": topic}
    if note:
        content["note"] = note
    if kind == "node":
        handle.attach(
            record_id,
            NodePayload(payload_id="_", target_id="_", type="tag", content=content),
        )
    else:
        # Step targets attach directly, mirroring the CLI attach path.
        handle.run_graph.attach_payload(
            StepPayload(
                payload_id=f"pl_tag_{record_id}",
                target_id=record_id,
                type="tag",
                content=content,
            )
        )


def test_topic_islands_follow_lineage_not_mere_connectivity():
    handle = _handle()
    root = handle.root_node_id
    # Two sibling branches from root: they share an ancestor but neither
    # derives from the other — that is two islands ("same subject, independent
    # lineages"), the join-candidate signal.
    a = _step(handle, root).output_node_id
    b = _step(handle, root).output_node_id
    _tag(handle, a, "gather")
    _tag(handle, b, "gather")
    view = topic_view(handle.run_graph, "gather")
    assert len(view.islands) == 2

    # A tagged descendant of `a` merges into a's island (lineage relation).
    child = _step(handle, a).output_node_id
    _tag(handle, child, "gather")
    view = topic_view(handle.run_graph, "gather")
    assert len(view.islands) == 2
    assert {tuple(sorted(i)) for i in view.islands} == {
        tuple(sorted((a, child))),
        (b,),
    }

    # Joining both branches with a multi-input step and tagging the join
    # merges everything into one island.
    join = handle.add_step(
        [a, b], StepPayload(payload_id="_", target_id="_", type="integration")
    )
    _tag(handle, join.output_node_id, "gather")
    view = topic_view(handle.run_graph, "gather")
    assert len(view.islands) == 1

    # Cut records leave the islands and are reported separately.
    handle.cut(join.step_id, target_kind="step", reason="undo the join")
    producer_b = handle.run_graph.producers_of(b)[0]
    handle.cut(producer_b, target_kind="step", reason="dead end")
    view = topic_view(handle.run_graph, "gather")
    assert len(view.islands) == 1  # a + child (join output is inactive now)
    assert set(view.inactive) == {b, join.output_node_id}


def test_topic_summary_latest_wins():
    handle = _handle()
    root = handle.root_node_id
    node = _step(handle, root).output_node_id
    handle.attach(
        node,
        NodePayload(
            payload_id="_", target_id="_", type="topic_summary",
            content={"topic": "tile", "text": "old belief"},
        ),
    )
    handle.attach(
        node,
        NodePayload(
            payload_id="_", target_id="_", type="topic_summary",
            content={"topic": "tile", "text": "new belief", "sources": [node]},
        ),
    )
    view = topic_view(handle.run_graph, "tile")
    assert view.summary is not None
    assert view.summary.text == "new belief"
    assert view.summary.sources == (node,)


def test_topic_names_and_overview():
    handle = _handle()
    root = handle.root_node_id
    a = _step(handle, root).output_node_id
    _tag(handle, a, "first")
    handle.attach(
        a,
        NodePayload(
            payload_id="_", target_id="_", type="topic_summary",
            content={"topic": "second", "text": "statement only, no tags"},
        ),
    )
    assert topic_names(handle.run_graph) == ["first", "second"]
    views = {view.name: view for view in list_topics(handle.run_graph)}
    assert len(views["first"].islands) == 1
    assert views["second"].islands == ()
    assert views["second"].summary.text == "statement only, no tags"


def test_tagging_a_step_counts_too():
    handle = _handle()
    root = handle.root_node_id
    step = _step(handle, root)
    _tag(handle, step.step_id, "method", kind="step", note="works well")
    view = topic_view(handle.run_graph, "method")
    assert view.islands == ((step.step_id,),)
    assert view.records[0].kind == "step"
    assert view.records[0].note == "works well"


def test_topic_summary_history_walks_oldest_to_current():
    from arctx.core.topics import topic_summary_history

    handle = _handle()
    root = handle.root_node_id
    node = _step(handle, root).output_node_id
    for text in ("first belief", "second belief", "third belief"):
        handle.attach(
            node,
            NodePayload(
                payload_id="_", target_id="_", type="topic_summary",
                content={"topic": "evolve", "text": text},
            ),
            user_id="u",
            lane_id="lane_x",
        )
    history = topic_summary_history(handle.run_graph, "evolve")
    assert [entry.text for entry in history] == [
        "first belief", "second belief", "third belief",
    ]
    assert history[-1].created_at is not None
    assert history[-1].user_id == "u"
    view = topic_view(handle.run_graph, "evolve")
    assert view.summary.text == "third belief"


# ---------------------------------------------------------------------------
# untag — append-only supersession on the (topic, record) pair
# ---------------------------------------------------------------------------


def _untag(handle, record_id, topic):
    handle.attach(
        record_id,
        NodePayload(
            payload_id="_", target_id="_", type="untag", content={"topic": topic}
        ),
    )


def test_untag_removes_membership_and_retag_brings_it_back():
    handle = _handle()
    a = _step(handle, handle.root_node_id).output_node_id
    b = _step(handle, a).output_node_id
    _tag(handle, a, "tiling")
    _tag(handle, b, "tiling")
    assert len(topic_view(handle.run_graph, "tiling").records) == 2

    _untag(handle, b, "tiling")
    view = topic_view(handle.run_graph, "tiling")
    assert [r.record_id for r in view.records] == [a]
    # The record itself is untouched — untag is not cut.
    assert b in handle.run_graph.nodes

    _tag(handle, b, "tiling")
    assert len(topic_view(handle.run_graph, "tiling").records) == 2


def test_untag_is_scoped_to_one_topic():
    handle = _handle()
    a = _step(handle, handle.root_node_id).output_node_id
    _tag(handle, a, "tiling")
    _tag(handle, a, "bench")

    _untag(handle, a, "tiling")

    assert topic_view(handle.run_graph, "tiling").records == ()
    assert [r.record_id for r in topic_view(handle.run_graph, "bench").records] == [a]


def test_island_tips_are_the_frontier_of_each_island():
    from arctx.core.topics import island_tips, record_output_node

    handle = _handle()
    root = handle.root_node_id
    a1 = _step(handle, root).output_node_id
    a2 = _step(handle, a1).output_node_id
    b1 = _step(handle, root).output_node_id
    for record_id in (a1, a2, b1):
        _tag(handle, record_id, "tiling")

    view = topic_view(handle.run_graph, "tiling")
    assert len(view.islands) == 2
    tips = [island_tips(handle.run_graph, island) for island in view.islands]
    assert tips == [(a2,), (b1,)]
    # A node stands for itself when used as a step input.
    assert record_output_node(handle.run_graph, a2) == a2


def test_joining_islands_requires_tagging_the_new_node():
    """The rule `topic join` exists to encode: a Step alone does not merge."""
    handle = _handle()
    root = handle.root_node_id
    a = _step(handle, root).output_node_id
    b = _step(handle, root).output_node_id
    _tag(handle, a, "tiling")
    _tag(handle, b, "tiling")
    assert len(topic_view(handle.run_graph, "tiling").islands) == 2

    joined = handle.add_step(
        [a, b], StepPayload(payload_id="_", target_id="_", type="topic_join")
    )
    # Still two islands: a and b remain mutually unreachable.
    assert len(topic_view(handle.run_graph, "tiling").islands) == 2

    _tag(handle, joined.output_node_id, "tiling")
    assert len(topic_view(handle.run_graph, "tiling").islands) == 1


def test_island_members_are_listed_oldest_first():
    """An island reads as a lineage, so tag order must not decide the order."""
    handle = _handle()
    a1 = _step(handle, handle.root_node_id).output_node_id
    a2 = _step(handle, a1).output_node_id
    a3 = _step(handle, a2).output_node_id
    # Tagged newest-first, on purpose.
    for record_id in (a3, a1, a2):
        _tag(handle, record_id, "tiling")

    (island,) = topic_view(handle.run_graph, "tiling").islands
    assert island == (a1, a2, a3)


# ---------------------------------------------------------------------------
# Which island a statement speaks for
# ---------------------------------------------------------------------------


def _summarize(handle, node_id, topic, text, sources=()):
    handle.attach(
        node_id,
        NodePayload(
            payload_id="_",
            target_id="_",
            type="topic_summary",
            content={"topic": topic, "text": text, "sources": list(sources)},
        ),
    )


def test_statement_islands_separates_one_lineage_from_a_reconciliation():
    from arctx.core.topics import island_statements, statement_islands

    handle = _handle()
    root = handle.root_node_id
    a = _step(handle, root).output_node_id
    b = _step(handle, root).output_node_id
    _tag(handle, a, "tiling")
    _tag(handle, b, "tiling")
    view = topic_view(handle.run_graph, "tiling")
    assert len(view.islands) == 2

    # Written on island 1's own node: it speaks for that lineage alone.
    _summarize(handle, a, "tiling", "island 1 の結論")
    history = topic_summary_history(handle.run_graph, "tiling")
    assert statement_islands(handle.run_graph, view.islands, history[-1]) == frozenset({0})

    # Citing both sides: the subject was reconciled in prose.
    _summarize(handle, root, "tiling", "両方をまとめた結論", sources=(a, b))
    per_island, reconciling = island_statements(handle.run_graph, "tiling")
    assert reconciling is not None and reconciling.text == "両方をまとめた結論"
    assert per_island[0] is not None and per_island[0].text == "island 1 の結論"
    assert per_island[1] is None


def test_statement_islands_is_empty_when_nothing_anchors_it():
    from arctx.core.topics import statement_islands

    handle = _handle()
    root = handle.root_node_id
    a = _step(handle, root).output_node_id
    b = _step(handle, root).output_node_id
    _tag(handle, a, "tiling")
    _tag(handle, b, "tiling")
    # Attached to the root, which no tagged record descends from.
    _summarize(handle, root, "tiling", "どこの話でもない")
    view = topic_view(handle.run_graph, "tiling")
    history = topic_summary_history(handle.run_graph, "tiling")
    assert statement_islands(handle.run_graph, view.islands, history[-1]) == frozenset()
