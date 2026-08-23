"""Check a run directory, and set aside what cannot be read.

A run is a handful of append-only jsonl files, and every reader parses all of
them. One unreadable line therefore takes the whole run with it: `dump`, `show`,
`explore` and `topics` all stop, and the only thing left working is `list`,
which reads `run.json` alone. That is a bad place to leave someone whose
experiment history lives in the file — so this module answers two questions the
error message cannot: *what exactly is broken*, and *how do I get the rest of my
run back*.

Repair never deletes. Broken lines move to `<file>.broken`, which is not part of
the run, and the file is rewritten without them. If the line held a real record,
it is still there to hand-edit and put back.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from arctx.storage.jsonl import JsonlRunStore

#: The files a run is made of. `run.json` and `graph.json` are whole-file JSON;
#: the rest are one record per line.
JSONL_FILES: tuple[str, ...] = (
    "nodes.jsonl",
    "steps.jsonl",
    "payloads.jsonl",
    "lanes.jsonl",
    "work_sessions.jsonl",
    "work_events.jsonl",
    "lane_events.jsonl",
)

JSON_FILES: tuple[str, ...] = ("run.json", "graph.json")

_EXCERPT = 120


@dataclass(frozen=True)
class BrokenLine:
    file: str
    line_number: int
    reason: str
    text: str

    @property
    def excerpt(self) -> str:
        return self.text if len(self.text) <= _EXCERPT else self.text[: _EXCERPT - 3] + "..."

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "line": self.line_number,
            "reason": self.reason,
            "text": self.excerpt,
        }


@dataclass(frozen=True)
class FileReport:
    name: str
    exists: bool
    rows: int
    broken: tuple[BrokenLine, ...]

    def to_dict(self) -> dict:
        return {
            "file": self.name,
            "exists": self.exists,
            "rows": self.rows,
            "broken": [line.to_dict() for line in self.broken],
        }


@dataclass(frozen=True)
class Diagnosis:
    run_id: str
    run_path: Path
    files: tuple[FileReport, ...]
    pending_journal: bool
    load_error: str | None

    @property
    def broken(self) -> tuple[BrokenLine, ...]:
        return tuple(line for report in self.files for line in report.broken)

    @property
    def healthy(self) -> bool:
        return not self.broken and self.load_error is None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "run_path": str(self.run_path),
            "healthy": self.healthy,
            "pending_journal": self.pending_journal,
            "load_error": self.load_error,
            "files": [report.to_dict() for report in self.files],
            "broken": [line.to_dict() for line in self.broken],
        }


def diagnose(store: JsonlRunStore, run_id: str) -> Diagnosis:
    """Read every file of *run_id* without giving up on the first bad line."""
    run_path = store.run_path(run_id)
    if not run_path.exists():
        raise KeyError(f"unknown run_id: {run_id}")

    reports = [_scan_json(run_path, name) for name in JSON_FILES]
    reports += [_scan_jsonl(run_path, name) for name in JSONL_FILES]

    load_error: str | None = None
    if not any(report.broken for report in reports):
        try:
            store.load_run(run_id)
        except Exception as exc:  # noqa: BLE001 — the point is to report it
            load_error = f"{type(exc).__name__}: {exc}"

    return Diagnosis(
        run_id=run_id,
        run_path=run_path,
        files=tuple(reports),
        # A journal left behind means a write was interrupted; the next write
        # replays it. Worth reporting either way.
        pending_journal=(run_path / ".append.journal").exists(),
        load_error=load_error,
    )


def repair(store: JsonlRunStore, run_id: str) -> tuple[Diagnosis, dict[str, int]]:
    """Move unparsable lines to ``<file>.broken`` so the rest of the run loads.

    Returns the diagnosis it acted on and how many lines were set aside per
    file. Files with nothing wrong are not touched at all.
    """
    diagnosis = diagnose(store, run_id)
    moved: dict[str, int] = {}

    for report in diagnosis.files:
        if not report.broken or not report.name.endswith(".jsonl"):
            continue
        path = diagnosis.run_path / report.name
        lines = path.read_text(encoding="utf-8").splitlines()
        bad_numbers = {line.line_number for line in report.broken}

        kept = [line for number, line in enumerate(lines, start=1) if number not in bad_numbers]
        removed = [line for number, line in enumerate(lines, start=1) if number in bad_numbers]

        broken_path = path.with_suffix(path.suffix + ".broken")
        with broken_path.open("a", encoding="utf-8") as fh:
            for line in removed:
                fh.write(line + "\n")

        text = "".join(line + "\n" for line in kept)
        path.write_text(text, encoding="utf-8")
        moved[report.name] = len(removed)

    return diagnosis, moved


def _scan_jsonl(run_path: Path, name: str) -> FileReport:
    path = run_path / name
    if not path.exists():
        return FileReport(name=name, exists=False, rows=0, broken=())

    rows = 0
    broken: list[BrokenLine] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except ValueError as exc:
            broken.append(BrokenLine(file=name, line_number=number, reason=str(exc), text=line))
        else:
            rows += 1
    return FileReport(name=name, exists=True, rows=rows, broken=tuple(broken))


def _scan_json(run_path: Path, name: str) -> FileReport:
    path = run_path / name
    if not path.exists():
        return FileReport(name=name, exists=False, rows=0, broken=())
    text = path.read_text(encoding="utf-8")
    try:
        json.loads(text)
    except ValueError as exc:
        # A whole-file JSON document is one "line" as far as repair goes, and
        # repair deliberately does not touch it: losing run.json loses the run.
        return FileReport(
            name=name,
            exists=True,
            rows=0,
            broken=(BrokenLine(file=name, line_number=1, reason=str(exc), text=text[:_EXCERPT]),),
        )
    return FileReport(name=name, exists=True, rows=1, broken=())
