"""Built-in git extension."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from stag.ext.base import ExtensionBase, InitContext, Violation

if TYPE_CHECKING:
    import argparse

    from stag.core.run.handle import RunHandle


@dataclass
class GitNamespace:
    """Python API namespace for git extension verbs.

    Core ``RunHandle`` stays git-agnostic; git verbs are exposed as
    ``handle.git.<verb>``.
    """

    handle: "RunHandle"

    def commit(self, **kwargs: Any) -> object:
        from stag.ext.git.verbs.commit import commit_impl

        return commit_impl(self.handle, **kwargs)

    def adopt_rewrite(self, **kwargs: Any) -> object:
        from stag.ext.git.verbs.rewrite import adopt_rewrite_impl

        return adopt_rewrite_impl(self.handle, **kwargs)

    def revert(self, **kwargs: Any) -> object:
        from stag.ext.git.verbs.revert import revert_impl

        return revert_impl(self.handle, **kwargs)

    def cherry_pick(self, **kwargs: Any) -> object:
        from stag.ext.git.verbs.cherry_pick import cherry_pick_impl

        return cherry_pick_impl(self.handle, **kwargs)

    def reset(self, **kwargs: Any) -> object:
        from stag.ext.git.verbs.reset import reset_impl

        return reset_impl(self.handle, **kwargs)

    def merge(self, **kwargs: Any) -> object:
        from stag.ext.git.verbs.merge import merge_impl

        return merge_impl(self.handle, **kwargs)

    def verify(self, **kwargs: Any) -> object:
        from stag.ext.git.verbs.verify import verify_impl

        return verify_impl(self.handle, **kwargs)

    def branch_members(self, branch: str) -> set[str]:
        from stag.ext.git.queries import branch_members

        return branch_members(self.handle.run_graph, branch)

    def current_sha(self, transition_id: str) -> str | None:
        from stag.ext.git.queries import current_sha

        return current_sha(self.handle.run_graph, transition_id)

    def transition_by_sha(self, sha: str) -> str | None:
        from stag.ext.git.queries import transition_by_sha

        return transition_by_sha(self.handle.run_graph, sha)


class GitExtension(ExtensionBase):
    """Standard extension for git-backed STAG workflows."""

    name = "git"
    version = "0.1"

    def register_schema(self) -> None:
        # Import-time side effects register payload decoders/classes.
        import stag.ext.git.events  # noqa: F401
        import stag.ext.git.payloads  # noqa: F401

    def register_verbs(self, handle: "RunHandle") -> None:
        if hasattr(handle, self.name):
            return
        setattr(handle, self.name, GitNamespace(handle))

    def register_cli(self, subparsers: "argparse._SubParsersAction") -> None:
        from stag.cli.commands.git import add_parser, cli_git

        parser = add_parser(subparsers)
        parser.set_defaults(_stag_handler=cli_git)

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
        from stag.cli.paths import find_repo_root, write_stag_id
        from stag.ext.git.cli.hook import run_hook_install

        raw_repo_root = ctx.options.get("ext_git_repo_root")
        try:
            repo_root = Path(str(raw_repo_root)) if raw_repo_root else find_repo_root()
        except RuntimeError:
            return

        write_stag_id(repo_root, ctx.run_id)

        if ctx.options.get("ext_git_no_hooks"):
            return

        run_hook_install(repo_path=repo_root, force=False)

    def validate(self, handle: "RunHandle") -> list[Violation]:
        from stag.ext.git.verbs.verify import verify_impl

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


__all__ = ["GitExtension", "GitNamespace"]
