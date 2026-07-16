"""RunHandle LanePayload attachment implementation."""

from __future__ import annotations

from arctx.core.schema.payloads import LanePayload


def attach_lane_impl(
    self,
    lane_id: str,
    payload: LanePayload,
    *,
    user_id: str | None,
) -> LanePayload:
    """Append information to a Lane and record its provenance.

    Lane payloads remain writable while a lane is closed: a summary or note is
    descriptive metadata, not an extension of the observed Node/Step history.
    """
    if user_id is None:
        raise ValueError("user_id is required to attach a lane payload")
    if lane_id not in self.run_graph.lanes:
        raise KeyError(f"unknown lane: {lane_id}")
    if payload.target_kind != "lane":
        raise ValueError(
            "attach_lane requires a lane-targeting payload "
            f"(target_kind='lane'), got {payload.target_kind!r}"
        )
    if payload.target_id not in ("", "pending", lane_id):
        raise ValueError(
            f"payload target_id {payload.target_id!r} does not match lane {lane_id!r}"
        )

    attached = LanePayload(
        payload_id=payload.payload_id,
        target_id=lane_id,
        type=payload.type,
        content=dict(payload.content),
        metadata=dict(payload.metadata),
    )
    self.run_graph.attach_payload(attached)
    event = self.record_work_event(
        user_id=user_id,
        lane_id=lane_id,
        event_type="lane_payload_attached",
        target_kind="lane",
        target_id=lane_id,
        created_records=(attached.payload_id,),
        summary=f"lane {attached.type}",
        data={"payload_id": attached.payload_id, "type": attached.type},
    )
    if event is None:  # defensive: user and lane were validated above.
        raise RuntimeError("failed to record lane payload event")
    return attached
