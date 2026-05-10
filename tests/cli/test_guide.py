"""Tests for the guide command topic system."""

from __future__ import annotations

import subprocess
import sys

import pytest

from optagent.cli.commands.guide import (
    GUIDES,
    TOPIC_SUMMARIES,
    TOPICS_EN,
    TOPICS_JA,
    run_guide_command,
    run_guide_list,
)

ALL_TOPICS = list(TOPIC_SUMMARIES.keys())


# ---------------------------------------------------------------------------
# run_guide_list
# ---------------------------------------------------------------------------


def test_list_returns_all_seven_topics():
    result = run_guide_list(lang="en")
    ids = [t["id"] for t in result["topics"]]
    assert len(ids) == 7
    for topic in ALL_TOPICS:
        assert topic in ids


def test_list_ja_returns_all_seven_topics():
    result = run_guide_list(lang="ja")
    ids = [t["id"] for t in result["topics"]]
    assert len(ids) == 7
    for topic in ALL_TOPICS:
        assert topic in ids


def test_list_includes_summaries():
    result = run_guide_list(lang="en")
    for entry in result["topics"]:
        assert entry["summary"], f"Empty summary for topic {entry['id']!r}"


# ---------------------------------------------------------------------------
# run_guide_command — default (overview)
# ---------------------------------------------------------------------------


def test_default_topic_is_overview():
    result = run_guide_command()
    assert result["topic"] == "overview"
    assert result["lang"] == "en"


def test_default_returns_nonempty_guide():
    result = run_guide_command()
    assert result["guide"].strip()


# ---------------------------------------------------------------------------
# run_guide_command — each topic, both languages
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("topic", ALL_TOPICS)
def test_topic_en_nonempty(topic):
    result = run_guide_command(lang="en", topic=topic)
    assert result["guide"].strip(), f"Empty guide for en/{topic}"
    assert result["topic"] == topic
    assert result["lang"] == "en"


@pytest.mark.parametrize("topic", ALL_TOPICS)
def test_topic_ja_nonempty(topic):
    result = run_guide_command(lang="ja", topic=topic)
    assert result["guide"].strip(), f"Empty guide for ja/{topic}"
    assert result["topic"] == topic
    assert result["lang"] == "ja"


# ---------------------------------------------------------------------------
# run_guide_command — content spot-checks
# ---------------------------------------------------------------------------


def test_topic_agent_contains_key_concepts():
    guide = run_guide_command(lang="en", topic="agent")["guide"]
    # Must mention RunGraph, Payload, and dump
    assert "RunGraph" in guide
    assert "Payload" in guide
    assert "dump" in guide


def test_topic_dump_contains_symbols():
    guide = run_guide_command(lang="en", topic="dump")["guide"]
    assert "→" in guide
    assert "⇢" in guide
    assert "✂" in guide
    assert "↻" in guide


def test_topic_overview_contains_core_concepts():
    guide = run_guide_command(lang="en", topic="overview")["guide"]
    assert "RunGraph" in guide
    assert "PlanPayload" in guide
    assert "append-only" in guide
    assert "dump" in guide


def test_topic_cut_mentions_cutpayload():
    guide = run_guide_command(lang="en", topic="cut")["guide"]
    assert "CutPayload" in guide
    assert "append-only" in guide


def test_topic_payloads_mentions_all_five():
    guide = run_guide_command(lang="en", topic="payloads")["guide"]
    for payload in ["NotePayload", "PlanPayload", "PredictionPayload", "ResultPayload", "CutPayload"]:
        assert payload in guide, f"Missing {payload} in payloads topic"


def test_topic_joins_mentions_multi_input():
    guide = run_guide_command(lang="en", topic="joins")["guide"]
    assert "input-node" in guide or "input_node" in guide


# ---------------------------------------------------------------------------
# run_guide_command — invalid topic raises ValueError
# ---------------------------------------------------------------------------


def test_invalid_topic_raises_value_error():
    with pytest.raises(ValueError, match="Unknown topic"):
        run_guide_command(topic="nonexistent_topic_xyz")


# ---------------------------------------------------------------------------
# CLI integration — nonzero exit + stderr on bad topic
# ---------------------------------------------------------------------------


def test_cli_bad_topic_nonzero_exit():
    result = subprocess.run(
        [sys.executable, "-m", "optagent.cli.main", "guide", "--topic", "does_not_exist"],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
        cwd=str(__import__("pathlib").Path(__file__).parent.parent.parent),
    )
    assert result.returncode != 0
    assert "does_not_exist" in result.stderr or "topic" in result.stderr.lower()


def test_cli_list_shows_seven_topics():
    result = subprocess.run(
        [sys.executable, "-m", "optagent.cli.main", "guide", "--list"],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
        cwd=str(__import__("pathlib").Path(__file__).parent.parent.parent),
    )
    assert result.returncode == 0
    for topic in ALL_TOPICS:
        assert topic in result.stdout


def test_cli_default_shows_overview():
    result = subprocess.run(
        [sys.executable, "-m", "optagent.cli.main", "guide"],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
        cwd=str(__import__("pathlib").Path(__file__).parent.parent.parent),
    )
    assert result.returncode == 0
    assert "RunGraph" in result.stdout or "optagent" in result.stdout


def test_cli_topic_agent():
    result = subprocess.run(
        [sys.executable, "-m", "optagent.cli.main", "guide", "--topic", "agent"],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
        cwd=str(__import__("pathlib").Path(__file__).parent.parent.parent),
    )
    assert result.returncode == 0
    assert "RunGraph" in result.stdout or "Payload" in result.stdout or "dump" in result.stdout


def test_cli_topic_dump():
    result = subprocess.run(
        [sys.executable, "-m", "optagent.cli.main", "guide", "--topic", "dump"],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "src"},
        cwd=str(__import__("pathlib").Path(__file__).parent.parent.parent),
    )
    assert result.returncode == 0
    assert "outline" in result.stdout
