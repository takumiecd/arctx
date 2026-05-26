"""Extension framework Protocol and base helpers.

Extensions are independent bundles of:
- Schema additions (Payload classes, WorkEvent types)
- Verb additions (RunHandle.<ext>.<verb>)
- CLI additions (stag <ext> <verb>)
- Default CLI aliases (shortcut: stag <alias> -> stag <ext> <verb>)
- Init-time side effects
- Optional integrity validators

See docs/ja/EXTENSION_FRAMEWORK.md for the full design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    import argparse
    from stag.core.run.handle import RunHandle


@dataclass(frozen=True)
class Violation:
    """A single invariant violation reported by Extension.validate."""

    extension: str
    kind: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class InitContext:
    """Data passed to Extension.on_init.

    Attributes
    ----------
    run_id:
        The newly created run's id.
    run_dir:
        Directory where the run is stored.
    options:
        argparse Namespace -> dict of values for ext_<name>_* options.
    """

    run_id: str
    run_dir: str
    options: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Extension(Protocol):
    """Stable contract for extensions."""

    name: str
    version: str

    def register_schema(self) -> None: ...
    def register_verbs(self, handle: "RunHandle") -> None: ...
    def register_cli(self, subparsers: "argparse._SubParsersAction") -> None: ...
    def default_aliases(self) -> dict[str, str]: ...
    def register_init_options(self, parser: "argparse.ArgumentParser") -> None: ...
    def on_init(self, ctx: InitContext) -> None: ...
    def validate(self, handle: "RunHandle") -> list[Violation]: ...


class ExtensionBase:
    """Convenience base class providing empty defaults for every Protocol method.

    Subclass and override only the methods you need.
    """

    name: str = ""
    version: str = "0.0"

    def register_schema(self) -> None: ...
    def register_verbs(self, handle: "RunHandle") -> None: ...
    def register_cli(self, subparsers: "argparse._SubParsersAction") -> None: ...

    def default_aliases(self) -> dict[str, str]:
        return {}

    def register_init_options(self, parser: "argparse.ArgumentParser") -> None: ...
    def on_init(self, ctx: InitContext) -> None: ...

    def validate(self, handle: "RunHandle") -> list[Violation]:
        return []
