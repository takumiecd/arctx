"""STAG path resolution — re-exports from stag_api.paths.

All path logic lives in stag_api.paths. This module re-exports the public
symbols so that CLI code can use ``from stag_cli.paths import ...``.
"""

from stag_api.paths import (  # noqa: F401
    find_repo_root,
    read_stag_id,
    resolve_git_dir,
    resolve_stag_home,
    resolve_store_dir,
    runs_dir,
    stag_id_path,
    write_stag_id,
)

__all__ = [
    "find_repo_root",
    "read_stag_id",
    "resolve_git_dir",
    "resolve_stag_home",
    "resolve_store_dir",
    "runs_dir",
    "stag_id_path",
    "write_stag_id",
]
