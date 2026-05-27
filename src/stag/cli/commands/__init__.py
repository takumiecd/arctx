"""Core CLI command registry."""

from __future__ import annotations

from stag.ext import CliCommand


def core_cli_commands() -> list[CliCommand]:
    """Return the built-in, extension-independent CLI commands."""
    from stag.cli.commands.alias_cmd import add_parser as add_alias_parser
    from stag.cli.commands.alias_cmd import cli_alias
    from stag.cli.commands.anchor import add_parser as add_anchor_parser
    from stag.cli.commands.anchor import cli_anchor
    from stag.cli.commands.current import add_parser as add_current_parser
    from stag.cli.commands.current import cli_current
    from stag.cli.commands.cut import add_parser as add_cut_parser
    from stag.cli.commands.cut import cli_cut
    from stag.cli.commands.dump import add_parser as add_dump_parser
    from stag.cli.commands.dump import cli_dump
    from stag.cli.commands.ext import add_parser as add_ext_parser
    from stag.cli.commands.ext import cli_ext
    from stag.cli.commands.graph import add_parser as add_graph_parser
    from stag.cli.commands.graph import cli_graph
    from stag.cli.commands.guide import add_parser as add_guide_parser
    from stag.cli.commands.guide import cli_guide
    from stag.cli.commands.init import add_parser as add_init_parser
    from stag.cli.commands.init import cli_init
    from stag.cli.commands.list import add_parser as add_list_parser
    from stag.cli.commands.list import cli_list
    from stag.cli.commands.migrate import add_parser as add_migrate_parser
    from stag.cli.commands.migrate import cli_migrate
    from stag.cli.commands.node import add_parser as add_node_parser
    from stag.cli.commands.node import cli_node
    from stag.cli.commands.outcomes import add_parser as add_outcomes_parser
    from stag.cli.commands.outcomes import cli_outcomes
    from stag.cli.commands.payload import add_parser as add_payload_parser
    from stag.cli.commands.payload import cli_payload
    from stag.cli.commands.reachable import add_parser as add_reachable_parser
    from stag.cli.commands.reachable import cli_reachable
    from stag.cli.commands.show import add_parser as add_show_parser
    from stag.cli.commands.show import cli_show
    from stag.cli.commands.sync import add_parser as add_sync_parser
    from stag.cli.commands.sync import cli_sync
    from stag.cli.commands.trace import add_parser as add_trace_parser
    from stag.cli.commands.trace import cli_trace
    from stag.cli.commands.transition import add_parser as add_transition_parser
    from stag.cli.commands.transition import cli_transition
    from stag.cli.commands.tui import add_parser as add_tui_parser
    from stag.cli.commands.tui import cli_tui
    from stag.cli.commands.use import add_parser as add_use_parser
    from stag.cli.commands.use import cli_use
    from stag.cli.commands.view import add_parser as add_view_parser
    from stag.cli.commands.view import cli_view
    from stag.cli.commands.work_session import add_parser as add_work_session_parser
    from stag.cli.commands.work_session import cli_work_session

    return [
        CliCommand("alias", add_alias_parser, cli_alias),
        CliCommand("anchor", add_anchor_parser, cli_anchor),
        CliCommand("current", add_current_parser, cli_current),
        CliCommand("ext", add_ext_parser, cli_ext),
        CliCommand("dump", add_dump_parser, cli_dump),
        CliCommand("graph", add_graph_parser, cli_graph),
        CliCommand("guide", add_guide_parser, cli_guide),
        CliCommand("init", add_init_parser, cli_init),
        CliCommand("list", add_list_parser, cli_list),
        CliCommand("migrate", add_migrate_parser, cli_migrate),
        CliCommand("node", add_node_parser, cli_node),
        CliCommand("outcomes", add_outcomes_parser, cli_outcomes),
        CliCommand("payload", add_payload_parser, cli_payload),
        CliCommand("reachable", add_reachable_parser, cli_reachable),
        CliCommand("cut", add_cut_parser, cli_cut),
        CliCommand("show", add_show_parser, cli_show),
        CliCommand("sync", add_sync_parser, cli_sync),
        CliCommand("tui", add_tui_parser, cli_tui),
        CliCommand("trace", add_trace_parser, cli_trace),
        CliCommand("transition", add_transition_parser, cli_transition),
        CliCommand("use", add_use_parser, cli_use),
        CliCommand("view", add_view_parser, cli_view),
        CliCommand("work-session", add_work_session_parser, cli_work_session),
    ]


def register_cli_commands(subparsers, commands: list[CliCommand]) -> None:
    """Register CLI commands and attach their dispatch handlers."""
    for command in commands:
        parser = command.add_parser(subparsers)
        parser.set_defaults(_stag_handler=command.handler)
