"""arctx CLI view subcommands."""

from __future__ import annotations

import argparse
import json

from arctx_cli.append_batch import graph_counts, maybe_append_or_save
from arctx_cli.context import (
    resolve_run_id_from_args,
    resolve_store,
    resolve_user_id_from_args,
    resolve_work_session_id_from_args,
)


def add_parser(subparsers) -> argparse.ArgumentParser:
    parser = subparsers.add_parser("view", help="Manage GraphViews")
    view_sub = parser.add_subparsers(dest="view_command", required=True)

    # view create
    create = view_sub.add_parser("create", help="Create a new GraphView")
    create.add_argument("--name", required=True)
    create.add_argument("--root-node", required=True, dest="root_node")
    create.add_argument("--run", default=None)
    create.add_argument("--store-dir", default=None)
    create.add_argument("--user", default=None)
    create.add_argument("--work-session", default=None)

    # view list
    lst = view_sub.add_parser("list", help="List all GraphViews")
    lst.add_argument("--run", default=None)
    lst.add_argument("--store-dir", default=None)

    # view show
    show = view_sub.add_parser("show", help="Show a GraphView")
    show.add_argument("view_name")
    show.add_argument("--run", default=None)
    show.add_argument("--store-dir", default=None)

    return parser


def cli_view(args) -> int:
    store = resolve_store(args.store_dir)
    run_id = resolve_run_id_from_args(args)
    if not store.run_path(run_id).exists():
        raise KeyError(f"unknown run_id: {run_id}")
    handle = store.load_run(run_id)

    if args.view_command == "create":
        user_id = resolve_user_id_from_args(args)
        work_session_id = resolve_work_session_id_from_args(args)
        before = graph_counts(handle)
        view = handle.view_create(args.name, root_node_id=args.root_node)
        handle.record_work_event(
            user_id=user_id,
            work_session_id=work_session_id,
            event_type="view_created",
            target_kind="view",
            target_id=view.view_id,
            created_records=(view.view_id,),
            summary=view.name,
        )
        maybe_append_or_save(
            store=store,
            handle=handle,
            user_id=user_id,
            work_session_id=work_session_id,
            before=before,
        )
        print(json.dumps(view.to_dict(), ensure_ascii=False, indent=2))

    elif args.view_command == "list":
        views = handle.view_list()
        print(json.dumps([v.to_dict() for v in views], ensure_ascii=False, indent=2))

    elif args.view_command == "show":
        view = handle.view_show(args.view_name)
        print(json.dumps(view.to_dict(), ensure_ascii=False, indent=2))

    return 0
