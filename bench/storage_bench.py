"""Storage backend benchmark for ARCTX.

Measures real-wall-clock performance of JsonlRunStore and SqliteRunStore
across four graph sizes: 100, 1000, 10000, 100000 nodes.

Usage::

    PYTHONPATH=src python3 bench/storage_bench.py
    PYTHONPATH=src python3 bench/storage_bench.py --max-n 100000
    PYTHONPATH=src python3 bench/storage_bench.py --store jsonl
    PYTHONPATH=src python3 bench/storage_bench.py --store sqlite

Flags:
  --max-n <int>   Upper bound on graph sizes to bench (default: 10000)
  --store <str>   Which store to run: jsonl | sqlite | both (default: both)
"""

from __future__ import annotations

import argparse
import cProfile
import io
import pstats
import statistics
import tempfile
import time
from pathlib import Path
from typing import Callable

from arctx.core.run import RunHandle, init
from arctx.core.schema.payloads import PlanPayload, ResultPayload
from arctx.core.schema.requirements import Requirement
from arctx.storage.jsonl import JsonlRunStore
from arctx.storage.sqlite import SqliteRunStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQ = Requirement(requirement_id="bench_req", target_type="task", target_id="bench")

SIZES = [100, 1000, 10000, 100000]


def _make_plan_payload() -> PlanPayload:
    return PlanPayload(payload_id="pending", target_id="pending", intent="bench step")


def _make_result_payload() -> ResultPayload:
    return ResultPayload(
        payload_id="pending",
        target_id="pending",
        status="completed",
        metrics={"score": 0.5},
    )


def _grow_run(run: RunHandle, n_iterations: int) -> None:
    """Grow run by n_iterations plan+observe cycles.

    Each cycle adds: 1 Node, 1 InputTransition, 1 OutputTransition, 2 Payloads.
    After k iterations the run has (1 + k) nodes (root + k output nodes).
    """
    current_node_id = run.root_node_id
    for _ in range(n_iterations):
        it = run.plan([current_node_id], _make_plan_payload())
        ot = run.observe(it.input_transition_id, _make_result_payload())
        current_node_id = ot.to_node_id


def _median_of(fn: Callable, repeats: int = 3) -> float:
    """Return the median elapsed time (seconds) over `repeats` calls."""
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t0)
    return statistics.median(times)


# ---------------------------------------------------------------------------
# Core bench routine for one store class
# ---------------------------------------------------------------------------


def bench_store(store_cls, store_name: str, sizes: list[int]) -> dict[int, dict[str, float]]:
    """Run all measurements for one store class across all sizes.

    Returns a dict: {n: {metric: seconds}}.
    """
    results: dict[int, dict[str, float]] = {}

    for n in sizes:
        iters = n // 2  # plan+observe = 2 nodes per cycle → n/2 cycles ≈ n nodes
        if iters < 1:
            iters = 1

        with tempfile.TemporaryDirectory() as td:
            store = store_cls(td)
            run = init(_req(), run_id=f"bench_{store_name}_{n}")

            # --- build cost: grow to n/2 iterations, save after every save call
            build_start = time.perf_counter()
            current_node_id = run.root_node_id
            for _ in range(iters):
                it = run.plan([current_node_id], _make_plan_payload())
                ot = run.observe(it.input_transition_id, _make_result_payload())
                current_node_id = ot.to_node_id
                store.save_run(run)
            build_elapsed = time.perf_counter() - build_start

            # --- load_run: median of 3 loads
            run_id = run.run_id
            load_time = _median_of(lambda: store.load_run(run_id), repeats=3)

            # --- save_run no-op: load once, save without mutation, median of 3
            loaded = store.load_run(run_id)
            noop_time = _median_of(lambda: store.save_run(loaded), repeats=3)

            # --- save_run 1-add: load, add one plan+observe, save once
            # We measure just the save, not the plan+observe mutation
            def _save_1_add() -> None:
                fresh = store.load_run(run_id)
                prev_node = list(fresh.run_graph.nodes.keys())[-1]
                it2 = fresh.plan([prev_node], _make_plan_payload())
                fresh.observe(it2.input_transition_id, _make_result_payload())
                store.save_run(fresh)

            # Use a fresh store path so each repeat starts clean
            # We only measure 1 iteration here (state mutates each call)
            t0 = time.perf_counter()
            _save_1_add()
            add1_time = time.perf_counter() - t0

            results[n] = {
                "build": build_elapsed,
                "load_run": load_time,
                "save_noop": noop_time,
                "save_1add": add1_time,
            }

        print(f"  {store_name} N={n} done", flush=True)

    return results


# ---------------------------------------------------------------------------
# cProfile load_run
# ---------------------------------------------------------------------------


def profile_load_run(store_cls, store_name: str, n: int) -> str:
    """Build a run of size n, then profile load_run, return formatted top-15 output."""
    iters = max(n // 2, 1)

    with tempfile.TemporaryDirectory() as td:
        store = store_cls(td)
        run = init(_req(), run_id=f"prof_{store_name}_{n}")

        current_node_id = run.root_node_id
        for _ in range(iters):
            it = run.plan([current_node_id], _make_plan_payload())
            ot = run.observe(it.input_transition_id, _make_result_payload())
            current_node_id = ot.to_node_id
        store.save_run(run)

        run_id = run.run_id

        prof = cProfile.Profile()
        prof.enable()
        store.load_run(run_id)
        prof.disable()

    buf = io.StringIO()
    ps = pstats.Stats(prof, stream=buf)
    ps.sort_stats("cumulative")
    ps.print_stats(15)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def _fmt(seconds: float) -> str:
    return f"{seconds:.4f}s"


def print_table(store_name: str, results: dict[int, dict[str, float]]) -> None:
    print(f"\n=== {store_name} ===")
    header = f"{'N':<10} {'build':>12} {'load_run':>12} {'save_no_op':>12} {'save_1_add':>12}"
    print(header)
    print("-" * len(header))
    for n, m in sorted(results.items()):
        print(
            f"{n:<10} {_fmt(m['build']):>12} {_fmt(m['load_run']):>12}"
            f" {_fmt(m['save_noop']):>12} {_fmt(m['save_1add']):>12}"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _req() -> Requirement:
    return Requirement(requirement_id="bench_req", target_type="task", target_id="bench")


def main() -> None:
    parser = argparse.ArgumentParser(description="ARCTX storage benchmark")
    parser.add_argument(
        "--max-n",
        type=int,
        default=10000,
        help="Maximum graph size to bench (default: 10000)",
    )
    parser.add_argument(
        "--store",
        choices=["jsonl", "sqlite", "both"],
        default="both",
        help="Which store to benchmark (default: both)",
    )
    args = parser.parse_args()

    active_sizes = [s for s in SIZES if s <= args.max_n]
    if not active_sizes:
        print(f"No sizes <= {args.max_n}. Smallest size is {SIZES[0]}.")
        return

    profile_n = active_sizes[-1]  # profile at largest active size

    store_map = {
        "jsonl": (JsonlRunStore, "JsonlRunStore"),
        "sqlite": (SqliteRunStore, "SqliteRunStore"),
    }

    run_stores = []
    if args.store in ("jsonl", "both"):
        run_stores.append(store_map["jsonl"])
    if args.store in ("sqlite", "both"):
        run_stores.append(store_map["sqlite"])

    all_results: dict[str, dict[int, dict[str, float]]] = {}
    profiles: dict[str, str] = {}

    for store_cls, store_name in run_stores:
        print(f"\nBenching {store_name} (sizes={active_sizes}) ...", flush=True)
        all_results[store_name] = bench_store(store_cls, store_name, active_sizes)

        print(f"Profiling {store_name} load_run at N={profile_n} ...", flush=True)
        profiles[store_name] = profile_load_run(store_cls, store_name, profile_n)

    # --- Print tables ---
    for store_name, results in all_results.items():
        print_table(store_name, results)

    # --- Print profiles ---
    print(f"\n=== load_run profile (N={profile_n}) ===")
    for store_name, prof_output in profiles.items():
        print(f"\n{store_name}:")
        # Trim the header pstats always emits and print the rest
        lines = prof_output.splitlines()
        for line in lines:
            print("  " + line)


if __name__ == "__main__":
    main()
