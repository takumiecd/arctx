"""RunHandle.observe implementation."""

from __future__ import annotations

from optagent.core.schema.graph import Node, OutputTransition
from optagent.core.schema.payloads import ResultPayload


def observe_impl(
    self,
    input_transition_id: str,
    result: ResultPayload,
    *,
    view: str = "main",
    user_id: str | None = None,
) -> OutputTransition:
    """Record an observed OutputTransition for an InputTransition.

    Creates a new output node and attaches the ResultPayload to the
    new OutputTransition. The payload marks this OT as an observed result.
    """
    if input_transition_id not in self.run_graph.input_transitions:
        raise KeyError(f"unknown input_transition_id: {input_transition_id}")

    new_node = Node(node_id=self._next_id("n"))
    self.run_graph.add_node(new_node)

    ot = OutputTransition(
        output_transition_id=self._next_id("ot"),
        input_transition_id=input_transition_id,
        to_node_id=new_node.node_id,
        metadata={**({"user_id": user_id} if user_id is not None else {})},
    )
    self.run_graph.add_output_transition(ot)

    result_payload = ResultPayload(
        payload_id=self._next_id("pl"),
        target_id=ot.output_transition_id,
        status=result.status,
        artifacts=result.artifacts,
        raw_outputs=result.raw_outputs,
        logs=result.logs,
        metrics=dict(result.metrics),
        errors=result.errors,
        actual_cost=dict(result.actual_cost),
        matched_prediction_output_id=result.matched_prediction_output_id,
        metadata=dict(result.metadata),
    )
    self.run_graph.attach_payload(result_payload)

    v = self._get_view(view)
    v.node_ids.add(new_node.node_id)
    v.output_transition_ids.add(ot.output_transition_id)
    v.payload_ids.add(result_payload.payload_id)
    return ot
