"""An exclusive file lock that exists on every platform arctx installs on.

`fcntl` is POSIX-only, and it was imported at the top of the storage module —
which every command reaches through `resolve_store`. Nothing in the packaging
says otherwise, so `pip install arctx-cli` succeeds on Windows and then every
command dies before it starts:

    ModuleNotFoundError: No module named 'fcntl'

The lock serialises writers to one run directory. Both implementations below
are advisory and process-wide, which is what that needs: they keep two `arctx`
processes from interleaving appends to the same files.
"""

from __future__ import annotations

import contextlib
import os
import time
from typing import IO, Iterator

try:  # POSIX
    import fcntl

    _HAVE_FCNTL = True
except ImportError:  # Windows
    fcntl = None  # type: ignore[assignment]
    _HAVE_FCNTL = False

try:  # Windows
    import msvcrt

    _HAVE_MSVCRT = True
except ImportError:  # POSIX
    msvcrt = None  # type: ignore[assignment]
    _HAVE_MSVCRT = False


class FileLockUnavailableError(RuntimeError):
    """No locking primitive on this platform.

    Raised rather than silently writing unlocked: concurrent writers are a
    normal way to use arctx (parallel agents share a run), and losing the lock
    without saying so trades a loud failure for a corrupted run.
    """


#: How long to keep retrying a Windows lock before giving up. `msvcrt.locking`
#: with LK_LOCK gives up on its own after roughly ten seconds; a writer waiting
#: on a slow batch is not an error, so retry rather than fail.
_WINDOWS_LOCK_TIMEOUT = 120.0
_WINDOWS_RETRY_DELAY = 0.05


@contextlib.contextmanager
def exclusive_lock(handle: IO[str]) -> Iterator[None]:
    """Hold an exclusive advisory lock on *handle* for the block."""
    _acquire(handle)
    try:
        yield
    finally:
        _release(handle)


def _acquire(handle: IO[str]) -> None:
    if _HAVE_FCNTL:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return
    if _HAVE_MSVCRT:
        handle.seek(0)
        deadline = time.monotonic() + _WINDOWS_LOCK_TIMEOUT
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(_WINDOWS_RETRY_DELAY)
    raise FileLockUnavailableError(
        f"no file locking primitive available on {os.name!r}: "
        "arctx serialises concurrent writers with one, and will not write without it"
    )


def _release(handle: IO[str]) -> None:
    if _HAVE_FCNTL:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return
    if _HAVE_MSVCRT:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            # Already gone (the handle is closing anyway). Releasing a lock we
            # do not hold is not worth failing a completed write over.
            pass
