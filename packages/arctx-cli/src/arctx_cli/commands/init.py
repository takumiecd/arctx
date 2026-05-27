"""arctx CLI init command."""

from __future__ import annotations

import argparse

import arctx as arctx
from arctx_cli.context import resolve_store
from arctx_cli.paths import find_repo_root, resolve_store_dir, arctx_id_path, write_arctx_id
from arctx.core.schema.requirements import Requirement


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``init`` subcommand parser."""
    parser = subparsers.add_parser("init", help="Initialize a new run")
    parser.add_argument("requirement_id", help="Requirement identifier")
    parser.add_argument(
        "--target-type",
        default="code",
        help="Target category (default: code)",
    )
    parser.add_argument(
        "--target-id",
        default=None,
        help="Specific target identifier (default: requirement_id)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Explicit run id (default: auto-generated)",
    )
    parser.add_argument(
        "--store-dir",
        default=None,
        help="Directory to save runs (default: <ARCTX_HOME>/runs)",
    )
    parser.add_argument(
        "--no-hooks",
        action="store_true",
        help="Skip installing git hooks (post-rewrite etc.)",
    )
    parser.add_argument(
        "--extension",
        action="append",
        default=[],
        dest="extension",
        metavar="NAME",
        help="Enable extension by name (may be repeated)",
    )

    # Pre-register init options from all built-in extensions so that
    # extension-specific flags (e.g. --dummy-flag) are accepted at parse time.
    from arctx.ext import list_available, load_extension  # noqa: PLC0415

    for ext_name in list_available():
        try:
            ext = load_extension(ext_name)
            ext.register_init_options(parser)
        except Exception:  # noqa: BLE001
            continue

    return parser


def run_init_command(
    *,
    requirement_id: str,
    target_type: str,
    target_id: str | None,
    run_id: str | None,
    store_dir: str | None,
    no_hooks: bool = False,
    extensions: list[str] | None = None,
    extension_options: dict[str, object] | None = None,
) -> dict[str, str]:
    """Create a new run and save it to disk.

    Parameters
    ----------
    requirement_id:
        Identifier for the requirement.
    target_type:
        Category of the target (e.g. "code", "kernel").
    target_id:
        Specific target identifier.
    run_id:
        Explicit run id. If None, one is generated automatically.
    store_dir:
        Directory under which run directories are created.
        If None, defaults to ``<ARCTX_HOME>/runs``.
    no_hooks:
        If True, skip installing git hooks.
    extensions:
        Names of extensions to enable.  Each extension's ``on_init`` is called
        and the extension is recorded in ``<run_dir>/extensions.json``.
    extension_options:
        Flat dict of parsed argparse values for extension-specific options,
        keyed by their ``dest`` names (e.g. ``ext__dummy_dummy_flag``).

    Returns
    -------
    dict with at least ``run_id``, ``root_node_id``, and ``arctx_id_path``
    (the path where the active-run pointer was written under ``<gitdir>/``,
    or None if not in a git repo).

    Raises
    ------
    FileExistsError
        If the run directory already exists.
    KeyError
        If an extension name is not in the built-in registry.
    """
    resolved_store_dir = store_dir if store_dir is not None else resolve_store_dir()

    requirement = Requirement(
        requirement_id=requirement_id,
        target_type=target_type,
        target_id=target_id or requirement_id,
    )

    handle = arctx.init(requirement, run_id=run_id)

    store = resolve_store(resolved_store_dir)
    run_path = store.run_path(handle.run_id)
    if run_path.exists():
        raise FileExistsError(f"run directory already exists: {run_path}")

    store.save_run(handle)

    # Write the active-run pointer under <gitdir>/arctx-id if we are
    # inside a git repo. Living under .git/ means git itself never
    # tracks it, so there is no risk of accidental commits.
    written_arctx_id_path: str | None = None
    try:
        repo_root = find_repo_root()
        write_arctx_id(repo_root, handle.run_id)
        written_arctx_id_path = str(arctx_id_path(repo_root))
    except RuntimeError:
        # Not inside a git repo — skip pointer creation silently.
        pass

    installed_hook_path: str | None = None
    hook_warning: str | None = None

    # Activate requested extensions.
    enabled_extensions: list[str] = []
    if extensions:
        from arctx.ext import load_extension  # noqa: PLC0415
        from arctx.ext.base import InitContext  # noqa: PLC0415
        from arctx.ext.enabled import EnabledExtension, add_enabled  # noqa: PLC0415

        for ext_name in extensions:
            ext = load_extension(ext_name)  # raises KeyError for unknown names
            opts = dict(extension_options or {})
            if no_hooks:
                opts["ext_git_no_hooks"] = True
            git_hook_existed = False
            if ext.name == "git" and not opts.get("ext_git_no_hooks"):
                try:
                    git_hook_existed = (
                        find_repo_root() / ".git" / "hooks" / "post-rewrite"
                    ).exists()
                except RuntimeError:
                    git_hook_existed = False
            ctx = InitContext(
                run_id=handle.run_id,
                run_dir=str(run_path),
                options=opts,
            )
            ext.on_init(ctx)
            if ext.name == "git" and not opts.get("ext_git_no_hooks"):
                try:
                    hook_path = find_repo_root() / ".git" / "hooks" / "post-rewrite"
                    if hook_path.exists() and not git_hook_existed:
                        installed_hook_path = str(hook_path)
                    elif hook_path.exists() and git_hook_existed:
                        hook_warning = f"hook already exists: {hook_path}"
                except RuntimeError:
                    pass
            add_enabled(run_path, EnabledExtension(name=ext.name, version=ext.version, config={}))
            enabled_extensions.append(ext_name)

    return {
        "run_id": handle.run_id,
        "root_node_id": handle.root_node_id,
        "store_dir": resolved_store_dir,
        "arctx_id_path": written_arctx_id_path,
        "hook_path": installed_hook_path,
        "hook_warning": hook_warning,
        "enabled_extensions": enabled_extensions,
    }


def cli_init(args) -> int:
    """Entry point for ``arctx init`` subcommand.

    Prints the generated run_id to stdout on success.
    """
    import sys

    try:
        result = run_init_command(
            requirement_id=args.requirement_id,
            target_type=args.target_type,
            target_id=args.target_id,
            run_id=args.run_id,
            store_dir=args.store_dir,
            no_hooks=args.no_hooks,
            extensions=list(args.extension or []),
            extension_options=vars(args),
        )
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(result["run_id"])
    if result.get("hook_path"):
        print(
            f"hint: git hook installed at {result['hook_path']}",
            file=sys.stderr,
        )
    if result.get("hook_warning"):
        print(f"warning: {result['hook_warning']}", file=sys.stderr)
    return 0
