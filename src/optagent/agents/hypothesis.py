"""Hypothesis generation agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from optagent.core.state_model import Hypothesis
from optagent.protocol import WorkItemDir


class HypothesisAgent:
    """Generates optimization hypotheses.
    
    Strategies:
    - SeedStrategy: Template-based from known patterns
    - ExploitStrategy: Explore around past winners
    - ExploreStrategy: Expand to unexplored axes
    - RepairStrategy: Fix failures from previous rounds
    - LLMStrategy: Use LLM for novel structural changes
    """

    def __init__(self, strategy: str = "seed") -> None:
        self.strategy = strategy

    def generate(self, work_item: WorkItemDir) -> list[Hypothesis]:
        """Generate hypotheses from request."""
        request = work_item.read_request()
        requirements = request["requirements"]
        
        # Simple seed strategy example
        target_id = requirements.get("target_id", "unknown")
        
        hypotheses = [
            Hypothesis(
                id=f"h_seed_001",
                target_keys=[target_id],
                claim=f"{target_id} has unnecessary overhead in generic path",
                proposed_change="Add specialized path for target conditions",
                expected_effect="Lower latency for target dispatch keys",
                risk="May regress edge cases",
                files_expected=["kernels/ops/*.py"],
                stop_conditions=["correctness failure", "speedup below threshold"],
            )
        ]
        
        # Write response
        work_item.write_response({
            "hypotheses": [h.to_dict() for h in hypotheses],
            "strategy": self.strategy,
        })
        
        return hypotheses
