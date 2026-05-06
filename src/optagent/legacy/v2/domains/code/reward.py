"""§11.3 Reward instantiation — Lexicographic correctness ≫ test ≫ style.

Corresponds to PLANNING_AND_RL.md §11.3.
"""

from __future__ import annotations

from optagent.legacy.v2.reward import RewardSpec, Objective, Constraint, Lexicographic


def create_code_reward_spec() -> RewardSpec:
    """Create default RewardSpec for code optimization (§11.3).

    Objectives:
        1. correctness (maximize) — fraction of tests passing
        2. test_count (maximize) — number of tests executed
        3. style (maximize) — style score (0-1)

    Constraints:
        - Compilable (hard)
        - No banned patterns (hard)

    Aggregator: Lexicographic — correctness dominates everything.
    """
    objectives = [
        Objective(name="correctness", direction="maximize", reference=1.0),
        Objective(name="test_count", direction="maximize"),
        Objective(name="style", direction="maximize", reference=1.0),
    ]

    constraints = [
        # TODO: add compilable check
        # TODO: add banned pattern check
    ]

    aggregator = Lexicographic(["correctness", "test_count", "style"])

    return RewardSpec(
        objectives=objectives,
        constraints=constraints,
        aggregator=aggregator,
    )
