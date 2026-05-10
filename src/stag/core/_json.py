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
        return _json.dumps(obj, ensure_ascii=False, sort_keys=True)

    HAVE_ORJSON = False
