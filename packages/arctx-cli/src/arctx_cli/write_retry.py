"""Retry a write whose decision was overtaken by another writer.

`append_batch` refuses a batch built against a run state that has since
changed, rather than letting two writers both believe they were the only one
(see `ConcurrentWriteRejected`). That is the right thing to do at the storage
layer, but on its own it hands the loser of a race an error for something that
is not their fault and that has an obvious resolution: read the run again and
redo the decision against what is there now.

That is what this does. The retry has to re-run the *whole* cycle — load,
decide, write — because the stale part is the decision, not the append. Redoing
it produces exactly the sequential outcome: with two concurrent `reparent`
calls on one node, the loser now retires the winner's step instead of the one
it originally saw, which is what would have happened had they run in order.

Only a retryable rejection is retried. A lane that closed mid-write is not:
reloading finds it closed again, so retrying would spin instead of reporting.

Contending writers back off with jitter between attempts. Without it they
reload and resubmit in lockstep, so the same ones keep losing: measured with
simultaneous `arctx reparent` on one node, 12 writers left 4 failing and 20
left 11, even though the run stayed correct throughout. Under contention a
writer may legitimately need close to one retry per other writer, so the
attempt budget is generous — it exists to stop an unbounded spin against a run
something else is writing to continuously, not to ration ordinary contention.
"""

from __future__ import annotations

import random
import time
from typing import Callable, TypeVar

T = TypeVar("T")

DEFAULT_ATTEMPTS = 12
_BACKOFF_BASE = 0.01
_BACKOFF_CAP = 0.25


def with_write_retry(
    operation: Callable[[], T],
    *,
    attempts: int = DEFAULT_ATTEMPTS,
) -> T:
    """Run *operation*, redoing it when another writer got there first.

    *operation* must perform the whole load-decide-write cycle, since retrying
    only the write would resubmit the same stale decision.
    """
    from arctx.storage.jsonl import ConcurrentWriteRejected  # noqa: PLC0415

    last: ConcurrentWriteRejected | None = None
    for attempt in range(max(1, attempts)):
        try:
            return operation()
        except ConcurrentWriteRejected as exc:
            if not getattr(exc, "retryable", True):
                raise
            last = exc
            # Jittered exponential backoff. The jitter is the load-bearing
            # part: a fixed delay keeps the losers synchronised, so they
            # collide again on the next attempt.
            delay = min(_BACKOFF_CAP, _BACKOFF_BASE * (2**attempt))
            time.sleep(random.uniform(0, delay))
    assert last is not None
    raise ConcurrentWriteRejected(
        f"gave up after {attempts} attempts: {last}. Something is writing to "
        f"this run continuously; try again when it settles."
    ) from last
