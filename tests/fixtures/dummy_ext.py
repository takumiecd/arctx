"""Dummy extension used only by the test suite.

This module is never imported by production code.  Tests inject it into the
built-in registry via monkey-patching::

    import stag.ext as _ext_mod
    _ext_mod._BUILTIN["_dummy"] = "tests.fixtures.dummy_ext:DummyExtension"

The ``on_init`` side-effect writes ``<run_dir>/_dummy_init.txt`` so tests can
assert that it was called.
"""

from __future__ import annotations

from pathlib import Path

from stag.ext.base import ExtensionBase, InitContext


class DummyExtension(ExtensionBase):
    """Minimal test-only extension."""

    name = "_dummy"
    version = "0.1"

    def default_aliases(self) -> dict[str, str]:
        return {"do-it": "_dummy run", "shortcut": "_dummy run"}

    def register_init_options(self, parser) -> None:  # type: ignore[override]
        parser.add_argument(
            "--dummy-flag",
            dest="ext__dummy_dummy_flag",
            action="store_true",
            default=False,
            help="Dummy flag for testing ext init options",
        )

    def on_init(self, ctx: InitContext) -> None:
        marker = Path(ctx.run_dir) / "_dummy_init.txt"
        marker.write_text(
            f"dummy init: flag={ctx.options.get('ext__dummy_dummy_flag', False)}",
            encoding="utf-8",
        )
