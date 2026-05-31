"""Repo registry (the repo 対応表) for the git extension.

A run can span several git repos. Each participating repo is recorded once as
a run-scoped ``RepoPayload`` attached to the run root node; every git payload
references its repo through ``repo_id`` only.

Identity stored in the run is environment-independent: ``repo_id`` (opaque
primary key), ``slug`` (USER/REPO display name), ``remotes`` (all known URL
forms), and ``canonical`` (the normalized key used for same-repo matching).
``local_path`` is the only environment-specific field and is stripped by
``to_shareable`` before the run leaves the machine (export / hub push).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from arctx.core.run_graph import RunGraph
from arctx.ext.git.payloads import RemoteRef, RepoPayload

if TYPE_CHECKING:
    from arctx.core.run.handle import RunHandle

REPO_MARKER = ".arctx-repo"

_SSH_SCP_RE = re.compile(r"^(?:ssh://)?(?:[^@/]+@)?([^:/]+)[:/](.+?)(?:\.git)?/?$")
_URL_RE = re.compile(r"^[a-z]+://(?:[^@/]+@)?([^:/]+)(?::\d+)?/(.+?)(?:\.git)?/?$")


def normalize_remote_url(url: str) -> str | None:
    """Reduce a git remote URL to a ``host/owner/repo`` canonical key.

    Both ``git@github.com:owner/repo.git`` and
    ``https://github.com/owner/repo`` normalize to ``github.com/owner/repo``,
    so the same upstream matches regardless of protocol. Returns None when the
    URL does not look like a recognizable remote.
    """
    url = url.strip()
    if not url:
        return None
    for pattern in (_URL_RE, _SSH_SCP_RE):
        m = pattern.match(url)
        if m:
            host = m.group(1).lower()
            path = m.group(2).strip("/").lower()
            return f"{host}/{path}"
    return None


def slug_from_canonical(canonical: str | None) -> str | None:
    """Derive an ``owner/repo`` slug from a canonical ``host/owner/repo`` key."""
    if not canonical:
        return None
    parts = canonical.split("/")
    if len(parts) >= 3:
        return "/".join(parts[1:])
    return None


def list_repos(graph: RunGraph) -> list[RepoPayload]:
    """Return all RepoPayload registry entries in the run."""
    repos: list[RepoPayload] = []
    for pid in graph.payloads_by_node.get(_root_node_id(graph), ()):
        payload = graph.payloads[pid]
        if isinstance(payload, RepoPayload):
            repos.append(payload)
    return repos


def repo_by_id(graph: RunGraph, repo_id: str) -> RepoPayload | None:
    for repo in list_repos(graph):
        if repo.repo_id == repo_id:
            return repo
    return None


def repo_by_canonical(graph: RunGraph, canonical: str) -> RepoPayload | None:
    for repo in list_repos(graph):
        if repo.canonical and repo.canonical == canonical:
            return repo
    return None


def _root_node_id(graph: RunGraph) -> str:
    root = graph.metadata.get("root_node_id")
    if root is not None:
        return str(root)
    roots = graph.roots()
    return roots[0] if roots else ""


# ---------------------------------------------------------------------------
# Marker file IO (environment-local; never travels with the run)
# ---------------------------------------------------------------------------


def read_repo_marker(repo_path: str | Path) -> str | None:
    """Return the repo_id from the nearest ``.arctx-repo`` marker, or None."""
    here = Path(repo_path).resolve()
    for directory in (here, *here.parents):
        marker = directory / REPO_MARKER
        if marker.is_file():
            value = marker.read_text(encoding="utf-8").strip()
            return value or None
    return None


def write_repo_marker(repo_root: str | Path, repo_id: str) -> None:
    """Write the repo_id marker at *repo_root* so future resolution is direct."""
    (Path(repo_root) / REPO_MARKER).write_text(repo_id + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Resolution: repo working tree -> repo_id (registering on first sight)
# ---------------------------------------------------------------------------


def resolve_repo_id(
    handle: "RunHandle", repo_path: str | Path, *, slug: str | None = None
) -> str:
    """Resolve *repo_path* to a repo_id in this run, registering it if new.

    Order: (1) ``.arctx-repo`` marker, (2) canonical match against the run's
    registry via the repo's git remotes, (3) register a fresh entry (works for
    purely local repos with no remote — opaque id only).

    *slug* overrides the display name only when registering a fresh entry; an
    already-registered repo keeps its recorded slug.
    """
    from arctx.ext.git.helpers import repo as git_repo

    graph = handle.run_graph

    marker_id = read_repo_marker(repo_path)
    if marker_id and repo_by_id(graph, marker_id) is not None:
        return marker_id

    remote_pairs = git_repo.remotes(repo_path)
    canonicals = [c for c in (normalize_remote_url(u) for _, u in remote_pairs) if c]
    for canonical in canonicals:
        existing = repo_by_canonical(graph, canonical)
        if existing is not None:
            _try_write_marker(repo_path, existing.repo_id)
            return existing.repo_id

    # Register a new repo entry.
    repo_id = marker_id or handle._next_id("repo")
    canonical = canonicals[0] if canonicals else None
    try:
        local_path = str(git_repo.find_repo_root(repo_path))
    except Exception:  # noqa: BLE001
        local_path = str(Path(repo_path).resolve())
    payload = RepoPayload(
        payload_id=handle._next_id("pl"),
        target_id=_root_node_id(graph),
        repo_id=repo_id,
        slug=slug or slug_from_canonical(canonical),
        remotes=tuple(RemoteRef(kind=k, url=u) for k, u in remote_pairs),
        canonical=canonical,
        local_path=local_path,
    )
    graph.attach_payload(payload)
    _try_write_marker(local_path, repo_id)
    return repo_id


def _try_write_marker(repo_path: str | Path, repo_id: str) -> None:
    try:
        from arctx.ext.git.helpers import repo as git_repo

        root = git_repo.find_repo_root(repo_path)
    except Exception:  # noqa: BLE001
        root = Path(repo_path)
    try:
        write_repo_marker(root, repo_id)
    except OSError:
        pass
