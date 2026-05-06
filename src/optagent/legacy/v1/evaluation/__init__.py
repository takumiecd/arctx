"""Evaluation framework for optimization artifacts."""

from optagent.legacy.v1.evaluation.base import Evaluator
from optagent.legacy.v1.evaluation.multi_size import MultiSizeEvaluator

__all__ = ["Evaluator", "MultiSizeEvaluator"]
