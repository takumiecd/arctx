"""Built-in git extension — records commits, never drives or watches git.

ARCTX is git-native at the storage layer (runs live in a repository, jsonl
merges with ``merge=union``, assets are references to git objects). That is
core and does not depend on this extension.

What this extension adds is narrow on purpose: a ``git_change`` record that
names commit hashes, plus read-time derivation of the diff those hashes stand
for. It does **not** run git on the user's behalf and does **not** install
hooks. Both of those were removed: driving git meant arctx's own subprocesses
tripped arctx's own hooks and double-recorded, and adopting bare git operations
meant guessing a graph position that ``arctx add`` tracks by other means. A
commit is recorded when the user says so, with ``arctx git add --commit``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from arctx.ext.base import CliCommand, ExtensionBase, InitContext, Violation

if TYPE_CHECKING:
    from arctx.core.run.handle import RunHandle


@dataclass
class GitNamespace:
    """Python API namespace for git extension verbs.

    Core ``RunHandle`` stays git-agnostic; git verbs are exposed as
    ``handle.git.<verb>``. Everything here reads — the write verbs
    (``commit``/``revert``/``merge``/``cherry_pick``/``reset``/
    ``adopt_rewrite``) were removed along with the hooks.
    """

    handle: "RunHandle"

    def verify(self, **kwargs: object) -> object:
        from arctx.ext.git.verbs.verify import verify_impl

        return verify_impl(self.handle, **kwargs)

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
    description = "Record git commits into the arctx graph and derive their diffs at read time."

    def register_schema(self) -> None:
        # Import-time side effects register payload decoders/classes.
        import arctx.ext.git.payloads  # noqa: F401

    def register_verbs(self, handle: "RunHandle") -> None:
        if hasattr(handle, self.name):
            return
        setattr(handle, self.name, GitNamespace(handle))

    def cli_commands(self) -> list[CliCommand]:
        from arctx_cli.ext.git import add_parser, cli_git

        return [CliCommand(name=self.name, add_parser=add_parser, handler=cli_git)]

    def default_aliases(self) -> dict[str, str]:
        return {"verify": "git verify"}

    def register_init_options(self, parser: object) -> None:
        group = parser.add_argument_group("git extension")  # type: ignore[attr-defined]
        group.add_argument(
            "--git-repo-root",
            dest="ext_git_repo_root",
            default=None,
            help="With --extension git, explicit git repository root",
        )

    def on_init(self, ctx: InitContext) -> None:
        """Point this checkout at the run. No hooks are installed."""
        from arctx.paths import find_repo_root, write_arctx_id

        raw_repo_root = ctx.options.get("ext_git_repo_root")
        try:
            repo_root = Path(str(raw_repo_root)) if raw_repo_root else find_repo_root()
        except RuntimeError:
            return

        try:
            write_arctx_id(repo_root, ctx.run_id)
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
        return """* `arctx git add --step T --commit SHA` : Record git commits on a step.
* `arctx git show --step T` : Show the records plus the diff git reports for them now.
* `arctx git verify` : Check the descendant constraint over all steps.
"""


__all__ = ["GitExtension", "GitNamespace"]
