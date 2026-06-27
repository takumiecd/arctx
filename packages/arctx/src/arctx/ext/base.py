"""Extension framework Protocol and base helpers.

Extensions are independent bundles of:
- Schema additions (Payload classes, WorkEvent types)
- Verb additions (RunHandle.<ext>.<verb>)
- CLI additions (arctx <ext> <verb>)
- Default CLI aliases (shortcut: arctx <alias> -> arctx <ext> <verb>)
- Init-time side effects
- Optional integrity validators

See docs/ja/EXTENSION_FRAMEWORK.md for the full design.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol, runtime_checkable

if TYPE_CHECKING:
    import argparse

    from arctx.core.run.handle import RunHandle


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


@dataclass(frozen=True)
class CliCommand:
    """A top-level CLI command contributed by an extension."""

    name: str
    add_parser: Callable[["argparse._SubParsersAction"], "argparse.ArgumentParser"]
    handler: Callable[["argparse.Namespace"], int]


@runtime_checkable
class Extension(Protocol):
    """Stable contract for extensions."""

    name: str
    version: str
    description: str

    def register_schema(self) -> None: ...
    def register_verbs(self, handle: "RunHandle") -> None: ...
    def cli_commands(self) -> list[CliCommand]: ...
    def default_aliases(self) -> dict[str, str]: ...
    def register_init_options(self, parser: "argparse.ArgumentParser") -> None: ...
    def on_init(self, ctx: InitContext) -> None: ...
    def validate(self, handle: "RunHandle") -> list[Violation]: ...
    def guide_text(self) -> str: ...


class ExtensionBase:
    """Convenience base class providing empty defaults for every Protocol method.

    Subclass and override only the methods you need.
    """

    name: str = ""
    version: str = "0.0"
    description: str = ""

    def register_schema(self) -> None:
        return None

    def register_verbs(self, handle: "RunHandle") -> None:
        del handle

    def cli_commands(self) -> list[CliCommand]:
        return []

    def default_aliases(self) -> dict[str, str]:
        return {}

    def register_init_options(self, parser: "argparse.ArgumentParser") -> None:
        del parser

    def on_init(self, ctx: InitContext) -> None:
        del ctx

    def validate(self, handle: "RunHandle") -> list[Violation]:
        del handle
        return []
        
    def guide_text(self) -> str:
        return ""
