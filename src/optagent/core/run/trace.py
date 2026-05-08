"""RunHandle.trace implementation."""

from __future__ import annotations

from collections import deque

from optagent.core.cuts import is_inactive_output_transition
from optagent.core.schema.payloads import NotePayload, PredictionPayload, ResultPayload
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
    """Walk observed history backwards from a node via BFS.

    Traverses all incoming active observed OTs, follows their ITs, and
    enqueues all input_node_ids (supporting multi-input ITs). Stops after
    ``depth`` backward steps if given. Inactive OTs are skipped.
    """
    if node_id not in self.run_graph.nodes:
        raise KeyError(f"unknown node_id: {node_id}")

    past_node_ids: set[str] = set()
    output_transition_ids: list[str] = []
    input_transition_ids: list[str] = []
    result_payload_ids: list[str] = []
    prediction_ot_ids: list[str] = []
    note_payload_ids: list[str] = []
    artifact_refs_seen: dict[str, None] = {}

    # Collect notes on start node
    for payload in self.run_graph.payloads_for_node(node_id):
        if isinstance(payload, NotePayload):
            note_payload_ids.append(payload.payload_id)

    # BFS: each queue entry is (node_id, steps_remaining)
    # steps_remaining = None means unlimited; 0 means stop before processing
    queue: deque[tuple[str, int | None]] = deque()
    queue.append((node_id, depth))
    visited_nodes: set[str] = {node_id}

    while queue:
        current, remaining = queue.popleft()

        if remaining is not None and remaining <= 0:
            continue

        incoming_ots = self.run_graph.output_transitions_to_node.get(current, [])

        for ot_id in incoming_ots:
            if is_inactive_output_transition(self.run_graph, ot_id):
                continue
            ot = self.run_graph.output_transitions[ot_id]
            ot_payloads = self.run_graph.payloads_for_output_transition(ot_id)
            has_result = any(isinstance(p, ResultPayload) for p in ot_payloads)
            if not has_result:
                continue

            output_transition_ids.append(ot_id)

            for payload in ot_payloads:
                if isinstance(payload, ResultPayload):
                    result_payload_ids.append(payload.payload_id)
                    if include_raw_refs:
                        for ref in payload.artifacts:
                            artifact_refs_seen[ref] = None
                        for ref in payload.raw_outputs:
                            artifact_refs_seen[ref] = None
                        for ref in payload.logs:
                            artifact_refs_seen[ref] = None

            it = self.run_graph.input_transitions[ot.input_transition_id]
            input_transition_ids.append(it.input_transition_id)

            if include_predictions:
                for pred_ot_id in self.run_graph.output_transitions_from_it.get(
                    it.input_transition_id, ()
                ):
                    pred_payloads = self.run_graph.payloads_for_output_transition(pred_ot_id)
                    if any(isinstance(p, PredictionPayload) for p in pred_payloads):
                        prediction_ot_ids.append(pred_ot_id)

            next_remaining = None if remaining is None else remaining - 1
            for parent_id in it.input_node_ids:
                if parent_id in visited_nodes:
                    continue
                visited_nodes.add(parent_id)
                past_node_ids.add(parent_id)

                for payload in self.run_graph.payloads_for_node(parent_id):
                    if isinstance(payload, NotePayload):
                        note_payload_ids.append(payload.payload_id)

                queue.append((parent_id, next_remaining))

    return TraceContext(
        current_node_id=node_id,
        past_node_ids=tuple(sorted(past_node_ids)),
        output_transition_ids=tuple(sorted(set(output_transition_ids))),
        input_transition_ids=tuple(sorted(set(input_transition_ids))),
        result_payload_ids=tuple(sorted(set(result_payload_ids))),
        prediction_output_transition_ids=tuple(sorted(set(prediction_ot_ids))),
        note_payload_ids=tuple(sorted(set(note_payload_ids))),
        artifact_refs=tuple(artifact_refs_seen.keys()),
    )
