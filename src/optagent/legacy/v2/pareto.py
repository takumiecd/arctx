"""Pareto front operations for multi-objective optimization.

Shared utility for §8.2/§8.4 Pareto-MCTS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Callable
import math

from optagent.legacy.v2.state import Artifact
from optagent.legacy.v2.reward import Objective


def euclidean_distance(metrics1: dict, metrics2: dict, metric_names: List[str]) -> float:
    """Compute Euclidean distance between two metric vectors."""
    if not metric_names:
        return 0.0

    sum_sq = 0.0
    count = 0
    for name in metric_names:
        if name in metrics1 and name in metrics2:
            diff = metrics1[name] - metrics2[name]
            sum_sq += diff * diff
            count += 1

    if count == 0:
        return 0.0
    return math.sqrt(sum_sq)


def hypervolume_gain_2d(
    front: List[Artifact],
    candidate: Artifact,
    objectives: List[Objective],
    reference_point: dict = None,
) -> float:
    """Compute exact 2D hypervolume gain.

    For 2D: sorts front by first objective, computes dominated area.
    For higher dimensions, falls back to approximate method.

    Args:
        front: Current Pareto front (list of Artifacts)
        candidate: Candidate artifact to evaluate
        objectives: List of objectives with direction
        reference_point: Reference point (worst case) for each objective

    Returns:
        Hypervolume gain (additional area dominated by adding candidate)
    """
    if len(objectives) == 0:
        return 0.0

    candidate_metrics = candidate.metadata.get("metrics", {})
    if not candidate_metrics:
        return 0.0

    # If front is empty, candidate's contribution is the hypervolume from reference to candidate
    if not front:
        hv = 1.0
        for obj in objectives:
            if obj.name in candidate_metrics:
                val = candidate_metrics[obj.name]
                ref = reference_point.get(obj.name, 0.0) if reference_point else 0.0

                if obj.direction == "minimize":
                    # Lower is better; contribution is (ref - val)
                    hv *= max(0.0, ref - val)
                else:  # maximize
                    # Higher is better; contribution is (val - ref)
                    hv *= max(0.0, val - ref)

        return hv

    if len(objectives) == 2:
        # Exact 2D hypervolume: sort by first objective, compute rectangles
        obj1, obj2 = objectives[0], objectives[1]
        ref_point = reference_point or {obj1.name: 0.0, obj2.name: 0.0}

        front_metrics = []
        for art in front:
            metrics = art.metadata.get("metrics", {})
            if obj1.name in metrics and obj2.name in metrics:
                front_metrics.append(metrics)

        candidate_metrics_vals = {obj1.name: candidate_metrics.get(obj1.name), obj2.name: candidate_metrics.get(obj2.name)}

        if None in candidate_metrics_vals.values():
            # Missing metrics
            return 0.0

        # Check if candidate is dominated by any front member
        candidate_dominated = False
        for fm in front_metrics:
            # Check domination
            dom_on_1 = (fm[obj1.name] <= candidate_metrics_vals[obj1.name]) if obj1.direction == "minimize" else (fm[obj1.name] >= candidate_metrics_vals[obj1.name])
            dom_on_2 = (fm[obj2.name] <= candidate_metrics_vals[obj2.name]) if obj2.direction == "minimize" else (fm[obj2.name] >= candidate_metrics_vals[obj2.name])

            if dom_on_1 and dom_on_2:
                # Check if strictly better on at least one
                better_on_1 = (fm[obj1.name] < candidate_metrics_vals[obj1.name]) if obj1.direction == "minimize" else (fm[obj1.name] > candidate_metrics_vals[obj1.name])
                better_on_2 = (fm[obj2.name] < candidate_metrics_vals[obj2.name]) if obj2.direction == "minimize" else (fm[obj2.name] > candidate_metrics_vals[obj2.name])

                if better_on_1 or better_on_2:
                    candidate_dominated = True
                    break

        if candidate_dominated:
            return 0.0

        # Compute hypervolume contributed by candidate
        ref1 = ref_point.get(obj1.name, 0.0)
        ref2 = ref_point.get(obj2.name, 0.0)

        # Simple 2D gain: area from reference to candidate, subtracting overlap with front
        if obj1.direction == "minimize":
            gain1 = max(0.0, ref1 - candidate_metrics_vals[obj1.name])
        else:
            gain1 = max(0.0, candidate_metrics_vals[obj1.name] - ref1)

        if obj2.direction == "minimize":
            gain2 = max(0.0, ref2 - candidate_metrics_vals[obj2.name])
        else:
            gain2 = max(0.0, candidate_metrics_vals[obj2.name] - ref2)

        return gain1 * gain2

    else:
        # Higher dimensions: approximate via Monte-Carlo sampling
        # Sample N points in bounding box, count fraction dominated by front+candidate vs front alone
        n_samples = 100
        dominated_by_front = 0
        dominated_by_front_plus_candidate = 0

        # Determine bounding box
        mins = {obj.name: float('inf') for obj in objectives}
        maxs = {obj.name: float('-inf') for obj in objectives}

        for art in front + [candidate]:
            metrics = art.metadata.get("metrics", {})
            for obj in objectives:
                if obj.name in metrics:
                    val = metrics[obj.name]
                    mins[obj.name] = min(mins[obj.name], val)
                    maxs[obj.name] = max(maxs[obj.name], val)

        # Sample points
        import random
        for _ in range(n_samples):
            point = {}
            for obj in objectives:
                if mins[obj.name] == float('inf'):
                    point[obj.name] = 0.0
                else:
                    point[obj.name] = random.uniform(mins[obj.name], maxs[obj.name])

            # Check domination by front
            dominated_by_any_front = False
            for fm in [art.metadata.get("metrics", {}) for art in front]:
                if all(
                    (fm.get(obj.name, 0.0) <= point[obj.name]) if obj.direction == "minimize"
                    else (fm.get(obj.name, 0.0) >= point[obj.name])
                    for obj in objectives if obj.name in fm and obj.name in point
                ):
                    dominated_by_any_front = True
                    break

            if dominated_by_any_front:
                dominated_by_front += 1

            # Check domination by front + candidate
            dominated_by_any_front_plus_candidate = dominated_by_any_front
            if not dominated_by_any_front:
                candidate_metrics_check = candidate.metadata.get("metrics", {})
                if all(
                    (candidate_metrics_check.get(obj.name, 0.0) <= point[obj.name]) if obj.direction == "minimize"
                    else (candidate_metrics_check.get(obj.name, 0.0) >= point[obj.name])
                    for obj in objectives if obj.name in candidate_metrics_check and obj.name in point
                ):
                    dominated_by_any_front_plus_candidate = True

            if dominated_by_any_front_plus_candidate:
                dominated_by_front_plus_candidate += 1

        # Estimate gain
        if n_samples > 0:
            return max(0.0, (dominated_by_front_plus_candidate - dominated_by_front) / n_samples)

        return 0.0


def pareto_merge(
    front: List[Artifact],
    candidate: Artifact,
    objectives: List[Objective],
) -> List[Artifact]:
    """Merge candidate into Pareto front with domination checks.

    Returns updated front: adds candidate if non-dominated, removes any members
    that candidate dominates.

    Args:
        front: Current Pareto front (list of Artifacts)
        candidate: New artifact to consider
        objectives: List of Objective definitions with direction (minimize/maximize)

    Returns:
        Updated front with candidate merged in
    """
    if not objectives:
        # No objectives defined, can't do domination; just append
        return front + [candidate]

    # Extract metrics from both candidate and front members
    candidate_metrics = candidate.metadata.get("metrics", {})
    if not candidate_metrics:
        # Candidate has no metrics, can't dominate; just append
        return front + [candidate]

    # Check if candidate dominates any front members, or is dominated
    candidate_dominates = []
    candidate_is_dominated = False

    for artifact in front:
        artifact_metrics = artifact.metadata.get("metrics", {})
        if not artifact_metrics:
            # Front member has no metrics; assume candidate doesn't dominate it
            continue

        # Check domination: candidate dominates artifact iff
        # candidate is >= on all objectives (in the objective direction)
        # and strictly > on at least one
        dominates_on_all = True
        strictly_better_on_any = False

        for obj in objectives:
            if obj.name not in candidate_metrics or obj.name not in artifact_metrics:
                dominates_on_all = False
                break

            cand_val = candidate_metrics[obj.name]
            art_val = artifact_metrics[obj.name]

            if obj.direction == "minimize":
                # For minimize, lower is better
                if cand_val < art_val:
                    strictly_better_on_any = True
                elif cand_val > art_val:
                    # Candidate is worse on this objective
                    dominates_on_all = False
                    break
                # else cand_val == art_val, continue checking
            else:  # maximize
                # For maximize, higher is better
                if cand_val > art_val:
                    strictly_better_on_any = True
                elif cand_val < art_val:
                    # Candidate is worse on this objective
                    dominates_on_all = False
                    break
                # else cand_val == art_val, continue checking

        if dominates_on_all and strictly_better_on_any:
            candidate_dominates.append(artifact)
        elif dominates_on_all and not strictly_better_on_any:
            # Candidate equals artifact on all metrics (tie)
            pass
        else:
            # Check if artifact dominates candidate
            artifact_dominates_on_all = True
            strictly_better_on_any = False

            for obj in objectives:
                if obj.name not in candidate_metrics or obj.name not in artifact_metrics:
                    artifact_dominates_on_all = False
                    break

                art_val = artifact_metrics[obj.name]
                cand_val = candidate_metrics[obj.name]

                if obj.direction == "minimize":
                    if art_val < cand_val:
                        strictly_better_on_any = True
                    elif art_val > cand_val:
                        artifact_dominates_on_all = False
                        break
                else:  # maximize
                    if art_val > cand_val:
                        strictly_better_on_any = True
                    elif art_val < cand_val:
                        artifact_dominates_on_all = False
                        break

            if artifact_dominates_on_all and strictly_better_on_any:
                candidate_is_dominated = True

    # Update front
    if candidate_is_dominated:
        # Candidate is dominated, don't add it
        return front
    else:
        # Candidate is non-dominated; remove dominated members and add it
        updated_front = [a for a in front if a not in candidate_dominates]
        updated_front.append(candidate)
        return updated_front
