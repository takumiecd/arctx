"""Asset read path for the serve layer — pure, socket-free git resolution.

Assets are ``(commit, path)`` references (see :mod:`arctx.core.gitref`), so
"reading an asset" means asking git for the object at request time. Everything
here is a plain function over a loaded run + a repo root, which keeps it unit
testable and lets the HTTP shell stay a transport.

Route shapes (the stable contract; see docs/ja/GIT_NATIVE.md):

  GET /asset?payload_id=pl_x                     -> reference + resolution status
  GET /asset/entries?payload_id=pl_x&path=sub    -> directory listing (JSON)
  GET /asset/content?payload_id=pl_x&path=sub    -> file content (text or base64)
  GET /asset/raw?payload_id=pl_x&path=sub        -> file bytes (HTTP shell only)

``path`` is optional and relative to the asset's own path, so a directory
asset can be browsed without minting more payloads.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from arctx.core.gitref import (
    GitRefError,
    MissingCommit,
    MissingPath,
    blob_size,
    guess_content_type,
    join_repo_path,
    list_tree,
    object_kind,
    read_blob,
    repo_root_for,
)
from arctx.core.schema.payloads import AssetPayload


class AssetError(Exception):
    """An asset request that should become a structured error response."""

    def __init__(self, status: int, message: str, *, code: str) -> None:
        """Build an error carrying an HTTP status and a machine-readable code."""
        super().__init__(message)
        self.status = status
        self.message = message
        self.code = code


@dataclass(frozen=True)
class RawAsset:
    """Bytes plus content type, for transports that can send binary."""

    data: bytes
    content_type: str
    path: str
    commit: str


def find_asset(handle, payload_id: str) -> AssetPayload:
    """Return the AssetPayload with *payload_id*, or raise :class:`AssetError`."""
    payload = handle.run_graph.payloads.get(payload_id)
    if payload is None:
        raise AssetError(404, f"unknown payload_id: {payload_id}", code="unknown_payload")
    if not isinstance(payload, AssetPayload):
        raise AssetError(
            400,
            f"payload {payload_id} is not an asset (payload_type={payload.payload_type})",
            code="not_an_asset",
        )
    return payload


def resolve_repo_root(run_path: str | Path) -> Path:
    """Return the repository enclosing the run data ("absent = self")."""
    try:
        return repo_root_for(run_path)
    except GitRefError as exc:
        raise AssetError(404, str(exc), code="no_repository") from exc


def _target_path(asset: AssetPayload, sub_path: str | None) -> str:
    try:
        return join_repo_path(asset.path, sub_path)
    except GitRefError as exc:
        raise AssetError(400, str(exc), code="bad_path") from exc


def _kind(repo_root: Path, commit: str, path: str) -> str:
    try:
        return object_kind(repo_root, commit, path)
    except MissingCommit as exc:
        raise AssetError(404, str(exc), code="missing_commit") from exc
    except MissingPath as exc:
        raise AssetError(404, str(exc), code="missing_path") from exc
    except GitRefError as exc:  # pragma: no cover - defensive
        raise AssetError(500, str(exc), code="git_error") from exc


def asset_view(handle, run_path: str | Path, payload_id: str) -> dict:
    """Return the asset reference plus whether it resolves in this clone."""
    asset = find_asset(handle, payload_id)
    reference = {
        "payload_id": asset.payload_id,
        "target_kind": asset.target_kind,
        "target_id": asset.target_id,
        "commit": asset.commit,
        "path": asset.path,
        "title": asset.title,
    }
    try:
        repo_root = resolve_repo_root(run_path)
        kind = _kind(repo_root, asset.commit, asset.path)
    except AssetError as exc:
        return {
            "asset": reference,
            "resolution": {"status": exc.code, "message": exc.message, "kind": None},
        }
    return {
        "asset": reference,
        "resolution": {
            "status": "ok",
            "kind": kind,
            "content_type": guess_content_type(asset.path) if kind == "blob" else None,
        },
    }


def asset_entries(
    handle, run_path: str | Path, payload_id: str, sub_path: str | None = None
) -> dict:
    """Return a JSON directory listing for a tree asset."""
    asset = find_asset(handle, payload_id)
    repo_root = resolve_repo_root(run_path)
    path = _target_path(asset, sub_path)
    kind = _kind(repo_root, asset.commit, path)
    if kind != "tree":
        raise AssetError(400, f"{path or '.'} is a {kind}, not a directory", code="not_a_tree")
    entries = list_tree(repo_root, asset.commit, path)
    return {
        "payload_id": asset.payload_id,
        "commit": asset.commit,
        "path": path,
        "entries": [entry.to_dict() for entry in entries],
    }


def asset_content(
    handle, run_path: str | Path, payload_id: str, sub_path: str | None = None
) -> dict:
    """Return file content as JSON — utf-8 inline when decodable, else base64."""
    raw = asset_raw(handle, run_path, payload_id, sub_path)
    try:
        text = raw.data.decode("utf-8")
        encoding, content = "utf-8", text
    except UnicodeDecodeError:
        encoding, content = "base64", base64.b64encode(raw.data).decode("ascii")
    return {
        "payload_id": payload_id,
        "commit": raw.commit,
        "path": raw.path,
        "content_type": raw.content_type,
        "size": len(raw.data),
        "encoding": encoding,
        "content": content,
    }


def asset_raw(
    handle, run_path: str | Path, payload_id: str, sub_path: str | None = None
) -> RawAsset:
    """Return the raw bytes of a blob asset (binary-safe)."""
    asset = find_asset(handle, payload_id)
    repo_root = resolve_repo_root(run_path)
    path = _target_path(asset, sub_path)
    kind = _kind(repo_root, asset.commit, path)
    if kind != "blob":
        raise AssetError(400, f"{path or '.'} is a {kind}, not a file", code="not_a_blob")
    data = read_blob(repo_root, asset.commit, path)
    return RawAsset(
        data=data,
        content_type=guess_content_type(path),
        path=path,
        commit=asset.commit,
    )


def asset_size(repo_root: Path, commit: str, path: str) -> int:
    """Size in bytes of ``<commit>:<path>`` (blob only)."""
    return blob_size(repo_root, commit, path)
