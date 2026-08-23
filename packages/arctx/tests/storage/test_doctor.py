"""Getting a run back after one line goes bad.

Every reader parses every line, so a single unparsable line stops `dump`,
`show`, `explore` and `topics` alike — everything except `list`, which only
reads run.json. Before `doctor` the way out was hand-editing jsonl.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from arctx import init
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.storage.doctor import diagnose, repair
from arctx.storage.jsonl import BrokenRunFileError, JsonlRunStore


@pytest.fixture()
def run_dir():
    with tempfile.TemporaryDirectory() as td:
        run = init(Requirement(requirement_id="r", target_type="task", target_id="t"),
                   run_id="doc")
        for index in range(3):
            run.add_step([run.root_node_id] if index == 0 else [tip],
                         StepPayload(payload_id="_", target_id="_", type="experiment",
                                     content={"n": index}))
            tip = list(run.run_graph.steps.values())[-1].output_node_id
        store = JsonlRunStore(td)
        store.save_run(run)
        yield store, Path(td) / "doc"


def _tear(path: Path) -> None:
    """Append the kind of half-written line an interrupted write leaves."""
    with path.open("a", encoding="utf-8") as fh:
        fh.write('{"payload_id": "pl_x", "target_id": "n_x", "pay')


def test_a_healthy_run_is_reported_healthy(run_dir):
    store, _ = run_dir
    diagnosis = diagnose(store, "doc")
    assert diagnosis.healthy
    assert diagnosis.broken == ()


def test_a_torn_line_names_its_file_and_line_number(run_dir):
    store, path = run_dir
    _tear(path / "payloads.jsonl")

    diagnosis = diagnose(store, "doc")
    assert not diagnosis.healthy
    assert len(diagnosis.broken) == 1
    broken = diagnosis.broken[0]
    assert broken.file == "payloads.jsonl"
    assert broken.line_number == 4
    assert "pl_x" in broken.excerpt


def test_loading_says_where_to_look(run_dir):
    """The old error was "Unterminated string at column 49" and nothing else."""
    store, path = run_dir
    _tear(path / "payloads.jsonl")

    with pytest.raises(BrokenRunFileError) as excinfo:
        store.load_run("doc")
    message = str(excinfo.value)
    assert "payloads.jsonl" in message
    assert "line 4" in message
    assert "arctx doctor" in message


def test_diagnose_reads_past_the_first_bad_line(run_dir):
    """A report that stops at the first problem is a worse error message."""
    store, path = run_dir
    _tear(path / "payloads.jsonl")
    with (path / "payloads.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("\nnot json at all\n")

    assert len(diagnose(store, "doc").broken) == 2


def test_repair_makes_the_run_load_again(run_dir):
    store, path = run_dir
    _tear(path / "payloads.jsonl")

    _, moved = repair(store, "doc")
    assert moved == {"payloads.jsonl": 1}
    assert diagnose(store, "doc").healthy
    assert len(store.load_run("doc").run_graph.payloads) == 3


def test_repair_keeps_what_it_removed(run_dir):
    """The line may have held a real record: quarantine, never delete."""
    store, path = run_dir
    _tear(path / "payloads.jsonl")

    repair(store, "doc")
    quarantine = path / "payloads.jsonl.broken"
    assert quarantine.exists()
    assert "pl_x" in quarantine.read_text(encoding="utf-8")


def test_repair_leaves_healthy_files_alone(run_dir):
    store, path = run_dir
    _tear(path / "payloads.jsonl")
    before = (path / "nodes.jsonl").read_text(encoding="utf-8")

    repair(store, "doc")
    assert (path / "nodes.jsonl").read_text(encoding="utf-8") == before
    assert not (path / "nodes.jsonl.broken").exists()


def test_repair_on_a_healthy_run_changes_nothing(run_dir):
    store, path = run_dir
    before = {p.name: p.read_text(encoding="utf-8") for p in path.glob("*.jsonl")}

    _, moved = repair(store, "doc")
    assert moved == {}
    assert {p.name: p.read_text(encoding="utf-8") for p in path.glob("*.jsonl")} == before


def test_a_broken_run_json_is_reported_but_not_repaired(run_dir):
    """Rewriting run.json without its bad line would be deleting the run."""
    store, path = run_dir
    (path / "run.json").write_text("{not json", encoding="utf-8")

    diagnosis = diagnose(store, "doc")
    assert [line.file for line in diagnosis.broken] == ["run.json"]

    _, moved = repair(store, "doc")
    assert moved == {}
    assert (path / "run.json").read_text(encoding="utf-8") == "{not json"
