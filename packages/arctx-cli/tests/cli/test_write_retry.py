"""Losing a race should be invisible, not an error the user has to handle.

`append_batch` refuses a batch built against a state that has since changed.
That is right at the storage layer, but on its own it hands the loser an error
for something that is not their fault. Redoing the whole load-decide-write
cycle turns it into the sequential outcome.
"""

from __future__ import annotations

import pytest

from arctx.storage.jsonl import ConcurrentWriteRejected
from arctx_cli.write_retry import with_write_retry


def test_a_stale_rejection_is_retried_until_it_lands():
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConcurrentWriteRejected("someone else got there first")
        return "written"

    assert with_write_retry(operation) == "written"
    assert calls["n"] == 3


def test_a_lane_closed_rejection_is_not_retried():
    """Reloading finds the lane closed again — retrying would only spin."""
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        raise ConcurrentWriteRejected("lane L was closed", retryable=False)

    with pytest.raises(ConcurrentWriteRejected, match="closed"):
        with_write_retry(operation)
    assert calls["n"] == 1


def test_it_gives_up_rather_than_spinning_forever():
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        raise ConcurrentWriteRejected("still losing")

    with pytest.raises(ConcurrentWriteRejected, match="gave up after"):
        with_write_retry(operation, attempts=3)
    assert calls["n"] == 3


def test_other_errors_pass_straight_through():
    def operation():
        raise ValueError("a real problem")

    with pytest.raises(ValueError, match="a real problem"):
        with_write_retry(operation)


def test_a_successful_operation_runs_exactly_once():
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        return 42

    assert with_write_retry(operation) == 42
    assert calls["n"] == 1


def test_contending_writers_back_off_instead_of_starving():
    """Without jitter the losers reload in lockstep and keep losing.

    Measured with simultaneous `arctx reparent` on one node before the backoff:
    12 writers left 4 failing and 20 left 11, though the run stayed correct.
    """
    import arctx_cli.write_retry as wr

    assert wr.DEFAULT_ATTEMPTS >= 12, "an N-way race needs close to N retries"

    slept: list[float] = []
    real_sleep = wr.time.sleep
    wr.time.sleep = slept.append
    try:
        calls = {"n": 0}

        def operation():
            calls["n"] += 1
            if calls["n"] < 5:
                raise ConcurrentWriteRejected("lost again")
            return "ok"

        assert with_write_retry(operation) == "ok"
    finally:
        wr.time.sleep = real_sleep

    assert len(slept) == 4
    assert all(0 <= d <= 0.25 for d in slept), slept
    assert len(set(slept)) > 1, "a fixed delay keeps the losers synchronised"
