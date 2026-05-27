"""Seed `.arctx/runs` with sample runs for TUI exploration.

Usage:
    PYTHONPATH=src python3 scripts/seed_sample_runs.py
"""

from __future__ import annotations

import shutil
from pathlib import Path

import arctx as arctx
from arctx import (
    NodePayload,
    Requirement,
    TransitionPayload,
)
from arctx.core.ids import opaque_id
from arctx.ext.git.payloads import CommitEntry, DiffSummary, GitChangePayload
from arctx.storage.jsonl import JsonlRunStore


STORE_DIR = Path(".arctx/runs")


def _wipe() -> None:
    if STORE_DIR.exists():
        shutil.rmtree(STORE_DIR)
    STORE_DIR.mkdir(parents=True, exist_ok=True)


def _tp(t_type: str, **content) -> TransitionPayload:
    return TransitionPayload(payload_id="_", target_id="_", type=t_type, content=dict(content))


def _np(text: str) -> NodePayload:
    return NodePayload(payload_id="_", target_id="_", type="note", content={"text": text})


# ---------------------------------------------------------------------------
# Demo 1: scheduling optimization with hyperparameter variants
# ---------------------------------------------------------------------------

def _scheduling_run(store: JsonlRunStore) -> None:
    """A scheduling optimization: baseline -> two variant branches."""
    req = Requirement("req_sched", "demo", "job_scheduling")
    run = arctx.init(req, run_id="scheduling-demo")

    # Baseline experiment.
    t_baseline = run.transition(
        [run.root_node_id],
        _tp("experiment", algorithm="FIFO", max_queue_size=100),
    )
    n_baseline = t_baseline.output_node_id
    run.attach(n_baseline, _np("makespan=142.0  wait_p95=38.0"))

    # Two sibling variants from baseline.
    t_sjf_opt = run.transition(
        [n_baseline],
        _tp("experiment", algorithm="SJF", max_queue_size=100),
    )
    t_sjf_pess = run.transition(
        [n_baseline],
        _tp("experiment", algorithm="SJF", max_queue_size=100, variant="pathological"),
    )
    n_sjf_opt = t_sjf_opt.output_node_id
    n_sjf_pess = t_sjf_pess.output_node_id
    run.attach(n_sjf_opt, _np("makespan=118.0  wait_p95=27.0 (optimistic)"))
    run.attach(n_sjf_pess, _np("makespan=135.0  wait_p95=33.0 (pathological)"))

    # Observe one of them.
    t_observe = run.transition(
        [n_sjf_opt],
        _tp("implementation", notes="deploy SJF to staging"),
    )
    run.attach(t_observe.output_node_id, _np("deployed successfully"))

    store.save_run(run)
    print(f"saved: {run.run_id}")


# ---------------------------------------------------------------------------
# Demo 2: kernel hyperparam sweep with GitChangePayload
# ---------------------------------------------------------------------------

def _kernel_run(store: JsonlRunStore) -> None:
    """A kernel optimization run exercising GitChangePayload."""
    req = Requirement("req_kern", "demo", "conv_kernel")
    run = arctx.init(req, run_id="kernel-opt-demo")

    # First suggestion.
    t1 = run.transition(
        [run.root_node_id],
        _tp("suggestion", param="sparse_threshold", value=0.5),
    )
    n1 = t1.output_node_id
    run.attach(n1, _np("threshold=0.5 → accuracy 87.2%"))

    # Attach GitChangePayload to the transition (typed subclass path).
    diff = DiffSummary(files_changed=3, insertions=42, deletions=8)
    commit_log = (
        CommitEntry(
            sha="a1b2c3d",
            subject="tune sparse threshold to 0.5",
            author="alice",
            date="2026-05-25T10:00:00+00:00",
        ),
    )
    run.run_graph.attach_payload(
        GitChangePayload(
            payload_id=opaque_id("pl"),
            target_id=t1.transition_id,
            branch="feat/sparse-tune",
            head_commit="a1b2c3d",
            diff_summary=diff,
            commit_log=commit_log,
        )
    )

    # Second iteration from result.
    t2 = run.transition(
        [n1],
        _tp("suggestion", param="sparse_threshold", value=0.3),
    )
    n2 = t2.output_node_id
    run.attach(n2, _np("threshold=0.3 → accuracy 89.1%"))

    # Cut the first result node (superseded).
    run.cut(n1, target_kind="node", reason="superseded by threshold=0.3 run")

    store.save_run(run)
    print(f"saved: {run.run_id}")


# ---------------------------------------------------------------------------
# Demo 3: multi-input join (solution synthesis)
# ---------------------------------------------------------------------------

def _synthesis_run(store: JsonlRunStore) -> None:
    """Two separate analyses joined into a synthesis transition."""
    req = Requirement("req_synth", "demo", "code_review")
    run = arctx.init(req, run_id="synthesis-demo")

    # Branch A: performance analysis.
    ta = run.transition(
        [run.root_node_id],
        _tp("analysis", domain="performance"),
    )
    na = ta.output_node_id
    run.attach(na, _np("hot path: matrix multiply bottleneck"))

    # Branch B: correctness analysis.
    tb = run.transition(
        [run.root_node_id],
        _tp("analysis", domain="correctness"),
    )
    nb = tb.output_node_id
    run.attach(nb, _np("edge case: empty input not handled"))

    # Join both analyses into a synthesis (multi-input transition).
    t_join = run.transition(
        [na, nb],
        _tp("synthesis", strategy="combined fix"),
    )
    n_synth = t_join.output_node_id
    run.attach(n_synth, _np("fix both: vectorize + add guard clause"))

    store.save_run(run)
    print(f"saved: {run.run_id}")


if __name__ == "__main__":
    _wipe()
    store = JsonlRunStore(STORE_DIR)
    _scheduling_run(store)
    _kernel_run(store)
    _synthesis_run(store)
    print("done.")
