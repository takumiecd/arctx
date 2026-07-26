"""Tests for read-time derivation of GitChangePayload views.

"jsonl は事実、見た目は導出": the record stores commit hashes and a branch;
subjects, diff stats, file lists, and patch text come out of git on demand. A
commit missing from the clone must degrade to an explicit marker, never to
stale text or a crash — so these tests build real temporary repositories.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from arctx.core.gitref import (
    CommitInfo,
    DiffStat,
    MissingCommit,
    changed_files,
    commit_exists,
    commit_info,
    commit_infos,
    commit_patch,
    diff_stat,
)
from arctx.ext.git.derive import (
    MISSING_COMMIT_NOTE,
    NO_REPOSITORY_NOTE,
    derive_git_change,
    derive_patch,
)
from arctx.ext.git.payloads import GitChangePayload

ABSENT_SHA = "0" * 40


def _run(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        args, cwd=str(cwd), capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _commit(repo: Path, message: str) -> str:
    _run(["git", "add", "-A"], repo)
    _run(["git", "commit", "-q", "-m", message], repo)
    return _run(["git", "rev-parse", "HEAD"], repo)


@pytest.fixture()
def repo(tmp_path):
    """A repo with two commits: base (1 file) then a 2-file change."""
    path = tmp_path / "repo"
    path.mkdir()
    _run(["git", "init", "-q", "-b", "main"], path)
    _run(["git", "config", "user.email", "test@example.com"], path)
    _run(["git", "config", "user.name", "Test User"], path)
    (path / "a.txt").write_text("one\n", encoding="utf-8")
    base = _commit(path, "base commit")

    (path / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    (path / "b.txt").write_text("new file\n", encoding="utf-8")
    head = _commit(path, "add b and extend a")
    return path, base, head


def _payload(head: str, *, commits=(), base: str | None = None) -> GitChangePayload:
    return GitChangePayload(
        payload_id="pl_g",
        target_id="t_1",
        branch="main",
        head_commit=head,
        commits=commits,
        metadata={"base_commit": base} if base else {},
    )


# ---------------------------------------------------------------------------
# gitref primitives
# ---------------------------------------------------------------------------


def test_commit_exists(repo):
    path, _base, head = repo
    assert commit_exists(path, head) is True
    assert commit_exists(path, ABSENT_SHA) is False
    assert commit_exists(path, "") is False


def test_commit_info_reads_metadata_from_git(repo):
    path, _base, head = repo
    info = commit_info(path, head)
    assert isinstance(info, CommitInfo)
    assert info.sha == head
    assert info.subject == "add b and extend a"
    assert "Test User" in info.author
    assert info.date


def test_commit_info_raises_for_absent_commit(repo):
    path, _base, _head = repo
    with pytest.raises(MissingCommit):
        commit_info(path, ABSENT_SHA)


def test_commit_infos_skips_absent_commits(repo):
    path, base, head = repo
    infos = commit_infos(path, [base, ABSENT_SHA, head])
    assert [info.sha for info in infos] == [base, head]


def test_diff_stat_against_first_parent(repo):
    path, _base, head = repo
    stat = diff_stat(path, head)
    assert isinstance(stat, DiffStat)
    assert stat.files_changed == 2
    assert stat.insertions == 2
    assert stat.deletions == 0


def test_diff_stat_against_explicit_base(repo):
    path, base, head = repo
    assert diff_stat(path, head, base).files_changed == 2


def test_changed_files_lists_paths(repo):
    path, base, head = repo
    assert sorted(changed_files(path, head, base)) == ["a.txt", "b.txt"]


def test_commit_patch_returns_diff_text(repo):
    path, base, head = repo
    text, truncated, byte_count = commit_patch(path, head, base)
    assert "b.txt" in text
    assert "+two" in text
    assert truncated is False
    assert byte_count == len(text.encode("utf-8"))


def test_commit_patch_truncates(repo):
    path, base, head = repo
    text, truncated, byte_count = commit_patch(path, head, base, max_bytes=20)
    assert truncated is True
    assert len(text) <= 20
    assert byte_count > 20


def test_gitref_raises_for_absent_commit(repo):
    path, _base, _head = repo
    for call in (diff_stat, changed_files, commit_patch):
        with pytest.raises(MissingCommit):
            call(path, ABSENT_SHA)


# ---------------------------------------------------------------------------
# derive_git_change
# ---------------------------------------------------------------------------


def test_derive_reads_stats_and_log_from_the_repository(repo):
    path, base, head = repo
    derived = derive_git_change(_payload(head, commits=(head,), base=base), path)

    assert derived.available is True
    assert derived.note is None
    assert derived.head_commit == head
    assert derived.branch == "main"
    assert derived.diff_stat.files_changed == 2
    assert sorted(derived.files) == ["a.txt", "b.txt"]
    assert [entry.subject for entry in derived.commit_log] == ["add b and extend a"]


def test_derive_excludes_arctx_run_data_from_the_diff(repo):
    """Recording commit N lands in commit N+1, so `.arctx/` is not the change."""
    path, base, _head = repo
    (path / ".arctx" / "runs").mkdir(parents=True)
    (path / ".arctx" / "runs" / "nodes.jsonl").write_text("{}\n", encoding="utf-8")
    (path / "c.txt").write_text("real work\n", encoding="utf-8")
    head = _commit(path, "work plus its own bookkeeping")

    derived = derive_git_change(_payload(head, commits=(head,), base=base), path)
    assert derived.available is True
    assert derived.files == ("a.txt", "b.txt", "c.txt")
    assert derived.diff_stat.files_changed == 3

    text, _truncated, _byte_count, note = derive_patch(_payload(head, base=base), path)
    assert note is None
    assert ".arctx" not in text


def test_derive_defaults_to_first_parent_when_no_base_recorded(repo):
    path, _base, head = repo
    derived = derive_git_change(_payload(head), path)
    assert derived.available is True
    assert derived.diff_stat.files_changed == 2


def test_derive_marks_a_commit_missing_from_this_clone(repo):
    path, _base, _head = repo
    derived = derive_git_change(_payload(ABSENT_SHA), path)

    assert derived.available is False
    assert derived.note == MISSING_COMMIT_NOTE
    # The record's own facts survive; only the derived view is empty.
    assert derived.head_commit == ABSENT_SHA
    assert derived.branch == "main"
    assert derived.commit_log == ()
    assert derived.files == ()
    assert derived.diff_stat == DiffStat()


def test_derive_marks_an_empty_head_commit_missing(repo):
    path, _base, _head = repo
    derived = derive_git_change(_payload(""), path)
    assert derived.available is False
    assert derived.note == MISSING_COMMIT_NOTE


def test_derive_reports_when_there_is_no_repository(tmp_path, monkeypatch):
    outside = tmp_path / "not_a_repo"
    outside.mkdir()
    monkeypatch.chdir(outside)
    derived = derive_git_change(_payload(ABSENT_SHA))
    assert derived.available is False
    assert derived.note == NO_REPOSITORY_NOTE


def test_derive_never_raises_for_a_bad_reference(repo):
    path, _base, _head = repo
    # Whatever is wrong, callers get a structured answer, not an exception.
    assert derive_git_change(_payload("not-a-sha"), path).available is False


def test_summary_line_renders_the_marker_when_unavailable(repo):
    path, _base, _head = repo
    line = derive_git_change(_payload(ABSENT_SHA), path).summary_line()
    assert MISSING_COMMIT_NOTE in line


def test_summary_line_renders_subject_and_stats_when_available(repo):
    path, base, head = repo
    line = derive_git_change(_payload(head, commits=(head,), base=base), path).summary_line()
    assert "add b and extend a" in line
    assert "2 files" in line


def test_derived_to_dict_is_json_ready(repo):
    path, base, head = repo
    data = derive_git_change(_payload(head, commits=(head,), base=base), path).to_dict()
    assert data["available"] is True
    assert data["diff_stat"]["files_changed"] == 2
    assert data["commit_log"][0]["subject"] == "add b and extend a"
    assert data["files"] == ["a.txt", "b.txt"]


# ---------------------------------------------------------------------------
# derive_patch
# ---------------------------------------------------------------------------


def test_derive_patch_returns_text(repo):
    path, base, head = repo
    text, truncated, byte_count, note = derive_patch(_payload(head, base=base), path)
    assert note is None
    assert "b.txt" in text
    assert truncated is False
    assert byte_count > 0


def test_derive_patch_marks_a_missing_commit(repo):
    path, _base, _head = repo
    text, truncated, byte_count, note = derive_patch(_payload(ABSENT_SHA), path)
    assert note == MISSING_COMMIT_NOTE
    assert text == ""
    assert truncated is False
    assert byte_count == 0


# ---------------------------------------------------------------------------
# the record itself
# ---------------------------------------------------------------------------


def test_payload_stores_no_derived_text():
    data = _payload("abc123", commits=("abc123",)).to_dict()
    assert set(data) == {
        "payload_id",
        "payload_type",
        "target_kind",
        "target_id",
        "branch",
        "head_commit",
        "commits",
        "metadata",
    }


def test_commit_shas_falls_back_to_head_commit():
    assert _payload("abc123").commit_shas == ("abc123",)
    assert _payload("abc123", commits=("a", "b")).commit_shas == ("a", "b")
    assert _payload("").commit_shas == ()


def test_round_trip_through_payload_from_dict():
    from arctx.core.schema.payloads import payload_from_dict

    original = _payload("abc123", commits=("abc123", "def456"), base="base1")
    restored = payload_from_dict(original.to_dict())
    assert isinstance(restored, GitChangePayload)
    assert restored.commits == ("abc123", "def456")
    assert restored.base_commit == "base1"
    assert restored.to_dict() == original.to_dict()
