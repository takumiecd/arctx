"""Core CLI command registry."""

from __future__ import annotations

from arctx.ext import CliCommand


def core_cli_commands() -> list[CliCommand]:
    """Return the built-in, extension-independent CLI commands."""
    from arctx_cli.commands.add import add_parser as add_add_parser
    from arctx_cli.commands.add import cli_add
    from arctx_cli.commands.alias_cmd import add_parser as add_alias_parser
    from arctx_cli.commands.alias_cmd import cli_alias
    from arctx_cli.commands.asset import add_parser as add_asset_parser
    from arctx_cli.commands.asset import cli_asset
    from arctx_cli.commands.attach import add_parser as add_attach_parser
    from arctx_cli.commands.attach import cli_attach
    from arctx_cli.commands.current import add_parser as add_current_parser
    from arctx_cli.commands.current import cli_current
    from arctx_cli.commands.cut import add_parser as add_cut_parser
    from arctx_cli.commands.cut import cli_cut
    from arctx_cli.commands.dump import add_parser as add_dump_parser
    from arctx_cli.commands.dump import cli_dump
    from arctx_cli.commands.export import add_parser as add_export_parser
    from arctx_cli.commands.export import cli_export
    from arctx_cli.commands.ext import add_parser as add_ext_parser
    from arctx_cli.commands.ext import cli_ext
    from arctx_cli.commands.graph import add_parser as add_graph_parser
    from arctx_cli.commands.graph import cli_graph
    from arctx_cli.commands.init import add_parser as add_init_parser
    from arctx_cli.commands.init import cli_init
    from arctx_cli.commands.lane import add_parser as add_lane_parser
    from arctx_cli.commands.lane import cli_lane
    from arctx_cli.commands.list import add_parser as add_list_parser
    from arctx_cli.commands.list import cli_list
    from arctx_cli.commands.log import add_parser as add_log_parser
    from arctx_cli.commands.log import cli_log
    from arctx_cli.commands.migrate import add_parser as add_migrate_parser
    from arctx_cli.commands.migrate import cli_migrate
    from arctx_cli.commands.reparent import add_parser as add_reparent_parser
    from arctx_cli.commands.reparent import cli_reparent
    from arctx_cli.commands.pr import (
        add_accept_parser,
        add_propose_parser,
        add_reject_parser,
        cli_accept,
        cli_propose,
        cli_reject,
    )
    from arctx_cli.commands.serve import add_parser as add_serve_parser
    from arctx_cli.commands.serve import cli_serve
    from arctx_cli.commands.sync_cmd import (
        add_pull_parser,
        add_push_parser,
        add_remote_parser,
        cli_pull,
        cli_push,
        cli_remote,
    )
    from arctx_cli.commands.show import add_parser as add_show_parser
    from arctx_cli.commands.show import cli_show
    from arctx_cli.commands.use import add_parser as add_use_parser
    from arctx_cli.commands.use import cli_use
    from arctx_cli.commands.work_session import add_parser as add_work_session_parser
    from arctx_cli.commands.work_session import cli_work_session

    return [
        CliCommand("add", add_add_parser, cli_add),
        CliCommand("alias", add_alias_parser, cli_alias),
        CliCommand("asset", add_asset_parser, cli_asset),
        CliCommand("attach", add_attach_parser, cli_attach),
        CliCommand("current", add_current_parser, cli_current),
        CliCommand("ext", add_ext_parser, cli_ext),
        CliCommand("dump", add_dump_parser, cli_dump),
        CliCommand("export", add_export_parser, cli_export),
        CliCommand("graph", add_graph_parser, cli_graph),
        CliCommand("init", add_init_parser, cli_init),
        CliCommand("lane", add_lane_parser, cli_lane),
        CliCommand("list", add_list_parser, cli_list),
        CliCommand("log", add_log_parser, cli_log),
        CliCommand("migrate", add_migrate_parser, cli_migrate),
        CliCommand("cut", add_cut_parser, cli_cut),
        CliCommand("reparent", add_reparent_parser, cli_reparent),
        CliCommand("propose", add_propose_parser, cli_propose),
        CliCommand("accept", add_accept_parser, cli_accept),
        CliCommand("reject", add_reject_parser, cli_reject),
        CliCommand("remote", add_remote_parser, cli_remote),
        CliCommand("push", add_push_parser, cli_push),
        CliCommand("pull", add_pull_parser, cli_pull),
        CliCommand("serve", add_serve_parser, cli_serve),
        CliCommand("show", add_show_parser, cli_show),
        CliCommand("use", add_use_parser, cli_use),
        CliCommand("work-session", add_work_session_parser, cli_work_session),
    ]


def register_cli_commands(subparsers, commands: list[CliCommand]) -> None:
    """Register CLI commands and attach their dispatch handlers."""
    for command in commands:
        parser = command.add_parser(subparsers)
        parser.set_defaults(_arctx_handler=command.handler)
