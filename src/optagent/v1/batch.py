"""Batch optimization runner."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from optagent.core.store import StateStore
from optagent.v1.core.manager import ManagerAgent
from optagent.v1.core.models import Requirement
from optagent.v1.core.state import OptimizationState
from optagent.v1.reporting.batch import BatchReport, BatchResult


class BatchOptimizer:
    """Run multiple optimization requirements in a batch.

    Parameters
    ----------
    manager_factory:
        Callable that returns a configured ManagerAgent.
    work_dir:
        Base directory for all batch runs.
    max_workers:
        Number of parallel workers (1 = sequential).
    """

    def __init__(
        self,
        manager_factory: Callable[[], ManagerAgent],
        work_dir: str | Path,
        max_workers: int = 1,
    ) -> None:
        self.manager_factory = manager_factory
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers

    def run(
        self,
        requirements: list[tuple[str, Requirement]],
        resume: bool = True,
    ) -> BatchReport:
        """Run optimization for all requirements.

        Parameters
        ----------
        requirements:
            List of (requirement_id, requirement) tuples.
        resume:
            If True, skip requirements with existing state files.

        Returns
        -------
        BatchReport with aggregated results.
        """
        report = BatchReport()
        report.total = len(requirements)

        # Filter completed requirements
        pending = []
        for req_id, req in requirements:
            state_file = self.work_dir / req_id / "state_round_1.json"
            if resume and state_file.exists():
                try:
                    state = OptimizationState.from_file(state_file)
                    result = BatchResult(
                        requirement_id=req_id,
                        requirement=req,
                        state=state,
                        success=True,
                    )
                    report.results.append(result)
                    self._update_stats(report, result)
                    continue
                except Exception:
                    pass
            pending.append((req_id, req))

        # Execute pending requirements
        if self.max_workers == 1:
            for req_id, req in pending:
                result = self._run_single(req_id, req)
                report.results.append(result)
                self._update_stats(report, result)
        else:
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._run_single, req_id, req): (req_id, req)
                    for req_id, req in pending
                }
                for future in as_completed(futures):
                    result = future.result()
                    report.results.append(result)
                    self._update_stats(report, result)

        # Sort and compute best speedup
        report.results.sort(key=lambda r: r.requirement_id)
        speedups = []
        for result in report.results:
            # v2 compatibility
            if result.state and hasattr(result.state, 'algorithm'):
                for ev in result.state.algorithm.evidence:
                    if hasattr(ev, 'speedup') and ev.speedup is not None:
                        speedups.append(ev.speedup)
            # v1.5 compatibility
            elif result.state and hasattr(result.state, 'evidence'):
                for evidence in result.state.evidence:
                    if evidence.speedup is not None:
                        speedups.append(evidence.speedup)
        if speedups:
            report.best_speedup = max(speedups)

        return report

    def _run_single(self, req_id: str, requirement: Requirement) -> BatchResult:
        """Run a single optimization requirement."""
        run_dir = self.work_dir / req_id
        run_dir.mkdir(parents=True, exist_ok=True)

        result = BatchResult(
            requirement_id=req_id,
            requirement=requirement,
        )

        start = time.monotonic()
        try:
            manager = self.manager_factory()
            if hasattr(manager, "work_dir"):
                manager.work_dir = run_dir
            if hasattr(manager, "state_store"):
                manager.state_store = StateStore(run_dir)
            state = manager.optimize(requirement)
            result.state = state
            result.success = True
        except Exception as exc:
            result.error = f"{type(exc).__name__}: {exc}"
        finally:
            result.duration_sec = time.monotonic() - start

        return result

    @staticmethod
    def _update_stats(report: BatchReport, result: BatchResult) -> None:
        if result.success:
            report.successful += 1
            # v2 compatibility: check algorithm.evidence for decisions
            if result.state and hasattr(result.state, 'algorithm'):
                evidence = result.state.algorithm.evidence
                if evidence:
                    last_ev = evidence[-1]
                    if getattr(last_ev, 'decision_recommendation', '') == 'accepted':
                        report.accepted += 1
                    else:
                        report.rejected += 1
            elif result.state and hasattr(result.state, 'decisions'):
                # v1.5 compatibility
                if result.state.decisions:
                    if result.state.decisions[-1].accepted:
                        report.accepted += 1
                    else:
                        report.rejected += 1
        else:
            report.failed += 1


# Type alias for cleaner imports
from typing import Callable
