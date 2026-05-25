"""Pickle-based RunGraph load cache for run directories.

The cache file ``run.cache.pkl`` lives inside the run directory alongside
``run.json`` / ``run.db`` / ``nodes.jsonl`` etc.  It is a derived artefact:
removing it is always safe — the only consequence is a slower ``load_run``.

Cache structure (pickled dict)::

    {
        "schema_version": CACHE_SCHEMA_VERSION,  # int
        "row_counts": (n_nodes, n_its, n_ots, n_payloads, n_views),  # tuple[int,...]
        "run_graph": <RunGraph instance>,
    }

Consistency check: after reading the file we compare ``row_counts`` with the
current on-disk counts.  A mismatch (stale write, external edit, corruption,
schema bump) causes a cache miss; the caller falls back to a full load and
rewrites the cache.

Design invariants upheld here:
- ``save_cache`` never raises; all exceptions are swallowed.
- ``load_cache`` returns ``None`` on any failure (missing file, unpickle error,
  version mismatch, count mismatch).
- Atomic write via ``tempfile + os.replace`` prevents half-written pickle files.
"""

from __future__ import annotations

import os
import pickle
import tempfile
from pathlib import Path

from stag.core.run_graph import RunGraph

# Bump this whenever RunGraph or any Payload dataclass changes its fields in a
# backward-incompatible way.
CACHE_SCHEMA_VERSION: int = 4

_CACHE_FILENAME = "run.cache.pkl"


def cache_path(run_dir: Path) -> Path:
    """Return the path to the cache file for *run_dir*."""
    return run_dir / _CACHE_FILENAME


def load_cache(run_dir: Path, expected_row_counts: tuple[int, ...]) -> RunGraph | None:
    """Try to load a cached RunGraph.

    Returns the cached ``RunGraph`` if the cache file exists, the schema
    version matches, and the stored row counts equal *expected_row_counts*.
    Returns ``None`` in every other case (file absent, corrupt, stale).
    """
    path = cache_path(run_dir)
    if not path.exists():
        return None
    try:
        with path.open("rb") as fh:
            data = pickle.load(fh)
        if not isinstance(data, dict):
            return None
        if data.get("schema_version") != CACHE_SCHEMA_VERSION:
            return None
        if data.get("row_counts") != expected_row_counts:
            return None
        graph = data.get("run_graph")
        if not isinstance(graph, RunGraph):
            return None
        return graph
    except Exception:  # noqa: BLE001 — any failure → cache miss
        return None


def save_cache(run_dir: Path, row_counts: tuple[int, ...], graph: RunGraph) -> None:
    """Atomically write *graph* to the cache file.

    Silently swallows all errors so that a cache write failure never surfaces
    to the caller.
    """
    path = cache_path(run_dir)
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "row_counts": row_counts,
        "run_graph": graph,
    }
    try:
        # Write to a temp file in the same directory so os.replace is atomic
        # (same filesystem).
        fd, tmp_path = tempfile.mkstemp(dir=run_dir, prefix=".cache_tmp_", suffix=".pkl")
        try:
            with os.fdopen(fd, "wb") as fh:
                pickle.dump(payload, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp_path, path)
        except Exception:  # noqa: BLE001
            # Clean up orphan temp file if something went wrong before replace.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
    except Exception:  # noqa: BLE001 — silently swallow
        pass
