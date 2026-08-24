"""A revision string off a payload must never reach git as an option.

A run travels in a repository, so a run received from someone else is
attacker-controlled data. ``GitChangePayload.base_commit`` reads straight out
of the payload's metadata and used to be placed, unvalidated, in a revision
position ahead of ``head``. Git parses a leading dash there as an option, and
``git diff --output=<path>`` truncates that path — so merely *viewing* a shared
run destroyed a file of the sender's choosing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from arctx.core.gitref import MissingCommit, changed_files, commit_patch, diff_stat, resolve_commit
from arctx.ext.git.derive import derive_git_change, derive_patch
from arctx.ext.git.payloads import GitChangePayload


def _repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    run = lambda *a: subprocess.run(a, cwd=str(repo), capture_output=True, check=True)  # noqa: E731
    run("git", "init", "-q", ".")
    run("git", "config", "user.email", "a@b")
    run("git", "config", "user.name", "a")
    (repo / "f.txt").write_text("hello\n")
    run("git", "add", "f.txt")
    run("git", "commit", "-q", "-m", "first")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()
    return repo, head


def _evil_payload(head: str, victim: Path) -> GitChangePayload:
    return GitChangePayload(
        payload_id="pl_x",
        target_id="t_x",
        branch="main",
        head_commit=head,
        commits=(head,),
        metadata={"base_commit": f"--output={victim}"},
    )


def test_derive_does_not_write_the_file_named_by_base_commit(tmp_path):
    repo, head = _repo(tmp_path)
    victim = tmp_path / "victim.txt"
    victim.write_text("DO NOT DESTROY ME\n")

    payload = _evil_payload(head, victim)
    assert payload.base_commit.startswith("--output=")

    derived = derive_git_change(payload, repo_root=repo)
    derive_patch(payload, repo_root=repo)

    assert victim.read_text() == "DO NOT DESTROY ME\n"
    # The record does not resolve, so it degrades the documented way rather
    # than silently producing a diff from a bogus base.
    assert derived.available is False


@pytest.mark.parametrize("bad", ["--output=/tmp/x", "-O/tmp/x", "--ext-diff"])
def test_diff_family_refuses_an_option_shaped_base(tmp_path, bad):
    """An unresolvable base raises, exactly as an unresolvable head does.

    Callers that want to degrade rather than fail catch ``GitRefError`` — which
    is how ``derive_git_change`` turns this into ``available=False``.
    """
    repo, head = _repo(tmp_path)

    for call in (diff_stat, changed_files, commit_patch):
        with pytest.raises(MissingCommit):
            call(repo, head, bad)


def test_resolve_commit_refuses_a_leading_dash(tmp_path):
    repo, _head = _repo(tmp_path)
    with pytest.raises(MissingCommit):
        resolve_commit(repo, "--output=/tmp/x")


def test_a_real_base_still_diffs(tmp_path):
    """The guard must not break the ordinary two-commit case."""
    repo, base = _repo(tmp_path)
    (repo / "f.txt").write_text("hello\nworld\n")
    subprocess.run(["git", "add", "f.txt"], cwd=str(repo), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "second"], cwd=str(repo), capture_output=True, check=True
    )
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()

    stat = diff_stat(repo, head, base)
    assert stat.files_changed == 1
    assert stat.insertions == 1
    assert changed_files(repo, head, base) == ["f.txt"]

    # An abbreviated sha is a legitimate revision and must keep working.
    assert changed_files(repo, head, base[:8]) == ["f.txt"]
