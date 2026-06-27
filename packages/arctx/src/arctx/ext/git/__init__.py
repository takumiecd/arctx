"""Built-in git extension."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from arctx.ext.base import CliCommand, ExtensionBase, InitContext, Violation

if TYPE_CHECKING:
    import argparse

    from arctx.core.run.handle import RunHandle


@dataclass
class GitNamespace:
    """Python API namespace for git extension verbs.

    Core ``RunHandle`` stays git-agnostic; git verbs are exposed as
    ``handle.git.<verb>``.
    """

    handle: "RunHandle"

    def commit(self, **kwargs: Any) -> object:
        from arctx.ext.git.verbs.commit import commit_impl

        return commit_impl(self.handle, **kwargs)

    def adopt_rewrite(self, **kwargs: Any) -> object:
        from arctx.ext.git.verbs.rewrite import adopt_rewrite_impl

        return adopt_rewrite_impl(self.handle, **kwargs)

    def revert(self, **kwargs: Any) -> object:
        from arctx.ext.git.verbs.revert import revert_impl

        return revert_impl(self.handle, **kwargs)

    def cherry_pick(self, **kwargs: Any) -> object:
        from arctx.ext.git.verbs.cherry_pick import cherry_pick_impl

        return cherry_pick_impl(self.handle, **kwargs)

    def reset(self, **kwargs: Any) -> object:
        from arctx.ext.git.verbs.reset import reset_impl

        return reset_impl(self.handle, **kwargs)

    def merge(self, **kwargs: Any) -> object:
        from arctx.ext.git.verbs.merge import merge_impl

        return merge_impl(self.handle, **kwargs)

    def verify(self, **kwargs: Any) -> object:
        from arctx.ext.git.verbs.verify import verify_impl

        return verify_impl(self.handle, **kwargs)

    def repo_add(self, **kwargs: Any) -> object:
        from arctx.ext.git.helpers.repo import resolve_worktree_path
        from arctx.ext.git.registry import resolve_repo_id

        repo_path = resolve_worktree_path(kwargs.get("repo_path"))
        return resolve_repo_id(self.handle, repo_path, slug=kwargs.get("slug"))

    def repos(self) -> list:
        from arctx.ext.git.registry import list_repos

        return list_repos(self.handle.run_graph)

    def branch_members(self, branch: str) -> set[str]:
        from arctx.ext.git.queries import branch_members

        return branch_members(self.handle.run_graph, branch)

    def current_sha(self, step_id: str) -> str | None:
        from arctx.ext.git.queries import current_sha

        return current_sha(self.handle.run_graph, step_id)

    def step_by_sha(self, sha: str) -> str | None:
        from arctx.ext.git.queries import step_by_sha

        return step_by_sha(self.handle.run_graph, sha)


class GitExtension(ExtensionBase):
    """Standard extension for git-backed ARCTX workflows."""

    name = "git"
    version = "0.1"
    description = "Integration with git to record commits and branches into the arctx graph."

    def register_schema(self) -> None:
        # Import-time side effects register payload decoders/classes.
        import arctx.ext.git.events  # noqa: F401
        import arctx.ext.git.payloads  # noqa: F401

    def register_verbs(self, handle: "RunHandle") -> None:
        if hasattr(handle, self.name):
            return
        setattr(handle, self.name, GitNamespace(handle))

    def cli_commands(self) -> list[CliCommand]:
        from arctx_cli.ext.git import add_parser, cli_git

        return [CliCommand(name=self.name, add_parser=add_parser, handler=cli_git)]

    def default_aliases(self) -> dict[str, str]:
        return {
            "branch": "git branch",
            "cherry-pick": "git cherry-pick",
            "commit": "git commit",
            "hook": "git hook",
            "merge": "git merge",
            "reset": "git reset",
            "revert": "git revert",
            "verify": "git verify",
        }

    def register_init_options(self, parser: "argparse.ArgumentParser") -> None:
        group = parser.add_argument_group("git extension")
        group.add_argument(
            "--git-no-hooks",
            dest="ext_git_no_hooks",
            action="store_true",
            help="With --extension git, skip installing git hooks",
        )
        group.add_argument(
            "--git-repo-root",
            dest="ext_git_repo_root",
            default=None,
            help="With --extension git, explicit git repository root",
        )

    def on_init(self, ctx: InitContext) -> None:
        from arctx.paths import find_repo_root, write_arctx_id
        from arctx_cli.ext.git.hook import run_hook_install

        raw_repo_root = ctx.options.get("ext_git_repo_root")
        try:
            repo_root = Path(str(raw_repo_root)) if raw_repo_root else find_repo_root()
        except RuntimeError:
            return

        try:
            write_arctx_id(repo_root, ctx.run_id)
        except OSError:
            pass

        if ctx.options.get("ext_git_no_hooks"):
            return

        try:
            run_hook_install(repo_path=repo_root, force=False)
        except OSError:
            pass

    def validate(self, handle: "RunHandle") -> list[Violation]:
        from arctx.ext.git.verbs.verify import verify_impl

        violations = verify_impl(handle)
        return [
            Violation(
                extension=self.name,
                kind=v.kind,
                message=v.message,
                details=dict(v.details),
            )
            for v in violations
        ]
    def guide_text(self) -> str:
        return """* `arctx git commit` : Record a git commit as a step in the arctx graph.
* `arctx git verify` : Run verification scripts and attach results to the graph.
* `arctx git branch` : Record a branch switch or creation.
"""

__all__ = ["GitExtension", "GitNamespace"]
