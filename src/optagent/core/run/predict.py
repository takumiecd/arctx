"""RunHandle.predict implementation."""

from __future__ import annotations

from optagent.core.schema.graph import Node, OutputTransition
from optagent.core.schema.payloads import PredictionPayload


def predict_impl(
    self,
    input_transition_id: str,
    *,
    view: str = "main",
    payloads: list[PredictionPayload] | None = None,
    max_outcomes: int | None = None,
    user_id: str | None = None,
) -> list[OutputTransition]:
    """Create one or more predicted OutputTransitions for an InputTransition.

    Each OutputTransition gets a new output node and a PredictionPayload.
    The payload distinguishes these OTs as predictions (vs. observed results).
    """
    if input_transition_id not in self.run_graph.input_transitions:
        raise KeyError(f"unknown input_transition_id: {input_transition_id}")

    count = max(1, max_outcomes or 1)
    template_payloads = list(payloads or [])

    output_transitions: list[OutputTransition] = []
    for index in range(count):
        new_node = Node(node_id=self._next_id("n"))
        self.run_graph.add_node(new_node)

        ot = OutputTransition(
            output_transition_id=self._next_id("ot"),
            input_transition_id=input_transition_id,
            to_node_id=new_node.node_id,
            metadata={"ordinal": index},
        )
        self.run_graph.add_output_transition(ot)

        if index < len(template_payloads):
            tmpl = template_payloads[index]
            pred_payload = PredictionPayload(
                payload_id=self._next_id("pl"),
                target_id=ot.output_transition_id,
                predicted_artifacts=tmpl.predicted_artifacts,
                predicted_metrics=dict(tmpl.predicted_metrics),
                rationale=tmpl.rationale,
                confidence=tmpl.confidence,
                predictor=tmpl.predictor,
                metadata=dict(tmpl.metadata),
            )
        else:
            pred_payload = PredictionPayload(
                payload_id=self._next_id("pl"),
                target_id=ot.output_transition_id,
                metadata={"ordinal": index},
            )
        self.run_graph.attach_payload(pred_payload)

        v = self._get_view(view)
        v.node_ids.add(new_node.node_id)
        v.output_transition_ids.add(ot.output_transition_id)
        v.payload_ids.add(pred_payload.payload_id)
        output_transitions.append(ot)

    return output_transitions
