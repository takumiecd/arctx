"""Tests for run export (markdown / LaTeX / HTML).

Covers all three formats, the cut-exclude opt-in filter, the local-path
opt-in (stripped by default), and the generic repo registry section.
"""

from __future__ import annotations

import arctx as arctx
from arctx.core.run.export import ExportOptions, export
from arctx.core.schema.payloads import TransitionPayload
from arctx.core.schema.requirements import Requirement
from arctx.ext import attach_extensions
from arctx.ext.git.payloads import RemoteRef, RepoPayload


def _make_handle(run_id: str = "run_exp"):
    req = Requirement(requirement_id="req1", target_type="task", target_id="t1")
    return arctx.init(req, run_id=run_id)


def _step_payload(handle, i):
    # transition() clones the payload and rebinds target_id, so a placeholder
    # target_id is fine here.
    return TransitionPayload(
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
        t = h.transition([h.root_node_id], _step_payload(h, 0))
        # cut the transition
        h.cut(t.transition_id, target_kind="transition")

        default_out = export(h, "md", ExportOptions())
        assert t.transition_id in default_out
        assert "(cut)" in default_out

        excluded = export(h, "md", ExportOptions(exclude_cut=True))
        assert t.transition_id not in excluded


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
