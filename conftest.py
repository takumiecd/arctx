"""Test-suite-wide isolation of ARCTX storage.

Run data now defaults to the *enclosing repository*'s ``.arctx/runs``. Without a
guard, any test that resolves a store dir without passing one explicitly would
write into this very repository. ``ARCTX_HOME`` is the documented explicit
override, so point it at a per-test tmp dir; a test that wants to exercise the
in-repo default deletes the variable itself.

The load cache lives outside run directories now (see
``arctx.storage._cache``), which means the default location is the developer's
own ``~/.cache/arctx``. ``ARCTX_CACHE_DIR`` is redirected for the same reason.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_arctx_home(tmp_path_factory, monkeypatch):
    monkeypatch.setenv("ARCTX_HOME", str(tmp_path_factory.mktemp("arctx_home")))
    monkeypatch.setenv("ARCTX_CACHE_DIR", str(tmp_path_factory.mktemp("arctx_cache")))
