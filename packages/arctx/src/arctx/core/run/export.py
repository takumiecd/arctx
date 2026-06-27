"""Export a run as a human-facing document: markdown, LaTeX, or HTML.

``dump`` renders the run for inspection / LLM consumption; ``export`` produces
a standalone artifact to hand to people. It reuses the same spanning-tree walk
as ``dump`` but emits a document with a title, an optional repo registry
section, and a nested outline of the run.

Two filters, both opt-in and with opposite defaults by intent:

- ``exclude_cut`` (default False): drop cut (inactive) nodes/steps. Cut
  is just history noise, so it is kept unless asked to be removed.
- ``include_local`` (default False): include each repo's ``local_path`` in the
  registry section. local paths are environment-specific (and can leak a
  username), so they are stripped by default — this is the single outlet that
  keeps shared/exported artifacts free of machine-local data.

This module stays repo-agnostic: it never imports the git extension. Repo
registry entries and per-step repo ids are read generically through
``payload_type`` and ``to_dict()`` so a run with no git payloads exports fine.
"""

from __future__ import annotations

from dataclasses import dataclass

from arctx.core.cuts import inactive_node_ids, inactive_step_ids
from arctx.core.lanes import lane_export_view
from arctx.core.run.handle import RunHandle
from arctx.core.run_graph import RunGraph
from arctx.core.schema.payloads import CutPayload, NodePayload, StepPayload


@dataclass
class ExportOptions:
    node_id: str | None = None
    depth: int | None = None
    full_payloads: bool = False
    exclude_cut: bool = False
    include_local: bool = False


@dataclass
class _Row:
    depth: int
    kind: str  # "node" | "step" | "ref"
    ident: str
    label: str
    cut: bool


# ---------------------------------------------------------------------------
# Summaries (mirror dump.py so outputs stay consistent)
# ---------------------------------------------------------------------------


def _truncate(s: str | None, n: int) -> str:
    if not s:
        return ""
    return s if len(s) <= n else s[: n - 1] + "…"


def _content_str(content: dict, full: bool) -> str:
    """Render a payload's content. ``text`` wins; otherwise a JSON blob.

    The point of an export is to carry the *why*, so this never drops content
    silently: ``text`` is shown verbatim, and any other content is serialized.
    ``full`` only controls how aggressively the JSON is truncated.
    """
    import json

    text = content.get("text")
    if isinstance(text, str) and text:
        return text
    blob = json.dumps(content, ensure_ascii=False)
    return blob if full else _truncate(blob, 80)


def _cut_reason(payload: CutPayload) -> str:
    reason = getattr(payload, "reason", None)
    return f"cut: {reason}" if reason else "cut"


def _node_summary(graph: RunGraph, node_id: str, full: bool = False) -> str | None:
    parts: list[str] = []
    for payload in graph.payloads_for_node(node_id):
        # Repo registry entries get their own section; don't echo them on nodes.
        if payload.payload_type == "repo":
            continue
        if isinstance(payload, CutPayload):
            parts.append(_cut_reason(payload))
        elif isinstance(payload, NodePayload):
            if payload.content:
                rendered = _content_str(payload.content, full)
                # Prefix with the type unless the content already is the text.
                if rendered == payload.content.get("text"):
                    parts.append(rendered)
                else:
                    parts.append(f"{payload.type} {rendered}")
            else:
                parts.append(payload.type)
        else:
            parts.append(payload.payload_type)
    return " · ".join(parts) if parts else None


def _step_summary(graph: RunGraph, step_id: str, full: bool) -> str:
    parts: list[str] = []
    for payload in graph.payloads_for_step(step_id):
        if isinstance(payload, CutPayload):
            parts.append(_cut_reason(payload))
        elif isinstance(payload, StepPayload):
            parts.append(payload.type)
            if full and payload.content:
                parts.append(_content_str(payload.content, full))
        else:
            parts.append(payload.payload_type)
    return " ".join(parts) if parts else "step"


# ---------------------------------------------------------------------------
# Repo registry (read generically; no git import)
# ---------------------------------------------------------------------------


def _repo_entries(graph: RunGraph) -> list[dict]:
    """Return RepoPayload entries as plain dicts, sorted by slug/repo_id."""
    entries = [
        p.to_dict()
        for p in graph.payloads.values()
        if p.payload_type == "repo"
    ]
    entries.sort(key=lambda e: str(e.get("slug") or e.get("repo_id") or ""))
    return entries


# ---------------------------------------------------------------------------
# Spanning-tree walk -> rows
# ---------------------------------------------------------------------------


def _walk(handle: RunHandle, opts: ExportOptions) -> list[_Row]:
    graph = handle.run_graph
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_step_ids(graph)
    root_id = opts.node_id or handle.root_node_id

    rows: list[_Row] = []
    visited_nodes: set[str] = set()
    visited_steps: set[str] = set()

    def emit_node(node_id: str, depth: int) -> None:
        cut = node_id in inactive_nodes
        if opts.exclude_cut and cut:
            return
        if node_id in visited_nodes:
            rows.append(_Row(depth, "ref", node_id, f"↻ {node_id}", cut))
            return
        visited_nodes.add(node_id)
        note = _node_summary(graph, node_id, opts.full_payloads)
        shown = note if opts.full_payloads else _truncate(note, 80) if note else note
        label = node_id if not note else f"{node_id} — {shown}"
        rows.append(_Row(depth, "node", node_id, label, cut))
        if opts.depth is not None and depth >= opts.depth:
            return
        for step_id in graph.steps_from_node(node_id):
            t = graph.steps[step_id]
            if t.input_node_ids and t.input_node_ids[0] != node_id:
                # Non-primary parent of a multi-input step.
                if not (opts.exclude_cut and step_id in inactive_trans):
                    rows.append(
                        _Row(
                            depth + 1,
                            "ref",
                            step_id,
                            f"▸ feeds {step_id}",
                            step_id in inactive_trans,
                        )
                    )
                continue
            emit_step(step_id, depth + 1)

    def emit_step(step_id: str, depth: int) -> None:
        cut = step_id in inactive_trans
        if opts.exclude_cut and cut:
            return
        t = graph.steps[step_id]
        summary = _step_summary(graph, step_id, opts.full_payloads)
        extras = ""
        if len(t.input_node_ids) > 1:
            extras = " " + " ".join(f"(+{n})" for n in t.input_node_ids[1:])
        if step_id in visited_steps:
            rows.append(_Row(depth, "ref", step_id, f"↻ {step_id}", cut))
            return
        visited_steps.add(step_id)
        label = f"→ {step_id}{extras}  {summary}"
        rows.append(_Row(depth, "step", step_id, label, cut))
        if t.output_node_id:
            emit_node(t.output_node_id, depth + 1)

    emit_node(root_id, 0)
    return rows


# ---------------------------------------------------------------------------
# Format renderers
# ---------------------------------------------------------------------------


def _cut_tag(fmt: str, row: _Row) -> str:
    if not row.cut:
        return ""
    return {"md": " *(cut)*", "tex": r" \emph{(cut)}", "html": ' <em>(cut)</em>'}[fmt]


def _esc_html(s: str) -> str:
    return (
        s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    )


def _esc_tex(s: str) -> str:
    for a, b in (("\\", r"\textbackslash{}"), ("&", r"\&"), ("%", r"\%"),
                 ("$", r"\$"), ("#", r"\#"), ("_", r"\_"), ("{", r"\{"),
                 ("}", r"\}"), ("~", r"\textasciitilde{}"), ("^", r"\textasciicircum{}")):
        s = s.replace(a, b)
    return s


def _render_repos_md(entries: list[dict], include_local: bool) -> list[str]:
    if not entries:
        return []
    out = ["## Repos", ""]
    for e in entries:
        slug = e.get("slug") or e.get("repo_id")
        out.append(f"- **{slug}** (`{e.get('repo_id')}`)")
        if e.get("canonical"):
            out.append(f"  - canonical: `{e['canonical']}`")
        for r in e.get("remotes") or []:
            out.append(f"  - remote ({r.get('kind')}): `{r.get('url')}`")
        if include_local and e.get("local_path"):
            out.append(f"  - local: `{e['local_path']}`")
    out.append("")
    return out


def render_markdown(handle: RunHandle, opts: ExportOptions) -> str:
    graph = handle.run_graph
    lines = [
        f"# Run `{handle.run_id}`",
        "",
        f"- nodes: {len(graph.nodes)}",
        f"- steps: {len(graph.steps)}",
        "",
    ]
    lines += _render_repos_md(_repo_entries(graph), opts.include_local)
    lines += ["## Graph", ""]
    for row in _walk(handle, opts):
        indent = "  " * row.depth
        lines.append(f"{indent}- {row.label}{_cut_tag('md', row)}")
    return "\n".join(lines) + "\n"


def render_html(handle: RunHandle, opts: ExportOptions) -> str:
    graph = handle.run_graph
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        f"<title>Run {_esc_html(handle.run_id)}</title>",
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;}"
        ".cut{color:#999;}li{margin:.1rem 0;}code{background:#f3f3f3;padding:0 .2em;}"
        "</style></head><body>",
        f"<h1>Run <code>{_esc_html(handle.run_id)}</code></h1>",
        f"<p>nodes: {len(graph.nodes)} &middot; steps: {len(graph.steps)}</p>",
    ]
    entries = _repo_entries(graph)
    if entries:
        parts.append("<h2>Repos</h2><ul>")
        for e in entries:
            slug = _esc_html(str(e.get("slug") or e.get("repo_id")))
            parts.append(f"<li><strong>{slug}</strong> <code>{_esc_html(str(e.get('repo_id')))}</code><ul>")
            if e.get("canonical"):
                parts.append(f"<li>canonical: <code>{_esc_html(str(e['canonical']))}</code></li>")
            for r in e.get("remotes") or []:
                parts.append(
                    f"<li>remote ({_esc_html(str(r.get('kind')))}): "
                    f"<code>{_esc_html(str(r.get('url')))}</code></li>"
                )
            if opts.include_local and e.get("local_path"):
                parts.append(f"<li>local: <code>{_esc_html(str(e['local_path']))}</code></li>")
            parts.append("</ul></li>")
        parts.append("</ul>")
    parts.append("<h2>Graph</h2>")
    prev_depth = -1
    for row in _walk(handle, opts):
        while prev_depth < row.depth:
            parts.append("<ul>")
            prev_depth += 1
        while prev_depth > row.depth:
            parts.append("</ul>")
            prev_depth -= 1
        cls = ' class="cut"' if row.cut else ""
        parts.append(f"<li{cls}>{_esc_html(row.label)}</li>")
    while prev_depth >= 0:
        parts.append("</ul>")
        prev_depth -= 1
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def render_latex(handle: RunHandle, opts: ExportOptions) -> str:
    graph = handle.run_graph
    lines = [
        r"\documentclass{article}",
        r"\usepackage[T1]{fontenc}",
        r"\begin{document}",
        rf"\section*{{Run \texttt{{{_esc_tex(handle.run_id)}}}}}",
        rf"nodes: {len(graph.nodes)}, steps: {len(graph.steps)}",
        "",
    ]
    entries = _repo_entries(graph)
    if entries:
        lines.append(r"\subsection*{Repos}")
        lines.append(r"\begin{itemize}")
        for e in entries:
            slug = _esc_tex(str(e.get("slug") or e.get("repo_id")))
            lines.append(rf"\item \textbf{{{slug}}} (\texttt{{{_esc_tex(str(e.get('repo_id')))}}})")
            sub = []
            if e.get("canonical"):
                sub.append(rf"\item canonical: \texttt{{{_esc_tex(str(e['canonical']))}}}")
            for r in e.get("remotes") or []:
                sub.append(
                    rf"\item remote ({_esc_tex(str(r.get('kind')))}): "
                    rf"\texttt{{{_esc_tex(str(r.get('url')))}}}"
                )
            if opts.include_local and e.get("local_path"):
                sub.append(rf"\item local: \texttt{{{_esc_tex(str(e['local_path']))}}}")
            if sub:
                lines.append(r"\begin{itemize}")
                lines += sub
                lines.append(r"\end{itemize}")
        lines.append(r"\end{itemize}")
    lines.append(r"\subsection*{Graph}")
    # Flat list with manual indentation keeps nesting depth unbounded-safe.
    lines.append(r"\begin{itemize}")
    for row in _walk(handle, opts):
        indent = r"\hspace*{" + str(row.depth) + r"em}" if row.depth else ""
        lines.append(rf"\item {indent}{_esc_tex(row.label)}{_cut_tag('tex', row)}")
    lines.append(r"\end{itemize}")
    lines.append(r"\end{document}")
    return "\n".join(lines) + "\n"


def json_document(handle: RunHandle, opts: ExportOptions) -> dict:
    """Build the machine-readable run document as a plain dict.

    Unlike the md/tex/html renderers (which emit a human-facing spanning-tree
    outline), this is the *data contract* for GUI surfaces: every node, step,
    and payload is emitted in full so a frontend can draw the DAG itself. It is
    the shared source of truth for both ``export --format json`` and the
    ``arctx serve`` HTTP API (``GET /run``).

    Cut propagation is precomputed here via core's ``inactive_*`` helpers and
    exposed as an ``inactive`` flag on each node/step, so frontends never have
    to reimplement cut semantics. ``--exclude-cut`` drops inactive records (and
    any payloads targeting them). ``--node``/``--depth`` restrict the export to
    the spanning subtree, reusing the same walk as the other formats.

    This module stays repo-agnostic: repo entries are read generically and,
    unless ``include_local`` is set, their environment-specific ``local_path``
    is stripped (mirroring ``RepoPayload.shareable()``).
    """
    graph = handle.run_graph
    inactive_nodes = inactive_node_ids(graph)
    inactive_trans = inactive_step_ids(graph)

    # Determine the set of records to include.
    if opts.node_id is None and opts.depth is None:
        node_ids = set(graph.nodes)
        step_ids = set(graph.steps)
    else:
        node_ids = set()
        step_ids = set()
        for row in _walk(handle, opts):
            if row.kind == "node":
                node_ids.add(row.ident)
            elif row.kind == "step":
                step_ids.add(row.ident)

    if opts.exclude_cut:
        node_ids -= inactive_nodes
        step_ids -= inactive_trans

    nodes_out = []
    for nid in node_ids:
        d = graph.nodes[nid].to_dict()
        d["inactive"] = nid in inactive_nodes
        nodes_out.append(d)
    nodes_out.sort(key=lambda d: str(d["node_id"]))

    steps_out = []
    for sid in step_ids:
        d = graph.steps[sid].to_dict()
        d["inactive"] = sid in inactive_trans
        steps_out.append(d)
    steps_out.sort(key=lambda d: str(d["step_id"]))

    payloads_out = []
    payload_ids = set()
    for p in graph.payloads.values():
        # Repo registry entries are surfaced in ``repos``; don't duplicate them.
        if p.payload_type == "repo":
            continue
        if p.target_kind == "node" and p.target_id not in node_ids:
            continue
        if p.target_kind == "step" and p.target_id not in step_ids:
            continue
        payload_ids.add(p.payload_id)
        payloads_out.append(p.to_dict())
    payloads_out.sort(key=lambda d: str(d.get("payload_id")))

    repos_out = []
    for e in _repo_entries(graph):
        if not opts.include_local:
            e = {k: v for k, v in e.items() if k != "local_path"}
        repos_out.append(e)

    lanes = lane_export_view(
        graph,
        node_ids=node_ids,
        step_ids=step_ids,
        payload_ids=payload_ids,
        root_node_id=handle.root_node_id,
    )

    return {
        "arctx_export_version": 1,
        "run_id": handle.run_id,
        "root_node_id": handle.root_node_id,
        "counts": {
            "nodes": len(nodes_out),
            "steps": len(steps_out),
            "payloads": len(payloads_out),
        },
        "nodes": nodes_out,
        "steps": steps_out,
        "payloads": payloads_out,
        "repos": repos_out,
        "lanes": lanes["lanes"],
        "work_events": lanes["work_events"],
        "record_provenance": lanes["record_provenance"],
        "created_provenance": lanes["created_provenance"],
        "groups": lanes["groups"],
        "lane_boundaries": lanes["lane_boundaries"],
        "lane_edge_summaries": lanes["lane_edge_summaries"],
    }


def render_json(handle: RunHandle, opts: ExportOptions) -> str:
    """Serialize :func:`json_document` to an indented JSON string."""
    import json

    return json.dumps(json_document(handle, opts), ensure_ascii=False, indent=2) + "\n"


def export(handle: RunHandle, fmt: str, opts: ExportOptions) -> str:
    if fmt in ("md", "markdown"):
        return render_markdown(handle, opts)
    if fmt == "html":
        return render_html(handle, opts)
    if fmt in ("tex", "latex"):
        return render_latex(handle, opts)
    if fmt == "json":
        return render_json(handle, opts)
    raise ValueError(f"unknown export format: {fmt!r}")
