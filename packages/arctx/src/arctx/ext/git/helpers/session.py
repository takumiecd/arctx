"""GitSession dataclass and JSON storage helpers."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_CURRENT_FILENAME = "current.json"
_SESSIONS_DIR = "sessions"


@dataclass
class GitSession:
    """Pending work interval anchored to a Step.

    Created by ``arctx git start`` and closed by ``arctx git finish``.
    Stored under ``<run_dir>/git/sessions/<session_id>.json``.
    This is NOT a graph record — it is a run-directory-level side-car file.
    """

    session_id: str
    run_id: str
    step_id: str
    repo_root: str  # absolute path
    base_commit: str
    base_branch: str
    base_dirty: bool
    started_at: str  # ISO 8601 with timezone
    started_by: str
    closed_at: str | None = None
    closed_by: str | None = None
    result_node_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "run_id": self.run_id,
            "step_id": self.step_id,
            "repo_root": self.repo_root,
            "base_commit": self.base_commit,
            "base_branch": self.base_branch,
            "base_dirty": self.base_dirty,
            "started_at": self.started_at,
            "started_by": self.started_by,
            "closed_at": self.closed_at,
            "closed_by": self.closed_by,
            "result_node_id": self.result_node_id,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GitSession":
        return cls(
            session_id=str(data["session_id"]),
            run_id=str(data["run_id"]),
            step_id=str(data["step_id"]),
            repo_root=str(data["repo_root"]),
            base_commit=str(data["base_commit"]),
            base_branch=str(data["base_branch"]),
            base_dirty=bool(data["base_dirty"]),
            started_at=str(data["started_at"]),
            started_by=str(data["started_by"]),
            closed_at=data.get("closed_at"),
            closed_by=data.get("closed_by"),
            result_node_id=data.get("result_node_id"),
            metadata=dict(data.get("metadata") or {}),
        )


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------


def _sessions_dir(run_dir: Path) -> Path:
    return run_dir / "git" / _SESSIONS_DIR


def _current_pointer_path(run_dir: Path) -> Path:
    return run_dir / "git" / _CURRENT_FILENAME


def _session_path(run_dir: Path, session_id: str) -> Path:
    return _sessions_dir(run_dir) / f"{session_id}.json"


def save_session(session: GitSession, run_dir: Path) -> Path:
    """Persist *session* to ``<run_dir>/git/sessions/<session_id>.json``."""
    sessions_dir = _sessions_dir(run_dir)
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = _session_path(run_dir, session.session_id)
    data = json.dumps(session.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
    # Atomic write via temp + rename
    fd, tmp = tempfile.mkstemp(dir=sessions_dir, suffix=".tmp")
    try:
        os.write(fd, data.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def load_session(session_id: str, run_dir: Path) -> GitSession:
    """Load a session by id from ``<run_dir>/git/sessions/``."""
    path = _session_path(run_dir, session_id)
    if not path.exists():
        raise KeyError(f"unknown session_id: {session_id}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return GitSession.from_dict(data)


def list_sessions(run_dir: Path) -> list[GitSession]:
    """Return all sessions in the run directory, sorted by session_id."""
    d = _sessions_dir(run_dir)
    if not d.exists():
        return []
    sessions = []
    for p in sorted(d.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            sessions.append(GitSession.from_dict(data))
        except Exception:
            continue
    return sessions


def save_current_pointer(session_id: str, run_dir: Path) -> None:
    """Write ``<run_dir>/git/current.json`` pointing to *session_id*."""
    git_dir = run_dir / "git"
    git_dir.mkdir(parents=True, exist_ok=True)
    path = _current_pointer_path(run_dir)
    data = json.dumps({"session_id": session_id}, ensure_ascii=False, indent=2)
    fd, tmp = tempfile.mkstemp(dir=git_dir, suffix=".tmp")
    try:
        os.write(fd, data.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_current_pointer(run_dir: Path) -> str | None:
    """Return the session_id from ``<run_dir>/git/current.json``, or None."""
    path = _current_pointer_path(run_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("session_id")
    except Exception:
        return None


def clear_current_pointer(session_id: str, run_dir: Path) -> None:
    """Clear ``<run_dir>/git/current.json`` if it points to *session_id*."""
    current = load_current_pointer(run_dir)
    if current == session_id:
        path = _current_pointer_path(run_dir)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
