"""Repo-relative paths are what git is handed, so they must be POSIX.

On Windows a path arrives with backslashes, and `git show <commit>:<path>`
only understands forward slashes. The whole string went through as one
segment, and git answered "exists on disk, but not in <commit>" — so every
asset recorded on Windows was unresolvable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arctx.core.gitref import GitRefError, join_repo_path, normalize_repo_path


def test_a_platform_path_never_reaches_git_with_a_backslash():
    """Fails on Windows before the fix; trivially true on POSIX, which is why
    it only meant something once CI started running there."""
    result = normalize_repo_path(Path("bench") / "result.txt")
    assert "\\" not in result
    assert result == "bench/result.txt"


def test_nested_platform_paths_too():
    result = normalize_repo_path(Path("a") / "b" / "c.txt")
    assert result == "a/b/c.txt"


def test_a_backslash_in_a_posix_filename_is_not_a_separator():
    """A blind replace would corrupt this: on POSIX, backslash is a legal
    character in a file name."""
    import sys

    if sys.platform == "win32":
        pytest.skip("backslash is a separator here, not a filename character")
    assert normalize_repo_path("weird\\name.txt") == "weird\\name.txt"


def test_forward_slashes_are_untouched():
    assert normalize_repo_path("bench/result.txt") == "bench/result.txt"


def test_the_repo_root_is_the_empty_path():
    assert normalize_repo_path("") == ""
    assert normalize_repo_path(".") == ""


def test_escaping_the_root_is_refused():
    with pytest.raises(GitRefError):
        normalize_repo_path("../outside.txt")


def test_join_keeps_posix_separators():
    assert join_repo_path("bench", str(Path("sub") / "x.txt")) == "bench/sub/x.txt"
