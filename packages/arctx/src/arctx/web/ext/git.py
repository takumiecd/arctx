"""Web UI extension for git-backed payloads."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from arctx.web.extensions import WebExtensionBase, WebRequest, WebRoute


class GitWebExtension(WebExtensionBase):
    def routes(self) -> list[WebRoute]:
        return [WebRoute(method="POST", path="/web/ext/git/diff", handler=_diff_route)]

    def scripts(self) -> list[str]:
        return [_GIT_DIFF_ELEMENT_SCRIPT]


def _diff_route(req: WebRequest) -> tuple[int, dict[str, Any]]:
    step_id = req.body.get("step_id")
    if not step_id:
        return 400, {"error": "step_id is required"}
    step_id = str(step_id)

    handle = req.store.load_run(req.run_id)
    if step_id not in handle.run_graph.steps:
        return 404, {"error": f"unknown step_id: {step_id}"}

    git_payloads = handle.run_graph.payloads_for_step(step_id, payload_type="git_change")
    if not git_payloads:
        return 404, {"error": f"step {step_id!r} has no git_change payload"}

    payload = git_payloads[-1]
    head_commit = payload.head_commit
    if not head_commit:
        return 400, {"error": f"git_change payload on {step_id!r} has no head_commit"}

    repo_path, error = _repo_path_for_run(req.store, req.run_id)
    if error is not None:
        return 404, {"error": error}

    # Everything below is derived from git at request time — the record holds
    # only hashes and a branch. A commit missing from this clone is a normal
    # outcome (shallow clone, never pushed), reported as an explicit marker
    # rather than an error.
    from arctx.ext.git.derive import derive_git_change, derive_patch

    derived = derive_git_change(payload, repo_path)
    max_bytes = _max_bytes(req.body.get("max_bytes"))
    text, truncated, byte_count, note = derive_patch(
        payload, repo_path, max_bytes=max_bytes
    )

    return 200, {
        "step_id": step_id,
        "repo_path": str(repo_path),
        "head_commit": head_commit,
        "branch": payload.branch,
        "available": derived.available,
        "note": note or derived.note,
        "subject": derived.commit_log[0].subject if derived.commit_log else "",
        "files": list(derived.files),
        "diff_stat": derived.diff_stat.to_dict(),
        "diff": text,
        "truncated": truncated,
        "byte_count": byte_count,
    }


def _repo_path_for_run(store: Any, run_id: str) -> tuple[Path, str | None]:
    """Resolve the repo holding this run.

    There is no repo registry: a run lives inside exactly one repository
    ("absent = self"), so the repo is the one containing the run's store dir,
    falling back to the cwd repo when the store is kept outside a checkout.
    """
    from arctx.paths import find_repo_root

    for start in (Path(store.run_path(run_id)), None):
        try:
            return find_repo_root(start), None
        except RuntimeError:
            continue
    return Path(), "cannot resolve a git repo for this run; git diff is only available in live local runs"


def _max_bytes(raw: object) -> int:
    if raw is None:
        return 300_000
    try:
        value = raw if isinstance(raw, int) else int(raw) if isinstance(raw, str) else 300_000
    except (TypeError, ValueError):
        return 300_000
    return max(8_000, min(value, 1_500_000))



_GIT_DIFF_ELEMENT_SCRIPT = r"""
(function () {
  const tagName = "arctx-git-diff-view";
  class GitDiffView extends HTMLElement {
    set payload(value) { this._payload = value; this.render(); }
    set display(value) { this._display = value; this.render(); }
    connectedCallback() { this.render(); }
    render() {
      if (!this.isConnected || !this._payload) return;
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      const payload = this._payload;
      this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; margin-top: 8px; font-family: system-ui, -apple-system, sans-serif; }
          button { padding: 5px 10px; border: 1px solid #cbd5e1; background: #fff; color: #0f172a; border-radius: 5px; cursor: pointer; font-size: 12px; }
          button:disabled { opacity: .55; cursor: default; }
          .error { margin: 6px 0 0; color: #dc2626; font-size: 12px; }
          .meta { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; margin: 8px 0; font-size: 12px; color: #475569; }
          .meta strong { display: block; color: #0f172a; overflow-wrap: anywhere; }
          details { margin: 8px 0; font-size: 12px; color: #475569; }
          summary { cursor: pointer; }
          ul { padding-left: 18px; margin: 6px 0; }
          pre { max-height: 520px; overflow: auto; white-space: pre; background: #0f172a; color: #e2e8f0; border: 1px solid #334155; border-radius: 6px; padding: 8px; font-size: 11px; }
          .muted { color: #94a3b8; font-size: 12px; margin: 6px 0 0; }
        </style>
        <button type="button">load diff</button>
        <div class="body"></div>
      `;
      this.shadowRoot.querySelector("button").addEventListener("click", () => { this.loadDiff(payload.target_id); });
    }
    async loadDiff(stepId) {
      const button = this.shadowRoot.querySelector("button");
      const body = this.shadowRoot.querySelector(".body");
      button.disabled = true;
      button.textContent = "loading diff...";
      body.innerHTML = "";
      try {
        const response = await fetch("/web/ext/git/diff", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ step_id: stepId })
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
        button.remove();
        body.innerHTML = this.diffHtml(data);
      } catch (error) {
        button.disabled = false;
        button.textContent = "load diff";
        body.innerHTML = `<p class="error">${escapeHtml(error.message || String(error))}</p>`;
      }
    }
    diffHtml(data) {
      const files = Array.isArray(data.files) ? data.files.map((file) => `<li>${escapeHtml(file)}</li>`).join("") : "";
      const truncated = data.truncated ? `<p class="muted">diff truncated at ${Number(data.byte_count || 0).toLocaleString()} bytes</p>` : "";
      // The diff is derived from git, so a commit absent from this clone has
      // nothing to render: say so instead of showing an empty diff.
      if (data.available === false || data.note) {
        return `
          <div class="meta">
            <span>commit<strong>${escapeHtml(data.head_commit || "")}</strong></span>
          </div>
          <p class="muted">${escapeHtml(data.note || "(commit not available locally)")}</p>
        `;
      }
      const stat = data.diff_stat || {};
      return `
        <div class="meta">
          <span>commit<strong>${escapeHtml(data.head_commit || "")}</strong></span>
          <span>subject<strong>${escapeHtml(data.subject || "")}</strong></span>
          <span>changes<strong>+${Number(stat.insertions || 0)} / -${Number(stat.deletions || 0)} in ${Number(stat.files_changed || 0)} files</strong></span>
        </div>
        <details ${files ? "open" : ""}>
          <summary>files</summary>
          <ul>${files || "<li>(none)</li>"}</ul>
        </details>
        ${truncated}
        <pre>${escapeHtml(data.diff || "")}</pre>
      `;
    }
  }
  function escapeHtml(value) { return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;"); }
  function install(api) { if (!customElements.get(tagName)) customElements.define(tagName, GitDiffView); api.registerPayloadElement("git_change", { tagName }); }
  if (window.arctxWeb) install(window.arctxWeb); else { window.arctxWebExtensions = window.arctxWebExtensions || []; window.arctxWebExtensions.push(install); }
})();
"""
