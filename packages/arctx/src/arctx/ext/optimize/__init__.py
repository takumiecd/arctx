"""Built-in optimize extension: scored trials over derived tables."""

from __future__ import annotations

from arctx.ext.base import CliCommand, ExtensionBase


class OptimizeExtension(ExtensionBase):
    """Trials with config/metrics, compared through name-keyed derived tables."""

    name = "optimize"
    version = "0.1"
    description = "Scored trials and derived comparison tables."

    def register_schema(self) -> None:
        import arctx.ext.optimize.payloads  # noqa: F401

    def cli_commands(self) -> list[CliCommand]:
        from arctx_cli.ext.optimize import (
            add_trial_parser,
            add_trials_parser,
            cli_trial,
            cli_trials,
        )

        return [
            CliCommand(name="trial", add_parser=add_trial_parser, handler=cli_trial),
            CliCommand(name="trials", add_parser=add_trials_parser, handler=cli_trials),
        ]

    def guide_text(self) -> str:
        return (
            "optimize: record scored attempts with "
            "`arctx trial add --table NAME --col k=v --metric k=v`; "
            "compare with `arctx trials [NAME] [--sort COL | --best min:COL]`."
        )


__all__ = ["OptimizeExtension"]
