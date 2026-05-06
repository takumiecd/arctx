"""Artifact building agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from optagent.legacy.v1.core.state_model import Artifact
from optagent.legacy.v1.protocol import WorkItemDir


class ArtifactBuilder:
    """Builds implementation artifacts from hypotheses.
    
    Modes:
    - NoCodeArtifact: Evaluate existing spec only
    - ParametricArtifact: Rule-based parameter changes
    - PatchArtifact: Generate reviewable patch
    - WorktreeArtifact: Isolated worktree implementation
    """

    def __init__(self, mode: str = "declare_only") -> None:
        self.mode = mode

    def build(self, work_item: WorkItemDir) -> Artifact:
        """Build artifact from hypothesis."""
        request = work_item.read_request()
        hypothesis = request["hypothesis"]
        
        artifact = Artifact(
            hypothesis_id=hypothesis["id"],
            artifact_type=self.mode,
            changed_files=[],
            candidate_specs=[f"{hypothesis['id']}_candidate"],
            registry_policy="declare_only",
            notes="Generated artifact from hypothesis",
        )
        
        work_item.write_response(artifact.to_dict())
        return artifact
