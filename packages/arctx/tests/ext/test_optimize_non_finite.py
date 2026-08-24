"""Non-finite metrics must not reach the canonical jsonl.

A diverged training run logging ``loss=NaN`` is an everyday event in the
flagship use case. NaN is not sortable -- every comparison is False, so
``min()``/``max()`` seeded on a NaN row return it as best in *both* directions
-- and it has no JSON spelling, so writing one puts bytes in the git-committed
canon that a strict parser refuses and jq silently turns into null.
"""

from __future__ import annotations

import json
import math

import pytest

from arctx.core._json import dumps
from arctx.ext.optimize.tables import value_kind


NON_FINITE = [float("nan"), float("inf"), float("-inf")]


@pytest.mark.parametrize("value", NON_FINITE)
def test_value_kind_refuses_non_finite(value):
    assert value_kind(value) is None


@pytest.mark.parametrize("value", [0, 1, -1, 0.0, 1.5, -2.5, 1e308])
def test_value_kind_still_accepts_finite_numbers(value):
    assert value_kind(value) == "number"


def test_bool_is_still_classified_before_number():
    assert value_kind(True) == "bool"


@pytest.mark.parametrize("value", NON_FINITE)
def test_the_serializer_refuses_rather_than_writing_a_bare_token(value):
    with pytest.raises(ValueError):
        dumps({"metrics": {"loss": value}})


def test_the_serializer_still_writes_ordinary_rows():
    assert json.loads(dumps({"b": 2, "a": 1.5})) == {"a": 1.5, "b": 2}


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity", "1e309"])
def test_the_cli_parser_refuses_every_non_finite_spelling(text):
    from arctx_cli.ext.optimize import _parse_scalar

    with pytest.raises(ValueError, match="finite"):
        _parse_scalar(text)


@pytest.mark.parametrize("text", ["0.17", "-3", "1e308", "true", "hello"])
def test_the_cli_parser_still_accepts_ordinary_values(text):
    from arctx_cli.ext.optimize import _parse_scalar

    value = _parse_scalar(text)
    if isinstance(value, float):
        assert math.isfinite(value)


def test_the_batch_path_reports_why(tmp_path):
    """`trial add --rows` is what a sweep script writes with json.dumps."""
    from arctx.ext.optimize.tables import _check_row
    from arctx.ext.optimize.payloads import TrialPayload

    row = TrialPayload(
        payload_id="pl_1",
        target_id="t_1",
        tables=("s",),
        config={"lr": 1.0},
        metrics={"loss": float("nan")},
    )
    reason = _check_row(row, {})
    assert reason is not None
    assert "finite" in reason
