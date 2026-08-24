"""Fast JSON helpers with orjson fallback.

Used by storage hot paths. CLI output formatting should keep using
the stdlib `json` module directly for ensure_ascii / indent control.
"""
from __future__ import annotations

try:
    import orjson as _orjson

    def loads(s: str | bytes) -> object:
        return _orjson.loads(s)

    def dumps(obj: object) -> str:
        return _orjson.dumps(obj, option=_orjson.OPT_SORT_KEYS).decode("utf-8")

    HAVE_ORJSON: bool = True

except ImportError:
    import json as _json

    def loads(s: str | bytes) -> object:  # type: ignore[misc]
        return _json.loads(s)

    def dumps(obj: object) -> str:  # type: ignore[misc]
        # allow_nan=False: bare NaN/Infinity are not JSON. Writing one puts
        # bytes in the git-committed canon that a strict parser (orjson, JS
        # JSON.parse) refuses to read, and jq silently turns into null. Fail
        # loudly at the write instead. Note orjson has no equivalent option --
        # it writes null for a non-finite float -- so the real guard is
        # validation at the point the value enters (see
        # arctx.ext.optimize.tables.value_kind); this is the backstop.
        return _json.dumps(obj, ensure_ascii=False, sort_keys=True, allow_nan=False)

    HAVE_ORJSON = False
