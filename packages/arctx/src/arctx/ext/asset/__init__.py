"""Built-in asset extension for attaching images, videos, and documents."""

from __future__ import annotations

import mimetypes
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from arctx.ext.base import CliCommand, ExtensionBase
from arctx.paths import runs_dir

if TYPE_CHECKING:
    from arctx.core.run.handle import RunHandle
    from arctx.ext.asset.payloads import AssetPayload


@dataclass
class AssetNamespace:
    """Python API namespace for asset extension verbs.

    Exposed as ``handle.asset.<verb>``.
    """

    handle: RunHandle

    def attach(
        self,
        target_id: str,
        file_path: str | Path,
        *,
        user_id: str | None = None,
        work_session_id: str | None = None,
    ) -> AssetPayload:
        """Copy a file to the run assets directory and attach an AssetPayload to a Node/Step."""
        # 1. Validate target_id
        target_kind: Literal["node", "step"]
        if target_id in self.handle.run_graph.nodes:
            target_kind = "node"
        elif target_id in self.handle.run_graph.steps:
            target_kind = "step"
        else:
            raise KeyError(f"unknown target_id: {target_id}")

        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"file not found: {file_path}")

        # 2. Extract metadata
        asset_id = self.handle._next_id("ast")
        filename = file_path.name
        mime_type, _ = mimetypes.guess_type(filename)
        if not mime_type:
            mime_type = "application/octet-stream"
        size_bytes = file_path.stat().st_size

        # 3. Copy file to <run_dir>/assets/
        run_dir = runs_dir() / self.handle.run_id
        assets_dir = run_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)

        dest_filename = f"{asset_id}_{filename}"
        dest_path = assets_dir / dest_filename
        shutil.copy2(file_path, dest_path)

        # 4. Create and attach the AssetPayload
        # Relative path is stored for portability
        rel_path = f"assets/{dest_filename}"
        payload_id = self.handle._next_id("pl")

        from arctx.ext.asset.payloads import AssetPayload

        payload = AssetPayload(
            payload_id=payload_id,
            target_id=target_id,
            target_kind=target_kind,
            asset_id=asset_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            path=rel_path,
        )

        if target_kind == "node":
            payload = self.handle.attach(
                target_id,
                payload,
                user_id=user_id,
                work_session_id=work_session_id,
            )
        else:
            self.handle.run_graph.attach_payload(payload)
            self.handle.record_work_event(
                user_id=user_id,
                work_session_id=work_session_id,
                event_type="payload_attached",
                target_kind="step",
                target_id=target_id,
                created_records=(payload.payload_id,),
                summary="asset",
            )

        return payload


class AssetExtension(ExtensionBase):
    """Extension for tracking and attaching asset files to graph nodes/steps."""

    name = "asset"
    version = "0.1"

    def register_schema(self) -> None:
        """Register the asset payload schema and decoders."""
        # Import payloads module to execute side-effect registrations
        import arctx.ext.asset.payloads  # noqa: F401

    def register_verbs(self, handle: RunHandle) -> None:
        """Expose python API verbs under handle.asset."""
        if hasattr(handle, self.name):
            return
        setattr(handle, self.name, AssetNamespace(handle))

    def cli_commands(self) -> list[CliCommand]:
        """Expose command-line endpoints under arctx asset."""
        from arctx_cli.ext.asset import add_parser, cli_asset

        return [CliCommand(name=self.name, add_parser=add_parser, handler=cli_asset)]

    def default_aliases(self) -> dict[str, str]:
        """Define default CLI aliases for convenience shortcuts."""
        return {
            "attach-file": "asset attach",
        }


__all__ = ["AssetExtension", "AssetNamespace"]
