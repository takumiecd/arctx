"""The lock has to exist everywhere the package installs.

`fcntl` is POSIX-only and was imported at the top of the storage module, which
every command reaches through `resolve_store`. Nothing in the packaging
restricts the platform, so `pip install arctx-cli` succeeded on Windows and
then every command — including read-only ones — died with
`ModuleNotFoundError: No module named 'fcntl'` before doing anything.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import tempfile
from pathlib import Path

import pytest

from arctx import init
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.storage import _locking
from arctx.storage._locking import FileLockUnavailableError, exclusive_lock
from arctx.storage.jsonl import JsonlRunStore


def test_this_platform_has_a_locking_primitive():
    assert _locking._HAVE_FCNTL or _locking._HAVE_MSVCRT, (
        "arctx serialises writers with a file lock; this platform offers neither "
        "fcntl nor msvcrt"
    )


def test_the_lock_is_exclusive():
    """Two holders of the same file must not be inside the block together."""
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lock"
        with path.open("a", encoding="utf-8") as first, path.open("a", encoding="utf-8") as second:
            with exclusive_lock(first):
                with pytest.raises(Exception):
                    # Non-blocking probe: a second exclusive hold must not be
                    # granted while the first is open.
                    _try_lock_without_waiting(second)


def _try_lock_without_waiting(handle) -> None:
    if _locking._HAVE_FCNTL:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    else:  # pragma: no cover - Windows
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)


def test_storage_imports_without_fcntl():
    """What a Windows interpreter sees when it imports the store.

    In a subprocess: reloading the module in-process would hand every later
    test a different copy of the exception classes.
    """
    script = textwrap.dedent(
        """
        import sys
        sys.modules["fcntl"] = None          # Windows has no fcntl
        import arctx.storage.jsonl           # every command reaches this
        from arctx.storage import _locking
        assert _locking._HAVE_FCNTL is False
        print("ok")
        """
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    result = subprocess.run([sys.executable, "-c", script], env=env,
                            capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_writing_without_any_lock_fails_loudly(monkeypatch):
    """Better a refused write than a silently unlocked one.

    Concurrent writers are a normal way to use arctx — parallel agents share a
    run — so losing the lock quietly would trade a loud failure for a corrupted
    run.
    """
    monkeypatch.setattr(_locking, "_HAVE_FCNTL", False)
    monkeypatch.setattr(_locking, "_HAVE_MSVCRT", False)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lock"
        with path.open("a", encoding="utf-8") as handle:
            with pytest.raises(FileLockUnavailableError):
                with exclusive_lock(handle):
                    pass


def test_reads_do_not_need_the_lock(monkeypatch):
    """A platform with no primitive still reads: only writers take the lock."""
    with tempfile.TemporaryDirectory() as td:
        run = init(Requirement(requirement_id="r", target_type="task", target_id="t"),
                   run_id="nolock")
        run.add_step([run.root_node_id], StepPayload(payload_id="_", target_id="_",
                                                     type="experiment"))
        store = JsonlRunStore(td)
        store.save_run(run)

        monkeypatch.setattr(_locking, "_HAVE_FCNTL", False)
        monkeypatch.setattr(_locking, "_HAVE_MSVCRT", False)
        assert len(store.load_run("nolock").run_graph.steps) == 1


def test_concurrent_writers_do_not_lose_each_other(tmp_path):
    """The reason the lock is there at all.

    Real processes, not threads: the lock has to hold across processes, which
    is how arctx is actually used (one agent per terminal).
    """
    run = init(Requirement(requirement_id="r", target_type="task", target_id="t"),
               run_id="race")
    store_dir = str(tmp_path / "runs")
    store = JsonlRunStore(store_dir)
    store.save_run(run)
    root = run.root_node_id

    script = textwrap.dedent(
        """
        import sys
        from arctx.core.schema.payloads import StepPayload
        from arctx.storage.jsonl import JsonlRunStore

        store_dir, root, index = sys.argv[1], sys.argv[2], sys.argv[3]
        store = JsonlRunStore(store_dir)
        handle = store.load_run("race")
        handle.add_step([root], StepPayload(payload_id="_", target_id="_",
                                            type="experiment", content={"i": index}))
        store.save_run(handle)
        """
    )

    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    procs = [
        subprocess.Popen([sys.executable, "-c", script, store_dir, root, str(index)], env=env)
        for index in range(8)
    ]
    for proc in procs:
        assert proc.wait(timeout=120) == 0

    assert len(store.load_run("race").run_graph.steps) == 8
