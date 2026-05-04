"""Multi-size evaluator that benchmarks at multiple scales.

This addresses the issue where optimizations look bad on small tensors
but win on larger sizes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

from optagent.evaluation.base import Evaluator
from optagent.core.models import Artifact, Evidence
from optagent.core.state import OptimizationState


@dataclass
class ScaleConfig:
    """Configuration for a single benchmark scale."""
    name: str
    parameters: dict[str, Any]
    description: str = ""


class MultiSizeEvaluator(Evaluator):
    """Evaluate artifacts across multiple workload sizes.

    Parameters
    ----------
    scales:
        List of scale configurations.
    base_evaluator:
        Base evaluator to use for each scale.
    aggregate_fn:
        Function to aggregate results across scales.
        Default: geometric mean of speedups.
    """

    def __init__(
        self,
        scales: list[ScaleConfig] | None = None,
        base_evaluator: Evaluator | None = None,
        aggregate_fn: Callable[[list[float]], float] | None = None,
    ) -> None:
        self.scales = scales or self._default_scales()
        self.base_evaluator = base_evaluator
        self.aggregate_fn = aggregate_fn or self._geometric_mean

    def evaluate(
        self,
        artifact: Artifact,
        state: OptimizationState,
    ) -> Evidence:
        """Evaluate artifact at all scales and aggregate results."""
        if self.base_evaluator is None:
            raise RuntimeError("MultiSizeEvaluator requires a base_evaluator")

        scale_results: list[dict[str, Any]] = []
        all_correct = True
        all_eligible = True

        for scale in self.scales:
            # Modify state for this scale
            scaled_state = self._apply_scale(state, scale)
            
            # Evaluate
            evidence = self.base_evaluator.evaluate(artifact, scaled_state)
            
            scale_results.append({
                "scale": scale.name,
                "speedup": evidence.speedup,
                "metric_value": evidence.metric_value,
                "baseline_value": evidence.baseline_value,
                "is_correct": evidence.is_correct,
                "is_eligible": evidence.is_eligible,
            })
            
            all_correct = all_correct and evidence.is_correct
            all_eligible = all_eligible and evidence.is_eligible

        # Aggregate speedups
        speedups = [
            r["speedup"] for r in scale_results
            if r["speedup"] is not None
        ]
        
        overall_speedup = None
        if speedups:
            overall_speedup = self.aggregate_fn(speedups)

        return Evidence(
            hypothesis_id=artifact.hypothesis_id,
            artifact_id=artifact.artifact_type,
            speedup=overall_speedup,
            is_correct=all_correct,
            is_eligible=all_eligible,
            details={
                "scale_results": scale_results,
                "scales_evaluated": len(self.scales),
            },
            raw_data=str(scale_results),
        )

    def is_available(self) -> bool:
        if self.base_evaluator is None:
            return False
        return self.base_evaluator.is_available()

    @staticmethod
    def _default_scales() -> list[ScaleConfig]:
        return [
            ScaleConfig(
                name="small",
                parameters={"batch_size": 1, "size_label": "small"},
                description="Small tensors / inference",
            ),
            ScaleConfig(
                name="medium",
                parameters={"batch_size": 16, "size_label": "medium"},
                description="Medium tensors",
            ),
            ScaleConfig(
                name="large",
                parameters={"batch_size": 64, "size_label": "large"},
                description="Large tensors / training",
            ),
        ]

    @staticmethod
    def _apply_scale(state: OptimizationState, scale: ScaleConfig) -> OptimizationState:
        """Create a modified state for the given scale."""
        # Create a shallow copy with modified parameters
        from dataclasses import replace
        
        if state.requirement is None:
            return state
        
        new_params = dict(state.requirement.parameters)
        new_params.update(scale.parameters)
        
        new_req = replace(
            state.requirement,
            parameters=new_params,
        )
        
        new_state = replace(state, requirement=new_req)
        return new_state

    @staticmethod
    def _geometric_mean(values: list[float]) -> float:
        """Compute geometric mean of speedups."""
        if not values:
            return 0.0
        log_sum = sum(math.log(v) for v in values if v > 0)
        return math.exp(log_sum / len(values))
