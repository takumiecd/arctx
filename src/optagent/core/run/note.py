"""RunHandle.note implementation."""

from __future__ import annotations

from optagent.core.schema.payloads import NotePayload


def note_impl(
    self,
    node_id: str,
    text: str,
    *,
    tags: list[str] | tuple[str, ...] = (),
    view: str = "main",
    user_id: str | None = None,
) -> NotePayload:
    """Attach a lightweight memo to a node."""
    if node_id not in self.run_graph.nodes:
        raise KeyError(f"unknown node_id: {node_id}")

    payload = NotePayload(
        payload_id=self._next_id("pl"),
        target_id=node_id,
        text=text,
        author=user_id,
        tags=tuple(tags),
    )
    self.run_graph.attach_payload(payload)
    v = self._get_view(view)
    v.payload_ids.add(payload.payload_id)
    return payload
