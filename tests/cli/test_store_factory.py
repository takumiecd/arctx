"""Tests for resolve_store() factory function."""

from __future__ import annotations

import json

import pytest

from stag.cli.context import resolve_store
from stag.storage.jsonl import JsonlRunStore
from stag.storage.sqlite import SqliteRunStore


def test_default_returns_jsonl(monkeypatch, tmp_path):
    monkeypatch.delenv("STAG_STORE", raising=False)
    store_dir = str(tmp_path / "runs")
    store = resolve_store(store_dir)
    assert isinstance(store, JsonlRunStore)


def test_env_jsonl_returns_jsonl(monkeypatch, tmp_path):
    monkeypatch.setenv("STAG_STORE", "jsonl")
    store_dir = str(tmp_path / "runs")
    store = resolve_store(store_dir)
    assert isinstance(store, JsonlRunStore)


def test_env_sqlite_returns_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("STAG_STORE", "sqlite")
    store_dir = str(tmp_path / "runs")
    store = resolve_store(store_dir)
    assert isinstance(store, SqliteRunStore)


def test_config_sqlite_returns_sqlite(monkeypatch, tmp_path):
    monkeypatch.delenv("STAG_STORE", raising=False)
    # config.json lives one level above store_dir (same as user config)
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"user": {"id": "alice"}, "storage": {"backend": "sqlite"}}),
        encoding="utf-8",
    )
    store_dir = str(tmp_path / "runs")
    store = resolve_store(store_dir)
    assert isinstance(store, SqliteRunStore)


def test_env_beats_config(monkeypatch, tmp_path):
    monkeypatch.setenv("STAG_STORE", "jsonl")
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps({"storage": {"backend": "sqlite"}}),
        encoding="utf-8",
    )
    store_dir = str(tmp_path / "runs")
    store = resolve_store(store_dir)
    assert isinstance(store, JsonlRunStore)


def test_unknown_backend_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("STAG_STORE", "redis")
    store_dir = str(tmp_path / "runs")
    with pytest.raises(RuntimeError, match="unknown store backend"):
        resolve_store(store_dir)
