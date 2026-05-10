"""RunHandle.cut implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from optagent.core.cuts import cut_input_transition_ids, cut_output_transition_ids
from optagent.core.schema.payloads import CutPayload


def cut_impl(
    self,
    target_id: str,
    *,
    target_kind: Literal["input_transition", "output_transition"],
    reason: str | None = None,
    user_id: str | None = None,
) -> CutPayload:
    """Append a CutPayload to mark an InputTransition or OutputTransition as inactive.

    - input_transition: the entire plan and all its outputs become inactive.
    - output_transition: only that output (and its downstream nodes) becomes inactive.
    """
    if target_kind == "input_transition":
        if target_id not in self.run_graph.input_transitions:
            raise KeyError(f"unknown input_transition_id: {target_id}")
        if target_id in cut_input_transition_ids(self.run_graph):
            raise ValueError(f"input_transition already cut: {target_id}")
    elif target_kind == "output_transition":
        if target_id not in self.run_graph.output_transitions:
            raise KeyError(f"unknown output_transition_id: {target_id}")
        if target_id in cut_output_transition_ids(self.run_graph):
            raise ValueError(f"output_transition already cut: {target_id}")
    else:
        raise ValueError(f"invalid target_kind: {target_kind!r}")

    cut = CutPayload(
        payload_id=self._next_id("pl"),
        target_id=target_id,
        target_kind=target_kind,
        cut_at=datetime.now(timezone.utc).isoformat(),
        reason=reason,
        user_id=user_id,
    )
    self.run_graph.attach_payload(cut)
    return cut
