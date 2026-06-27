"""Tests for RunHandle.git.verify (descendant constraint, no real git required).

All git subprocess calls are mocked via ``unittest.mock.patch``.
"""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from arctx.ext.git.verbs.verify import VerifyViolation
from arctx.core.schema.requirements import Requirement
import arctx as arctx
from arctx.ext import attach_extensions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_handle(run_id: str = "run_test"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return attach_extensions(arctx.init(req, run_id=run_id), ["git"])


def _ensure_session(handle, user_id: str = "user", ws_id: str = "ws_1") -> None:
    handle.ensure_lane(user_id=user_id, lane_id=ws_id)


def _make_chain(handle, shas: list[str]):
    """Create a linear commit chain with the given SHAs.

    Returns list of (step, output_node_id) tuples.
    """
    _ensure_session(handle)
    result = []
    for i, sha in enumerate(shas):
        t = handle.git.commit(
            message=f"commit {i + 1}",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit=sha,
            dry_run=True,
        )
        result.append((t, t.output_node_id))
    return result


def _mock_git_ok():
    """Return a mock that makes git cat-file -e and merge-base succeed (return 0)."""

    def side_effect(cmd, **kwargs):
        m = MagicMock()
        m.returncode = 0
        return m

    return patch("subprocess.run", side_effect=side_effect)


def _mock_git_non_ancestor():
    """Return a mock where merge-base --is-ancestor exits 1 (not ancestor)."""

    def side_effect(cmd, **kwargs):
        m = MagicMock()
        if "merge-base" in cmd and "--is-ancestor" in cmd:
            m.returncode = 1
        else:
            # cat-file -e → exists
            m.returncode = 0
        return m

    return patch("subprocess.run", side_effect=side_effect)


def _mock_git_dead_sha():
    """Return a mock where git cat-file -e exits 1 (object missing)."""

    def side_effect(cmd, **kwargs):
        m = MagicMock()
        if "cat-file" in cmd:
            m.returncode = 1  # not found
        else:
            m.returncode = 0
        return m

    return patch("subprocess.run", side_effect=side_effect)


# ---------------------------------------------------------------------------
# Tests: happy path
# ---------------------------------------------------------------------------


class TestVerifyHappyPath:
    def test_empty_run_no_violations(self):
        """A run with no steps has nothing to check."""
        handle = _make_handle()
        with _mock_git_ok():
            violations = handle.git.verify()
        assert violations == []

    def test_single_commit_no_violations(self):
        """A single commit step has no input sha to check."""
        handle = _make_handle()
        _make_chain(handle, ["sha_A"])
        with _mock_git_ok():
            violations = handle.git.verify()
        # root → t1(sha_A): input is root node (no sha) → skip
        assert violations == []

    def test_linear_chain_two_commits_ok(self):
        """root → t1(sha_A) → n1 → t2(sha_B): sha_B is descendant of sha_A → ok."""
        handle = _make_handle()
        _make_chain(handle, ["sha_A", "sha_B"])

        with _mock_git_ok():
            violations = handle.git.verify()

        assert violations == []

    def test_linear_chain_three_commits_ok(self):
        """Three-commit chain with all git calls succeeding → no violations."""
        handle = _make_handle()
        _make_chain(handle, ["sha_A", "sha_B", "sha_C"])

        with _mock_git_ok():
            violations = handle.git.verify()

        assert violations == []


# ---------------------------------------------------------------------------
# Tests: non_descendant
# ---------------------------------------------------------------------------


class TestVerifyNonDescendant:
    def test_second_commit_not_descendant(self):
        """t2's sha is NOT a descendant of t1's sha → one non_descendant violation."""
        handle = _make_handle()
        chain = _make_chain(handle, ["sha_A", "sha_B"])
        t2 = chain[1][0]

        with _mock_git_non_ancestor():
            violations = handle.git.verify()

        assert len(violations) == 1
        v = violations[0]
        assert v.step_id == t2.step_id
        assert v.kind == "non_descendant"
        assert "sha_B" in v.message
        assert "sha_A" in v.message

    def test_non_descendant_details(self):
        """Violation details contain expected keys."""
        handle = _make_handle()
        chain = _make_chain(handle, ["sha_A", "sha_B"])
        t2 = chain[1][0]

        with _mock_git_non_ancestor():
            violations = handle.git.verify()

        v = violations[0]
        assert v.details["output_sha"] == "sha_B"
        assert v.details["input_sha"] == "sha_A"
        assert v.details["step_id"] == t2.step_id


# ---------------------------------------------------------------------------
# Tests: missing_sha
# ---------------------------------------------------------------------------


class TestVerifyMissingSha:
    def test_step_without_git_change_payload(self):
        """A Step with no GitChangePayload → 'missing_sha' violation."""
        handle = _make_handle()
        # Use plain step() which does NOT attach a GitChangePayload.
        from arctx.core.schema.payloads import StepPayload
        from arctx.core.ids import opaque_id

        t = handle.add_step(
            input_node_ids=(handle.root_node_id,),
            payload=StepPayload(
                payload_id=opaque_id("pl"),
                target_id="__placeholder__",  # will be replaced inside add_step_impl
                type="test",
            ),
        )

        with _mock_git_ok():
            violations = handle.git.verify()

        kinds = [v.kind for v in violations]
        assert "missing_sha" in kinds

    def test_missing_sha_step_id_correct(self):
        """The violation records the correct step_id."""
        handle = _make_handle()
        from arctx.core.schema.payloads import StepPayload
        from arctx.core.ids import opaque_id

        t = handle.add_step(
            input_node_ids=(handle.root_node_id,),
            payload=StepPayload(
                payload_id=opaque_id("pl"),
                target_id="__placeholder__",
                type="test",
            ),
        )

        with _mock_git_ok():
            violations = handle.git.verify()

        missing = [v for v in violations if v.kind == "missing_sha"]
        assert len(missing) == 1
        assert missing[0].step_id == t.step_id


# ---------------------------------------------------------------------------
# Tests: cut steps are skipped
# ---------------------------------------------------------------------------


class TestVerifyCutSteps:
    def test_cut_step_not_checked(self):
        """Cut steps are excluded from verification."""
        handle = _make_handle()
        chain = _make_chain(handle, ["sha_A", "sha_B"])
        t2 = chain[1][0]

        # Cut t2.
        handle.cut(
            target_id=t2.step_id,
            target_kind="step",
            reason="test cut",
        )

        with _mock_git_non_ancestor():
            violations = handle.git.verify()

        # t2 is cut → skipped; only t1 remains, and t1's input is root (no sha) → ok
        assert violations == []

    def test_downstream_of_cut_also_not_checked(self):
        """Steps downstream of a cut are also inactive → skipped."""
        handle = _make_handle()
        chain = _make_chain(handle, ["sha_A", "sha_B", "sha_C"])
        t1 = chain[0][0]

        # Cut t1 → t2 and t3 become inactive too.
        handle.cut(
            target_id=t1.step_id,
            target_kind="step",
            reason="cut root",
        )

        with _mock_git_non_ancestor():
            violations = handle.git.verify()

        assert violations == []


# ---------------------------------------------------------------------------
# Tests: root node as input is skipped
# ---------------------------------------------------------------------------


class TestVerifyRootNodeSkipped:
    def test_root_input_skipped(self):
        """root → t1: root has no sha, so input side is skipped. No violation."""
        handle = _make_handle()
        _ensure_session(handle)
        handle.git.commit(
            message="first",
            branch="main",
            user_id="user",
            lane_id="ws_1",
            head_commit="sha_A",
            dry_run=True,
        )

        # Even if merge-base would return non-ancestor, the root-input check
        # skips it because root is not in step_by_output_node.
        with _mock_git_non_ancestor():
            violations = handle.git.verify()

        # No t2 to create a chain, so nothing checked at git level.
        assert violations == []


# ---------------------------------------------------------------------------
# Tests: missing_input_sha
# ---------------------------------------------------------------------------


class TestVerifyMissingInputSha:
    def test_input_step_has_no_sha(self):
        """Input step has no GitChangePayload → 'missing_input_sha' violation."""
        handle = _make_handle()
        from arctx.core.schema.payloads import StepPayload
        from arctx.ext.git.payloads import GitChangePayload
        from arctx.core.ids import opaque_id
        from arctx.core.schema.graph import Node, Step

        graph = handle.run_graph

        # Manually insert: root → t_no_sha(no GitChangePayload) → n1 → t_with_sha(sha_B) → n2
        n1 = Node(node_id=opaque_id("n"))
        graph.add_node(n1)
        t_no_sha_id = opaque_id("t")
        from arctx.core.schema.graph import Step as Trans
        t_no_sha = Trans(
            step_id=t_no_sha_id,
            input_node_ids=(handle.root_node_id,),
            output_node_id=n1.node_id,
        )
        graph.add_step(t_no_sha)
        # Attach a generic payload (NOT GitChangePayload)
        tp = StepPayload(
            payload_id=opaque_id("pl"),
            target_id=t_no_sha_id,
            type="test",
        )
        graph.attach_payload(tp)

        n2 = Node(node_id=opaque_id("n"))
        graph.add_node(n2)
        t_with_sha_id = opaque_id("t")
        t_with_sha = Trans(
            step_id=t_with_sha_id,
            input_node_ids=(n1.node_id,),
            output_node_id=n2.node_id,
        )
        graph.add_step(t_with_sha)
        gcp = GitChangePayload(
            payload_id=opaque_id("pl"),
            target_id=t_with_sha_id,
            branch="main",
            head_commit="sha_B",
            diff_summary="",
            commit_log=(),
        )
        graph.attach_payload(gcp)

        with _mock_git_ok():
            violations = handle.git.verify()

        missing_input = [v for v in violations if v.kind == "missing_input_sha"]
        assert len(missing_input) == 1
        assert missing_input[0].step_id == t_with_sha_id


# ---------------------------------------------------------------------------
# Tests: dead_sha
# ---------------------------------------------------------------------------


class TestVerifyDeadSha:
    def test_dead_sha_detected(self):
        """When git cat-file -e reports sha is missing → 'dead_sha' violation."""
        handle = _make_handle()
        _make_chain(handle, ["sha_A", "sha_B"])

        with _mock_git_dead_sha():
            violations = handle.git.verify()

        dead = [v for v in violations if v.kind == "dead_sha"]
        assert len(dead) >= 1
