"""Test the built-in extension registry."""

import pytest

from stag.ext import Extension, ExtensionBase, list_available, load_extension


def test_registry_starts_empty_or_minimal():
    # At E1 there are no built-in extensions yet.
    avail = list_available()
    assert isinstance(avail, list)


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
