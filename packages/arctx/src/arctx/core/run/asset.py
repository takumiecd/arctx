"""RunHandle.attach_asset implementation — git-object references.

An asset is a reference, never a copy: ``(commit, path)`` resolved against the
repository that encloses the run data ("absent = self"). Attaching validates
that the reference actually resolves in this clone, and warns — without
blocking — when the commit has not been pushed anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from arctx.core.gitref import (
    GitRefError,
    head_commit,
    normalize_repo_path,
    object_kind,
    repo_root_for,
    resolve_commit,
    unpushed_warning,
)
from arctx.core.schema.payloads import AssetPayload


@dataclass(frozen=True)
class AssetAttachment:
    """Result of :meth:`RunHandle.attach_asset`.

    ``payload`` is the recorded :class:`AssetPayload`. ``warning`` carries the
    non-blocking push-status warning (``None`` when the commit is reachable
    from a remote-tracking ref) so a CLI/API caller can surface it; it is
    deliberately *not* stored on the record — push state is environment-local
    and changes over time, while the jsonl holds only facts.
    """

    payload: AssetPayload
    warning: str | None = None
    kind: str = "blob"


def attach_asset_impl(
    self,
    target_id: str,
    path: str | Path,
    *,
    commit: str | None = None,
    target_kind: str | None = None,
    title: str | None = None,
    repo_root: str | Path | None = None,
    user_id: str | None = None,
    lane_id: str | None = None,
) -> AssetAttachment:
    """Attach a git-object reference to a Node or Step.

    *path* is repo-root-relative (an absolute or cwd-relative path inside the
    repo is accepted and normalized) and may name a file or a directory.
    *commit* defaults to the enclosing repository's HEAD.

    Raises
    ------
    GitRefError
        When the run is not inside a git repository, or when
        ``<commit>:<path>`` does not resolve there.
    KeyError
        When *target_id* is not a known Node or Step.

    """
    graph = self.run_graph
    if target_kind is None:
        in_nodes = target_id in graph.nodes
        in_steps = target_id in graph.steps
        if in_nodes and in_steps:  # pragma: no cover - ids are opaque uuids
            raise ValueError(f"ambiguous target_id {target_id!r}: node and step")
        if not (in_nodes or in_steps):
            raise KeyError(f"unknown target_id: {target_id}")
        target_kind = "node" if in_nodes else "step"
    elif target_kind == "node":
        if target_id not in graph.nodes:
            raise KeyError(f"unknown node_id: {target_id}")
    elif target_kind == "step":
        if target_id not in graph.steps:
            raise KeyError(f"unknown step_id: {target_id}")
    else:
        raise ValueError(f"target_kind must be 'node' or 'step', got {target_kind!r}")

    root = Path(repo_root) if repo_root is not None else repo_root_for()
    rel_path = normalize_repo_path(path, repo_root=root)

    resolved_commit = resolve_commit(root, commit) if commit else head_commit(root)
    kind = object_kind(root, resolved_commit, rel_path)
    if kind not in ("blob", "tree"):
        raise GitRefError(
            f"{rel_path or '.'} at {resolved_commit[:12]} is a {kind}, "
            "which cannot be attached as an asset"
        )

    payload = AssetPayload(
        payload_id=self._next_id("pl"),
        target_id=target_id,
        target_kind=target_kind,  # type: ignore[arg-type]
        commit=resolved_commit,
        path=rel_path,
        title=title,
    )
    graph.attach_payload(payload)
    self.record_work_event(
        user_id=user_id,
        lane_id=lane_id,
        event_type="asset_attached",
        target_kind=target_kind,
        target_id=target_id,
        created_records=(payload.payload_id,),
        summary=title or rel_path or ".",
    )
    return AssetAttachment(
        payload=payload,
        warning=unpushed_warning(root, resolved_commit),
        kind=kind,
    )
