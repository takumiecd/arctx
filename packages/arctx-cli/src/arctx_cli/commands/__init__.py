"""Core CLI command registry."""

from __future__ import annotations

from arctx.ext import CliCommand


def core_cli_commands() -> list[CliCommand]:
    """Return the built-in, extension-independent CLI commands."""
    from arctx_cli.commands.alias_cmd import add_parser as add_alias_parser
    from arctx_cli.commands.alias_cmd import cli_alias
    from arctx_cli.commands.anchor import add_parser as add_anchor_parser
    from arctx_cli.commands.anchor import cli_anchor
    from arctx_cli.commands.claude_code import add_parser as add_claude_code_parser
    from arctx_cli.commands.claude_code import cli_claude_code
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
    from arctx_cli.commands.guide import add_parser as add_guide_parser
    from arctx_cli.commands.guide import cli_guide
    from arctx_cli.commands.init import add_parser as add_init_parser
    from arctx_cli.commands.init import cli_init
    from arctx_cli.commands.list import add_parser as add_list_parser
    from arctx_cli.commands.list import cli_list
    from arctx_cli.commands.migrate import add_parser as add_migrate_parser
    from arctx_cli.commands.migrate import cli_migrate
    from arctx_cli.commands.node import add_parser as add_node_parser
    from arctx_cli.commands.node import cli_node
    from arctx_cli.commands.outcomes import add_parser as add_outcomes_parser
    from arctx_cli.commands.outcomes import cli_outcomes
    from arctx_cli.commands.payload import add_parser as add_payload_parser
    from arctx_cli.commands.payload import cli_payload
    from arctx_cli.commands.reachable import add_parser as add_reachable_parser
    from arctx_cli.commands.reachable import cli_reachable
    from arctx_cli.commands.show import add_parser as add_show_parser
    from arctx_cli.commands.show import cli_show
    from arctx_cli.commands.sync import add_parser as add_sync_parser
    from arctx_cli.commands.sync import cli_sync
    from arctx_cli.commands.trace import add_parser as add_trace_parser
    from arctx_cli.commands.trace import cli_trace
    from arctx_cli.commands.transition import add_parser as add_transition_parser
    from arctx_cli.commands.transition import cli_transition
    from arctx_cli.commands.use import add_parser as add_use_parser
    from arctx_cli.commands.use import cli_use
    from arctx_cli.commands.view import add_parser as add_view_parser
    from arctx_cli.commands.view import cli_view
    from arctx_cli.commands.work_session import add_parser as add_work_session_parser
    from arctx_cli.commands.work_session import cli_work_session

    return [
        CliCommand("alias", add_alias_parser, cli_alias),
        CliCommand("anchor", add_anchor_parser, cli_anchor),
        CliCommand("claude-code", add_claude_code_parser, cli_claude_code),
        CliCommand("current", add_current_parser, cli_current),
        CliCommand("ext", add_ext_parser, cli_ext),
        CliCommand("dump", add_dump_parser, cli_dump),
        CliCommand("export", add_export_parser, cli_export),
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
        parser.set_defaults(_arctx_handler=command.handler)
