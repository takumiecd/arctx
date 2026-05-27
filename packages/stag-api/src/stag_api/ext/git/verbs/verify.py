"""RunHandle.git.verify implementation."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from stag_api.ext.git.helpers.repo import resolve_worktree_path
from stag_api.ext.git.queries import current_sha

if TYPE_CHECKING:
    from stag_api.core.run.handle import RunHandle


@dataclass(frozen=True)
class VerifyViolation:
    """One violation of the descendant constraint."""

    transition_id: str
    kind: Literal["dead_sha", "non_descendant", "missing_sha", "missing_input_sha"]
    message: str
    details: dict = field(default_factory=dict)  # type: ignore[assignment]


def _sha_exists(sha: str, repo_path: Path) -> bool:
    result = subprocess.run(
        ["git", "cat-file", "-e", sha],
        cwd=str(repo_path),
        capture_output=True,
    )
    return result.returncode == 0


def _is_ancestor(ancestor_sha: str, descendant_sha: str, repo_path: Path) -> Literal["ok", "non_descendant", "dead_sha"]:
    if not _sha_exists(ancestor_sha, repo_path):
        return "dead_sha"
    if not _sha_exists(descendant_sha, repo_path):
        return "dead_sha"

    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor_sha, descendant_sha],
        cwd=str(repo_path),
        capture_output=True,
    )
    if result.returncode == 0:
        return "ok"
    if result.returncode == 1:
        return "non_descendant"
    return "dead_sha"


def verify_impl(
    self: "RunHandle",
    *,
    repo_path: Path | None = None,
    skip_dead_sha_check: bool = False,
) -> list[VerifyViolation]:
    """Verify the descendant constraint over all non-cut transitions."""
    from stag_api.core.cuts import inactive_transition_ids  # noqa: PLC0415

    graph = self.run_graph
    resolved_repo_path = resolve_worktree_path(repo_path)

    inactive = inactive_transition_ids(graph)
    violations: list[VerifyViolation] = []

    for t_id, transition in graph.transitions.items():
        if t_id in inactive:
            continue

        output_sha = current_sha(graph, t_id)

        if output_sha is None:
            violations.append(
                VerifyViolation(
                    transition_id=t_id,
                    kind="missing_sha",
                    message=(
                        f"Transition {t_id} has no GitChangePayload; "
                        "cannot verify descendant constraint"
                    ),
                    details={"transition_id": t_id},
                )
            )
            continue

        for input_node_id in transition.input_node_ids:
            if input_node_id not in graph.transition_by_output_node:
                continue

            in_t_id = graph.transition_by_output_node[input_node_id]
            input_sha = current_sha(graph, in_t_id)

            if input_sha is None:
                violations.append(
                    VerifyViolation(
                        transition_id=t_id,
                        kind="missing_input_sha",
                        message=(
                            f"Transition {t_id}: input node {input_node_id} "
                            f"has no GitChangePayload on its producing transition {in_t_id}"
                        ),
                        details={
                            "transition_id": t_id,
                            "input_node_id": input_node_id,
                            "input_transition_id": in_t_id,
                            "output_sha": output_sha,
                        },
                    )
                )
                continue

            if skip_dead_sha_check:
                result = subprocess.run(
                    ["git", "merge-base", "--is-ancestor", input_sha, output_sha],
                    cwd=str(resolved_repo_path),
                    capture_output=True,
                )
                if result.returncode == 0:
                    status: Literal["ok", "non_descendant", "dead_sha"] = "ok"
                elif result.returncode == 1:
                    status = "non_descendant"
                else:
                    status = "dead_sha"
            else:
                status = _is_ancestor(input_sha, output_sha, resolved_repo_path)

            if status == "ok":
                continue

            if status == "non_descendant":
                violations.append(
                    VerifyViolation(
                        transition_id=t_id,
                        kind="non_descendant",
                        message=(
                            f"Transition {t_id}: output sha {output_sha!r} is NOT "
                            f"a descendant of input sha {input_sha!r} "
                            f"(input node {input_node_id})"
                        ),
                        details={
                            "transition_id": t_id,
                            "input_node_id": input_node_id,
                            "input_sha": input_sha,
                            "output_sha": output_sha,
                        },
                    )
                )
            else:
                violations.append(
                    VerifyViolation(
                        transition_id=t_id,
                        kind="dead_sha",
                        message=(
                            f"Transition {t_id}: sha {output_sha!r} or input sha "
                            f"{input_sha!r} is not present in git object store"
                        ),
                        details={
                            "transition_id": t_id,
                            "input_node_id": input_node_id,
                            "input_sha": input_sha,
                            "output_sha": output_sha,
                        },
                    )
                )

    return violations
