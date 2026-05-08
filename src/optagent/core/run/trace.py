"""RunHandle.trace implementation."""

from __future__ import annotations

from optagent.core.schema.payloads import NotePayload, ResultPayload, PredictionPayload
from optagent.core.schema.snapshots import TraceContext


def trace_impl(
    self,
    node_id: str,
    *,
    view: str = "main",
    depth: int | None = None,
    include_predictions: bool = False,
    include_raw_refs: bool = True,
) -> TraceContext:
    """Walk observed history backwards from a node.

    Traverses: node → incoming OT(s) → their IT → IT's input nodes → repeat.
    Only follows OutputTransitions that carry a ResultPayload (observed).
    """
    if node_id not in self.run_graph.nodes:
        raise KeyError(f"unknown node_id: {node_id}")

    remaining = depth
    cursor = node_id
    past_node_ids: list[str] = []
    output_transition_ids: list[str] = []
    input_transition_ids: list[str] = []
    result_payload_ids: list[str] = []
    prediction_ot_ids: list[str] = []
    note_payload_ids: list[str] = []
    artifact_refs: list[str] = []

    # Collect notes on start node
    for payload in self.run_graph.payloads_for_node(cursor):
        if isinstance(payload, NotePayload):
            note_payload_ids.append(payload.payload_id)

    while remaining is None or remaining > 0:
        incoming_ots = self.run_graph.output_transitions_to_node.get(cursor, [])
        # Find the observed OT (ResultPayload) among incoming ones
        observed_ot = None
        for ot_id in reversed(incoming_ots):
            ot = self.run_graph.output_transitions[ot_id]
            ot_payloads = self.run_graph.payloads_for_output_transition(ot_id)
            has_result = any(isinstance(p, ResultPayload) for p in ot_payloads)
            if has_result:
                observed_ot = ot
                break

        if observed_ot is None:
            break

        output_transition_ids.append(observed_ot.output_transition_id)

        # Collect result payload info
        for payload in self.run_graph.payloads_for_output_transition(
            observed_ot.output_transition_id
        ):
            if isinstance(payload, ResultPayload):
                result_payload_ids.append(payload.payload_id)
                if include_raw_refs:
                    artifact_refs.extend(payload.artifacts)
                    artifact_refs.extend(payload.raw_outputs)
                    artifact_refs.extend(payload.logs)

        # Go to the IT
        it = self.run_graph.input_transitions[observed_ot.input_transition_id]
        input_transition_ids.append(it.input_transition_id)

        if include_predictions:
            for ot_id in self.run_graph.output_transitions_from_it.get(
                it.input_transition_id, ()
            ):
                ot_payloads = self.run_graph.payloads_for_output_transition(ot_id)
                if any(isinstance(p, PredictionPayload) for p in ot_payloads):
                    prediction_ot_ids.append(ot_id)

        # Walk to input nodes (take the first one as the "parent")
        if not it.input_node_ids:
            break
        parent_node_id = it.input_node_ids[0]
        past_node_ids.append(parent_node_id)

        # Collect notes on the parent node
        for payload in self.run_graph.payloads_for_node(parent_node_id):
            if isinstance(payload, NotePayload):
                note_payload_ids.append(payload.payload_id)

        cursor = parent_node_id
        if remaining is not None:
            remaining -= 1

    return TraceContext(
        current_node_id=node_id,
        past_node_ids=tuple(past_node_ids),
        output_transition_ids=tuple(output_transition_ids),
        input_transition_ids=tuple(input_transition_ids),
        result_payload_ids=tuple(result_payload_ids),
        prediction_output_transition_ids=tuple(prediction_ot_ids),
        note_payload_ids=tuple(note_payload_ids),
        artifact_refs=tuple(artifact_refs),
    )
