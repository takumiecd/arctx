"""v2 domains — domain-specific instantiations of the optimization framework.

Corresponds to PLANNING_AND_RL.md §11.
"""

from optagent.legacy.v2.domains.code.state import CodeState, CodeArtifact
from optagent.legacy.v2.domains.code.action import EditCode, RunTests, RunBenchmark
from optagent.legacy.v2.domains.code.proposer import CodeProposer
from optagent.legacy.v2.domains.code.executor import CodeExecutor
from optagent.legacy.v2.domains.code.reward import create_code_reward_spec
from optagent.legacy.v2.domains.code.optimizer import CodeOptimizer

__all__ = [
    "CodeState",
    "CodeArtifact",
    "EditCode",
    "RunTests",
    "RunBenchmark",
    "CodeProposer",
    "CodeExecutor",
    "create_code_reward_spec",
    "CodeOptimizer",
]
