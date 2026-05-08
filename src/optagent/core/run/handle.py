"""Run handle definition and initialization."""

from __future__ import annotations

from dataclasses import dataclass, field

from optagent.core.cuts import is_active_node
from optagent.core.graph_view import GraphView
from optagent.core.ids import sequential_id, slugify, timestamp_id
from optagent.core.run_graph import RunGraph
from optagent.core.schema.graph import Node
from optagent.core.schema.requirements import Requirement


@dataclass
class RunHandle:
    """In-memory handle for one optimization/problem-solving run."""

    run_id: str
    requirement: Requirement
    run_graph: RunGraph
    views: dict[str, GraphView] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)

    def _next_id(self, prefix: str) -> str:
        self._counters[prefix] = self._counters.get(prefix, 0) + 1
        return sequential_id(prefix, self._counters[prefix])

    @property
    def root_node_id(self) -> str:
        return "n_0000"

    def _ensure_active_node(self, node_id: str) -> None:
        """Reject node IDs that are unknown or sit inside a cut subtree."""
        if node_id not in self.run_graph.nodes:
            raise KeyError(f"unknown node_id: {node_id}")
        if not is_active_node(self.run_graph, node_id):
            raise ValueError(
                f"node is in a cut (inactive) branch: {node_id}; "
                "no new plans or observations can extend it"
            )

    def _get_view(self, name: str) -> GraphView:
        if name not in self.views:
            raise KeyError(f"unknown view: {name!r}")
        return self.views[name]

    def save(self, store) -> object:
        return store.save_run(self)


def init(requirement: Requirement, *, run_id: str | None = None) -> RunHandle:
    """Create a new in-memory run with a seeded RunGraph and 'main' GraphView."""

    rid = run_id or timestamp_id(f"run_{slugify(requirement.requirement_id)}")

    graph = RunGraph()
    root = Node(node_id="n_0000")
    graph.add_node(root)

    main_view = GraphView(
        view_id="view_main",
        name="main",
        root_node_ids=(root.node_id,),
        node_ids={root.node_id},
    )

    handle = RunHandle(
        run_id=rid,
        requirement=requirement,
        run_graph=graph,
        views={"main": main_view},
        _counters={
            "n": 0,
            "it": 0,
            "ot": 0,
            "pl": 0,
        },
    )
    return handle


# Bind verb implementations.
from optagent.core.run.plan import plan_impl as _plan_impl  # noqa: E402
from optagent.core.run.note import note_impl as _note_impl  # noqa: E402
from optagent.core.run.observe import observe_impl as _observe_impl  # noqa: E402
from optagent.core.run.predict import predict_impl as _predict_impl  # noqa: E402
from optagent.core.run.rewind import rewind_impl as _rewind_impl  # noqa: E402
from optagent.core.run.trace import trace_impl as _trace_impl  # noqa: E402
from optagent.core.run.view import (  # noqa: E402
    view_create_impl as _view_create_impl,
    view_list_impl as _view_list_impl,
    view_merge_impl as _view_merge_impl,
    view_show_impl as _view_show_impl,
)

RunHandle.plan = _plan_impl
RunHandle.note = _note_impl
RunHandle.observe = _observe_impl
RunHandle.result = _observe_impl
RunHandle.predict = _predict_impl
RunHandle.rewind = _rewind_impl
RunHandle.trace = _trace_impl
RunHandle.history = _trace_impl
RunHandle.view_create = _view_create_impl
RunHandle.view_list = _view_list_impl
RunHandle.view_show = _view_show_impl
RunHandle.view_merge = _view_merge_impl
