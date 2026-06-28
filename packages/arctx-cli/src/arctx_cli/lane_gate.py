"""Guard that refuses writes to a closed lane.

A lane's lifecycle is open → closed → (reopen) open. "Closed" only means
something if writes respect it: once a lane is closed, ``add`` / ``attach`` /
``asset attach`` / ``git add`` and friends refuse to append to it until it is
explicitly reopened with ``arctx lane open`` (or the caller passes ``--force``).
"""

from __future__ import annotations


def ensure_lane_open(handle, lane_id: str | None, *, force: bool = False) -> None:
    """Raise if *lane_id* names a closed lane, unless *force* is set.

    No-op when *lane_id* is falsy (no lane context) or unknown — those are the
    pre-existing default/lane-less write paths and are not this guard's business.
    """
    if not lane_id or force:
        return
    lane = handle.run_graph.lanes.get(lane_id)
    if lane is not None and getattr(lane, "status", "open") == "closed":
        raise ValueError(
            f"lane is closed: {lane_id}; reopen it with "
            f"`arctx lane open {lane_id}` (or pass --force to write anyway)"
        )
