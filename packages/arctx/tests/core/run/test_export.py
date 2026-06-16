"""Tests for run export (markdown / LaTeX / HTML / JSON).

Covers all formats, the cut-exclude opt-in filter, the local-path
opt-in (stripped by default), and the generic repo registry section.
"""

from __future__ import annotations

import json

import arctx as arctx
from arctx.core.run.export import ExportOptions, export
from arctx.core.schema.payloads import StepPayload
from arctx.core.schema.requirements import Requirement
from arctx.ext import attach_extensions
from arctx.ext.git.payloads import RemoteRef, RepoPayload


def _make_handle(run_id: str = "run_exp"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return arctx.init(req, run_id=run_id)


def _step_payload(handle, i):
    # step() clones the payload and rebinds target_id, so a placeholder
    # target_id is fine here.
    return StepPayload(
        payload_id=handle._next_id("pl"),
        target_id="pending",
        type="step",
        content={"i": i},
    )


class TestExportFormats:
    def test_markdown_has_title_and_graph(self):
        h = _make_handle()
        out = export(h, "md", ExportOptions())
        assert "# Run `run_exp`" in out
        assert "## Graph" in out
        assert h.root_node_id in out

    def test_html_is_wellformed_shell(self):
        h = _make_handle()
        out = export(h, "html", ExportOptions())
        assert out.startswith("<!doctype html>")
        assert "<h1>Run" in out
        assert out.rstrip().endswith("</html>")

    def test_latex_has_document_env(self):
        h = _make_handle()
        out = export(h, "tex", ExportOptions())
        assert r"\begin{document}" in out
        assert r"\end{document}" in out

    def test_unknown_format_raises(self):
        h = _make_handle()
        try:
            export(h, "pdf", ExportOptions())
        except ValueError as e:
            assert "unknown export format" in str(e)
        else:  # pragma: no cover
            raise AssertionError("expected ValueError")


class TestCutExclude:
    def test_cut_kept_by_default_excluded_on_demand(self):
        h = _make_handle()
        t = h.add_step([h.root_node_id], _step_payload(h, 0))
        # cut the step
        h.cut(t.step_id, target_kind="step")

        default_out = export(h, "md", ExportOptions())
        assert t.step_id in default_out
        assert "(cut)" in default_out

        excluded = export(h, "md", ExportOptions(exclude_cut=True))
        assert t.step_id not in excluded


class TestRepoSection:
    def _with_repo(self, h, *, local: str = "/Users/me/dev/proj"):
        payload = RepoPayload(
            payload_id=h._next_id("pl"),
            target_id=h.root_node_id,
            repo_id="repo_x",
            slug="me/proj",
            remotes=(RemoteRef(kind="ssh", url="git@github.com:me/proj.git"),),
            canonical="github.com/me/proj",
            local_path=local,
        )
        h.run_graph.attach_payload(payload)

    def test_repo_section_present(self):
        h = _make_handle()
        self._with_repo(h)
        out = export(h, "md", ExportOptions())
        assert "## Repos" in out
        assert "me/proj" in out
        assert "github.com/me/proj" in out

    def test_local_path_stripped_by_default(self):
        h = _make_handle()
        self._with_repo(h, local="/Users/secret/dev/proj")
        out = export(h, "md", ExportOptions())
        assert "/Users/secret/dev/proj" not in out

    def test_local_path_included_on_demand(self):
        h = _make_handle()
        self._with_repo(h, local="/Users/secret/dev/proj")
        out = export(h, "md", ExportOptions(include_local=True))
        assert "/Users/secret/dev/proj" in out

    def test_no_repo_section_without_repos(self):
        h = _make_handle()
        out = export(h, "md", ExportOptions())
        assert "## Repos" not in out


class TestJsonExport:
    def test_shape_and_metadata(self):
        h = _make_handle()
        doc = json.loads(export(h, "json", ExportOptions()))
        assert doc["arctx_export_version"] == 1
        assert doc["run_id"] == "run_exp"
        assert doc["root_node_id"] == h.root_node_id
        for key in ("nodes", "steps", "payloads", "repos"):
            assert isinstance(doc[key], list)
        assert doc["counts"]["nodes"] == len(doc["nodes"])
        # Root node is always present.
        assert any(n["node_id"] == h.root_node_id for n in doc["nodes"])

    def test_step_and_payload_emitted_in_full(self):
        h = _make_handle()
        t = h.add_step([h.root_node_id], _step_payload(h, 42))
        doc = json.loads(export(h, "json", ExportOptions()))

        step = next(s for s in doc["steps"] if s["step_id"] == t.step_id)
        assert step["input_node_ids"] == [h.root_node_id]
        assert step["output_node_id"] == t.output_node_id
        assert step["inactive"] is False

        pl = next(p for p in doc["payloads"] if p["target_id"] == t.step_id)
        assert pl["content"] == {"i": 42}

    def test_inactive_flag_and_exclude_cut(self):
        h = _make_handle()
        t = h.add_step([h.root_node_id], _step_payload(h, 0))
        h.cut(t.step_id, target_kind="step")

        doc = json.loads(export(h, "json", ExportOptions()))
        step = next(s for s in doc["steps"] if s["step_id"] == t.step_id)
        assert step["inactive"] is True

        excluded = json.loads(export(h, "json", ExportOptions(exclude_cut=True)))
        assert all(s["step_id"] != t.step_id for s in excluded["steps"])

    def test_repos_in_dedicated_array_local_stripped(self):
        h = _make_handle()
        payload = RepoPayload(
            payload_id=h._next_id("pl"),
            target_id=h.root_node_id,
            repo_id="repo_x",
            slug="me/proj",
            remotes=(RemoteRef(kind="ssh", url="git@github.com:me/proj.git"),),
            canonical="github.com/me/proj",
            local_path="/Users/secret/dev/proj",
        )
        h.run_graph.attach_payload(payload)

        doc = json.loads(export(h, "json", ExportOptions()))
        assert len(doc["repos"]) == 1
        assert doc["repos"][0]["repo_id"] == "repo_x"
        assert "local_path" not in doc["repos"][0]
        # Repo payloads are not duplicated into the generic payloads list.
        assert all(p.get("payload_type") != "repo" for p in doc["payloads"])

        with_local = json.loads(export(h, "json", ExportOptions(include_local=True)))
        assert with_local["repos"][0]["local_path"] == "/Users/secret/dev/proj"
