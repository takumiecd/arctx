"""RunHandle.observe implementation."""

from __future__ import annotations

from optagent.core.cuts import is_inactive_input_transition, is_inactive_output_transition
from optagent.core.schema.graph import Node, OutputTransition
from optagent.core.schema.payloads import PredictionPayload, ResultPayload


def observe_impl(
    self,
    input_transition_id: str,
    result: ResultPayload,
    *,
    user_id: str | None = None,
) -> OutputTransition:
    """Record an observed OutputTransition for an InputTransition.

    Creates a new output node and attaches the ResultPayload to the
    new OutputTransition. The payload marks this OT as an observed result.
    """
    if input_transition_id not in self.run_graph.input_transitions:
        raise KeyError(f"unknown input_transition_id: {input_transition_id}")
    if is_inactive_input_transition(self.run_graph, input_transition_id):
        raise ValueError(
            f"input_transition is inactive (cut or in cut subtree): {input_transition_id}"
        )

    if result.matched_prediction_output_id is not None:
        mpid = result.matched_prediction_output_id
        if mpid not in self.run_graph.output_transitions:
            raise KeyError(f"unknown matched_prediction_output_id: {mpid}")
        pred_payloads = self.run_graph.payloads_for_output_transition(mpid)
        if not any(isinstance(p, PredictionPayload) for p in pred_payloads):
            raise ValueError(
                f"matched_prediction_output_id does not point to a prediction: {mpid}"
            )
        matched_ot = self.run_graph.output_transitions[mpid]
        if matched_ot.input_transition_id != input_transition_id:
            raise ValueError(
                f"matched_prediction_output_id belongs to a different input_transition: {mpid}"
            )
        if is_inactive_output_transition(self.run_graph, mpid):
            raise ValueError(f"matched_prediction_output_id is inactive: {mpid}")

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
    return ot
