"""stag CLI init command."""

from __future__ import annotations

import argparse
from pathlib import Path

import stag
from stag.cli.context import resolve_store
from stag.cli.paths import find_repo_root, resolve_store_dir, write_stag_id
from stag.core.schema.requirements import Requirement


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
        help="Directory to save runs (default: <STAG_HOME>/runs)",
    )
    parser.add_argument(
        "--no-stag-id-commit",
        action="store_true",
        help="Create .stag-id but skip suggesting git add (no-op flag for scripting)",
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
    from stag.ext import list_available, load_extension  # noqa: PLC0415

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
        If None, defaults to ``<STAG_HOME>/runs``.
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
    dict with at least ``run_id``, ``root_node_id``, and ``stag_id_path``
    (the path where ``.stag-id`` was written, or None if not in a git repo).

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

    handle = stag.init(requirement, run_id=run_id)

    store = resolve_store(resolved_store_dir)
    run_path = store.run_path(handle.run_id)
    if run_path.exists():
        raise FileExistsError(f"run directory already exists: {run_path}")

    store.save_run(handle)

    # Write .stag-id in the repo root if we are inside a git repo.
    written_stag_id_path: str | None = None
    try:
        repo_root = find_repo_root()
        write_stag_id(repo_root, handle.run_id)
        written_stag_id_path = str(repo_root / ".stag-id")
    except RuntimeError:
        # Not inside a git repo — skip .stag-id creation silently.
        pass

    # Install git hooks unless opted out.
    installed_hook_path: str | None = None
    hook_warning: str | None = None
    if not no_hooks:
        try:
            repo_root_for_hooks = find_repo_root()
            from stag.cli.commands.hook import run_hook_install  # noqa: PLC0415
            hook_result = run_hook_install(repo_path=repo_root_for_hooks, force=False)
            if hook_result["status"] == "installed":
                installed_hook_path = hook_result["hook_path"]
            elif hook_result["status"] == "skipped":
                hook_warning = hook_result["message"]
        except RuntimeError:
            # Not inside a git repo — skip hook install silently.
            pass

    # Activate requested extensions.
    enabled_extensions: list[str] = []
    if extensions:
        from stag.ext import load_extension  # noqa: PLC0415
        from stag.ext.base import InitContext  # noqa: PLC0415
        from stag.ext.enabled import EnabledExtension, add_enabled  # noqa: PLC0415

        for ext_name in extensions:
            ext = load_extension(ext_name)  # raises KeyError for unknown names
            opts = dict(extension_options or {})
            ctx = InitContext(
                run_id=handle.run_id,
                run_dir=str(run_path),
                options=opts,
            )
            ext.on_init(ctx)
            add_enabled(run_path, EnabledExtension(name=ext.name, version=ext.version, config={}))
            enabled_extensions.append(ext_name)

    return {
        "run_id": handle.run_id,
        "root_node_id": handle.root_node_id,
        "store_dir": resolved_store_dir,
        "stag_id_path": written_stag_id_path,
        "hook_path": installed_hook_path,
        "hook_warning": hook_warning,
        "enabled_extensions": enabled_extensions,
    }


def cli_init(args) -> int:
    """Entry point for ``stag init`` subcommand.

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
    if result.get("stag_id_path"):
        print(
            f"hint: run 'git add {result['stag_id_path']}' to track this run in git",
            file=sys.stderr,
        )
    if result.get("hook_path"):
        print(
            f"hint: git hook installed at {result['hook_path']}",
            file=sys.stderr,
        )
    if result.get("hook_warning"):
        print(f"warning: {result['hook_warning']}", file=sys.stderr)
    return 0
