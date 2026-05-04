"""Artifact validation utilities."""

from __future__ import annotations

import ast
from typing import Any

from optagent.core.models import Artifact


class ArtifactValidator:
    """Validates generated artifacts for correctness and safety."""

    def validate(self, artifact: Artifact) -> dict[str, Any]:
        """Validate an artifact and return validation results.
        
        Checks:
        1. Syntax validity (for code artifacts)
        2. Safety (no forbidden operations)
        3. Structure (required elements present)
        """
        results = {
            "valid": True,
            "errors": [],
            "warnings": [],
        }

        if artifact.artifact_type == "code":
            self._validate_code(artifact, results)
        elif artifact.artifact_type == "config":
            self._validate_config(artifact, results)

        return results

    def _validate_code(self, artifact: Artifact, results: dict[str, Any]) -> None:
        """Validate code artifact."""
        content = artifact.content
        
        # Check syntax
        try:
            ast.parse(content)
        except SyntaxError as exc:
            results["valid"] = False
            results["errors"].append(f"Syntax error: {exc}")
            return

        # Check for forbidden operations
        forbidden = ["eval(", "exec(", "__import__", "subprocess"]
        for op in forbidden:
            if op in content:
                results["warnings"].append(f"Potentially unsafe operation: {op}")

        # Check structure
        if "class " not in content and "def " not in content:
            results["warnings"].append("No class or function definitions found")

    def _validate_config(self, artifact: Artifact, results: dict[str, Any]) -> None:
        """Validate config artifact."""
        # Basic structure check
        if not artifact.content.strip():
            results["valid"] = False
            results["errors"].append("Empty config")
