"""Pickle-based RunGraph load cache for run directories.

The cache file ``run.cache.pkl`` lives inside the run directory alongside
``run.json`` / ``nodes.jsonl`` etc.  It is a derived artefact:
removing it is always safe — the only consequence is a slower ``load_run``.

Cache structure (pickled dict)::

    {
        "schema_version": CACHE_SCHEMA_VERSION,  # int
        "fingerprint": ((name, digest_or_None), ...),  # tuple[tuple[str, str|None], ...]
        "payload_types": <registered_payload_types() of the writer>,  # tuple[str,...]
        "run_graph": <RunGraph instance>,
    }

Consistency check: after reading the file we compare ``fingerprint`` with a
freshly computed one — a content digest of every file ``load_run`` reads.  A
mismatch (stale write, external edit, corruption, schema bump, a different
branch checked out) causes a cache miss; the caller falls back to a full load
and rewrites the cache.

The fingerprint is a digest and not a row count on purpose.  Storage here is
git-native, so the ordinary way this directory changes is ``git checkout`` /
``pull`` / ``stash`` — operations that routinely swap content while leaving the
number of lines alone.  Counting rows made those changes invisible and the
cache answered with the *other* branch's run.

Design invariants upheld here:
- ``save_cache`` never raises; all exceptions are swallowed.
- ``load_cache`` returns ``None`` on any failure (missing file, unpickle error,
  version mismatch, count mismatch).
- Atomic write via ``tempfile + os.replace`` prevents half-written pickle files.
"""

from __future__ import annotations

import hashlib
import os
import pickle
import tempfile
from pathlib import Path

from arctx.core.run_graph import RunGraph
from arctx.core.schema.payloads import registered_payload_types

# Every file `JsonlRunStore.load_run` reads. A cached graph is only valid if
# all of them are byte-identical to what produced it, so anything added to the
# load path must be added here too.
FINGERPRINTED_FILES: tuple[str, ...] = (
    "run.json",
    "graph.json",
    "nodes.jsonl",
    "steps.jsonl",
    "payloads.jsonl",
    "lanes.jsonl",
    "work_sessions.jsonl",
    "work_events.jsonl",
    "lane_events.jsonl",
)

# (filename, content digest or None when the file is absent) for each of the
# above, in order.
Fingerprint = tuple[tuple[str, str | None], ...]

_CHUNK = 1 << 20


def fingerprint(run_dir: Path) -> Fingerprint:
    """Digest every file `load_run` reads, so any content change is a cache miss.

    Reading the bytes is not extra work: the counting this replaced already
    read every line of every jsonl file, and hashing 5.8 MB of a real run costs
    under 5 ms — a fraction of the parse the cache exists to skip.
    """
    parts: list[tuple[str, str | None]] = []
    for name in FINGERPRINTED_FILES:
        path = run_dir / name
        try:
            with path.open("rb") as fh:
                digest = hashlib.blake2b(digest_size=16)
                while True:
                    chunk = fh.read(_CHUNK)
                    if not chunk:
                        break
                    digest.update(chunk)
            parts.append((name, digest.hexdigest()))
        except FileNotFoundError:
            parts.append((name, None))
        except OSError:
            # Unreadable for any other reason: refuse to vouch for the cache.
            parts.append((name, "<unreadable>"))
    return tuple(parts)

# Bump this whenever RunGraph or any Payload dataclass changes its fields in a
# backward-incompatible way.
#
# v6: WorkEvent.work_session_id renamed to WorkEvent.lane_id. Pickles from v5
#     restore the old attribute and lack ``lane_id``, crashing lane membership.
# v7: the cache records the writer's registered payload types. A graph decoded
#     by a process with a different registry is not interchangeable: unknown
#     payload types degrade to generic Node/StepPayload on load, and an older
#     process sharing the run directory would silently poison the cache for
#     newer readers (observed with a pre-optimize server degrading trials).
# v8: row counts replaced by a content fingerprint over every file load_run
#     reads. Counts missed same-length edits (a branch switch) and did not
#     cover lane_events.jsonl / work_sessions.jsonl / run.json / graph.json at
#     all.
CACHE_SCHEMA_VERSION: int = 8

_CACHE_FILENAME = "run.cache.pkl"


def cache_path(run_dir: Path) -> Path:
    """Return the path to the cache file for *run_dir*."""
    return run_dir / _CACHE_FILENAME


def load_cache(run_dir: Path, expected_fingerprint: Fingerprint) -> RunGraph | None:
    """Try to load a cached RunGraph.

    Returns the cached ``RunGraph`` if the cache file exists, the schema
    version matches, and the stored fingerprint equals *expected_fingerprint*.
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
        if data.get("fingerprint") != expected_fingerprint:
            return None
        if data.get("payload_types") != registered_payload_types():
            return None
        graph = data.get("run_graph")
        if not isinstance(graph, RunGraph):
            return None
        return graph
    except Exception:  # noqa: BLE001 — any failure → cache miss
        return None


def save_cache(run_dir: Path, fingerprint: Fingerprint, graph: RunGraph) -> None:
    """Atomically write *graph* to the cache file.

    Silently swallows all errors so that a cache write failure never surfaces
    to the caller.
    """
    path = cache_path(run_dir)
    payload = {
        "schema_version": CACHE_SCHEMA_VERSION,
        "fingerprint": fingerprint,
        "payload_types": registered_payload_types(),
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
