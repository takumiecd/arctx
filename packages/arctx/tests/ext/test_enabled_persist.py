"""Test extensions.json persist/load."""

from arctx.ext import attach_extensions
from arctx.ext.enabled import EnabledExtension, add_enabled, load_enabled, save_enabled


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


def test_attach_extensions_skips_unknown_names():
    # A run whose enabled list still names "asset" (now a core payload, no
    # longer an extension) must not crash when its extensions are attached.
    from arctx import init
    from arctx.core.schema.requirements import Requirement

    handle = init(Requirement(requirement_id="r", target_type="task", target_id="t"))
    # Should not raise on the unknown name; known names still attach.
    attach_extensions(handle, ["asset", "git"])
    assert hasattr(handle, "git")
