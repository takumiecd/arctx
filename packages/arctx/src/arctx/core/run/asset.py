"""RunHandle.attach_asset implementation.

Copies a file into the run's ``artifacts/`` directory and attaches a core
:class:`~arctx.core.schema.payloads.AssetPayload` to a Node or Step.
"""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from arctx.core.schema.payloads import AssetPayload
from arctx.paths import runs_dir

if TYPE_CHECKING:
    from arctx.core.run.handle import RunHandle


def attach_asset_impl(
    self: "RunHandle",
    target_id: str,
    file_path: str | Path,
    *,
    user_id: str | None = None,
    work_session_id: str | None = None,
) -> AssetPayload:
    """Copy *file_path* into the run and attach an AssetPayload to *target_id*."""
    if target_id in self.run_graph.nodes:
        target_kind = "node"
    elif target_id in self.run_graph.steps:
        target_kind = "step"
    else:
        raise KeyError(f"unknown target_id: {target_id}")

    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"file not found: {file_path}")

    asset_id = self._next_id("ast")
    filename = file_path.name
    mime_type, _ = mimetypes.guess_type(filename)
    if not mime_type:
        mime_type = "application/octet-stream"
    size_bytes = file_path.stat().st_size

    artifacts_dir = runs_dir() / self.run_id / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    dest_filename = f"{asset_id}_{filename}"
    shutil.copy2(file_path, artifacts_dir / dest_filename)

    payload = AssetPayload(
        payload_id=self._next_id("pl"),
        target_id=target_id,
        target_kind=target_kind,  # type: ignore[arg-type]
        asset_id=asset_id,
        filename=filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        path=f"artifacts/{dest_filename}",
    )

    if target_kind == "node":
        return self.attach(
            target_id, payload, user_id=user_id, work_session_id=work_session_id
        )

    self.run_graph.attach_payload(payload)
    self.record_work_event(
        user_id=user_id,
        work_session_id=work_session_id,
        event_type="payload_attached",
        target_kind="step",
        target_id=target_id,
        created_records=(payload.payload_id,),
        summary="asset",
    )
    return payload
