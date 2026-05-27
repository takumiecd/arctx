"""Test extensions.json persist/load."""

from stag_api.ext.enabled import EnabledExtension, add_enabled, load_enabled, save_enabled


def test_load_empty_when_missing(tmp_path):
    assert load_enabled(tmp_path) == []


def test_save_and_load_roundtrip(tmp_path):
    e1 = EnabledExtension(name="git", version="0.1", config={"foo": "bar"})
    save_enabled(tmp_path, [e1])
    loaded = load_enabled(tmp_path)
    assert loaded == [e1]


def test_add_enabled_idempotent(tmp_path):
    e1 = EnabledExtension(name="git", version="0.1")
    add_enabled(tmp_path, e1)
    add_enabled(tmp_path, e1)  # adding again should not duplicate
    loaded = load_enabled(tmp_path)
    assert len(loaded) == 1
    assert loaded[0].name == "git"


def test_multiple_extensions(tmp_path):
    e1 = EnabledExtension(name="git", version="0.1")
    e2 = EnabledExtension(name="jupyter", version="0.1")
    add_enabled(tmp_path, e1)
    add_enabled(tmp_path, e2)
    loaded = load_enabled(tmp_path)
    assert {e.name for e in loaded} == {"git", "jupyter"}
