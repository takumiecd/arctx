"""There is one storage backend, and asking for another one says so.

Storage is git-native: the committed jsonl canon *is* the run. A second
store that ``.arctx/.gitignore`` excludes is not an alternative backend —
writes through it reach no commit and no other clone — so ``sqlite`` is
gone rather than guarded. A machine still configured for it has to be told
that, not silently switched, because the failure it used to produce was
invisible: records accumulating in a file git never sees.
"""

from __future__ import annotations

import json

import pytest

from arctx.session import resolve_store
from arctx.storage import JsonlRunStore


def _unwrap(store):
    """Return the concrete store behind ExtensionAwareStore."""
    return getattr(store, "_store", store)


def test_default_is_jsonl(tmp_path, monkeypatch):
    monkeypatch.delenv("ARCTX_STORE", raising=False)
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path))

    assert isinstance(_unwrap(resolve_store(str(tmp_path / "runs"))), JsonlRunStore)


def test_explicit_jsonl_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_STORE", "jsonl")
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path))

    assert isinstance(_unwrap(resolve_store(str(tmp_path / "runs"))), JsonlRunStore)


def test_sqlite_env_is_refused_and_explains_why(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_STORE", "sqlite")
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path))

    with pytest.raises(RuntimeError) as excinfo:
        resolve_store(str(tmp_path / "runs"))

    message = str(excinfo.value)
    assert "sqlite" in message
    assert "ARCTX_STORE" in message  # where the setting came from
    assert "run.db" in message  # what the data it wrote was called
    assert "jsonl" in message  # what to use instead


def test_sqlite_in_config_is_refused_and_names_the_file(tmp_path, monkeypatch):
    monkeypatch.delenv("ARCTX_STORE", raising=False)
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path))
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"storage": {"backend": "sqlite"}}), encoding="utf-8")

    with pytest.raises(RuntimeError) as excinfo:
        resolve_store(str(tmp_path / "runs"))

    assert str(config) in str(excinfo.value)


def test_unknown_backend_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("ARCTX_STORE", "postgres")
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path))

    with pytest.raises(RuntimeError, match="postgres"):
        resolve_store(str(tmp_path / "runs"))
