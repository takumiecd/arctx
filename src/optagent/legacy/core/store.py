"""JSONL-backed run store for Evidence Graph records."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from optagent.legacy.core.ids import timestamp_id
from optagent.legacy.core.schema import AttemptRecord, DecisionRecord, FindingRecord, RequirementRecord


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StateStore:
    """Filesystem store for optimization runs.

    Layout:
        run.json
        requirements.json
        attempts.jsonl
        decisions.jsonl
        findings.jsonl
        artifacts/
        raw/
        reports/
    """

    root: Path
    run_id: str | None = None

    def __init__(self, root: str | Path, run_id: str | None = None) -> None:
        self.root = Path(root)
        self.run_id = run_id
        self.root.mkdir(parents=True, exist_ok=True)
        for dirname in ("artifacts", "raw", "reports"):
            (self.root / dirname).mkdir(exist_ok=True)
        self._ensure_run_file()

    @property
    def attempts_path(self) -> Path:
        return self.root / "attempts.jsonl"

    @property
    def decisions_path(self) -> Path:
        return self.root / "decisions.jsonl"

    @property
    def findings_path(self) -> Path:
        return self.root / "findings.jsonl"

    def save_requirement(self, requirement: RequirementRecord) -> Path:
        path = self.root / "requirements.json"
        self._write_json(path, requirement.to_dict())
        return path

    def append_attempt(self, attempt: AttemptRecord) -> None:
        self._append_jsonl(self.attempts_path, attempt.to_dict())
        if attempt.decision is not None:
            self.append_decision(attempt.decision)
        if attempt.finding is not None:
            self.append_finding(attempt.finding)

    def append_decision(self, decision: DecisionRecord) -> None:
        self._append_jsonl(self.decisions_path, decision.to_dict())

    def append_finding(self, finding: FindingRecord) -> None:
        self._append_jsonl(self.findings_path, finding.to_dict())

    def save_artifact(self, name: str, content: str | bytes) -> Path:
        path = self.root / "artifacts" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        return path

    def save_raw_output(self, name: str, content: str | bytes) -> Path:
        path = self.root / "raw" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        return path

    def read_attempts(self) -> list[dict[str, Any]]:
        if not self.attempts_path.exists():
            return []
        return [
            json.loads(line)
            for line in self.attempts_path.read_text().splitlines()
            if line.strip()
        ]

    def _ensure_run_file(self) -> None:
        path = self.root / "run.json"
        if path.exists():
            return
        run_id = self.run_id or timestamp_id(self.root.name or "run")
        self._write_json(
            path,
            {
                "run_id": run_id,
                "created_at": _now_iso(),
                "schema": "optagent.evidence_graph.v1",
                "layout": {
                    "requirements": "requirements.json",
                    "attempts": "attempts.jsonl",
                    "decisions": "decisions.jsonl",
                    "findings": "findings.jsonl",
                    "artifacts": "artifacts/",
                    "raw": "raw/",
                    "reports": "reports/",
                },
            },
        )

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

    @staticmethod
    def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data, sort_keys=True) + "\n")
