"""Identifier helpers for optimization runs and evidence graph records."""

from __future__ import annotations

import re
from datetime import datetime, timezone


_SAFE_ID = re.compile(r"[^a-zA-Z0-9_.-]+")


def slugify(value: str, fallback: str = "item") -> str:
    """Return a stable filesystem-safe slug."""
    slug = _SAFE_ID.sub("_", value.strip()).strip("._-").lower()
    return slug or fallback


def timestamp_id(prefix: str, now: datetime | None = None) -> str:
    """Return a timestamp-based id suitable for run directories."""
    current = now or datetime.now(timezone.utc)
    return f"{slugify(prefix)}_{current.strftime('%Y%m%d_%H%M%S')}"


def sequential_id(prefix: str, index: int, width: int = 4) -> str:
    """Return ids like attempt_0001."""
    return f"{slugify(prefix)}_{index:0{width}d}"
