"""Test the built-in extension registry."""

import pytest

from stag.ext import Extension, ExtensionBase, list_available, load_extension
from stag.core.schema.requirements import Requirement
from stag.core.run import init


def test_registry_starts_empty_or_minimal():
    avail = list_available()
    assert isinstance(avail, list)
    assert "git" in avail


def test_load_git_extension():
    ext = load_extension("git")
    assert ext.name == "git"
    assert ext.version == "0.1"
    assert "commit" in ext.default_aliases()


def test_git_extension_registers_namespace():
    ext = load_extension("git")
    handle = init(Requirement(requirement_id="req", target_type="task", target_id="t"))

    ext.register_verbs(handle)

    assert hasattr(handle, "git")
    assert callable(handle.git.commit)
    assert not hasattr(handle, "commit")


def test_load_unknown_raises():
    with pytest.raises(KeyError):
        load_extension("does_not_exist")


def test_extension_base_satisfies_protocol():
    ext = ExtensionBase()
    assert isinstance(ext, Extension)


def test_extension_base_defaults():
    ext = ExtensionBase()
    assert ext.default_aliases() == {}
    assert ext.validate(handle=None) == []  # type: ignore[arg-type]


def test_third_party_discovery():
    from unittest.mock import patch, MagicMock

    mock_ep = MagicMock()
    mock_ep.name = "myext"
    mock_ep.load.return_value = MagicMock(return_value="MyExtInstance")

    with patch("stag.ext._get_entry_points", return_value={"myext": mock_ep}):
        avail = list_available()
        assert "myext" in avail
        assert "git" in avail

        ext = load_extension("myext")
        assert ext == "MyExtInstance"
