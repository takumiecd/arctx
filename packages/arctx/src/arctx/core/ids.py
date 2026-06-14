"""Identifier helpers for run and step records."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone


_SAFE_ID = re.compile(r"[^a-zA-Z0-9_.-]+")


def slugify(value: str, fallback: str = "item") -> str:
    """Return a stable filesystem-safe slug."""
    slug = _SAFE_ID.sub("_", value.strip()).strip("._-").lower()
    return slug or fallback


def timestamp_id(prefix: str, now: datetime | None = None) -> str:
    """Return a timestamp-based id."""
    current = now or datetime.now(timezone.utc)
    return f"{slugify(prefix)}_{current.strftime('%Y%m%d_%H%M%S')}"


def sequential_id(prefix: str, index: int, width: int = 4) -> str:
    """Return ids such as ``state_0001``."""
    return f"{slugify(prefix)}_{index:0{width}d}"


def opaque_id(prefix: str) -> str:
    """Return a collision-resistant opaque id with a readable kind prefix."""
    return f"{slugify(prefix)}_{uuid.uuid4().hex}"
