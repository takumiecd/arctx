"""Web UI extension for git-backed payloads."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from arctx_web.extensions import WebExtensionBase, WebRequest, WebRoute


class GitWebExtension(WebExtensionBase):
    """Browser-side git helpers for arctx-web."""

    def routes(self) -> list[WebRoute]:
        """Return JSON routes used by the git payload renderer."""
        return [WebRoute(method="POST", path="/web/ext/git/diff", handler=_diff_route)]

    def scripts(self) -> list[str]:
        """Return the browser renderer for git_change payloads."""
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

    payload = git_payloads[-1].to_dict()
    head_commit = str(payload.get("head_commit") or "")
    if not head_commit:
        return 400, {"error": f"git_change payload on {step_id!r} has no head_commit"}

    repo_id = str(payload.get("repo_id") or "")
    repo_path, error = _repo_path_for_git_payload(handle.run_graph, repo_id)
    if error is not None:
        return 404, {"error": error}

    max_bytes = _max_bytes(req.body.get("max_bytes"))
    patch, patch_error = _git_show_patch(repo_path, head_commit, max_bytes=max_bytes)
    if patch_error is not None:
        return 400, {"error": patch_error}

    return 200, {
        "step_id": step_id,
        "repo_id": repo_id,
        "repo_path": str(repo_path),
        "head_commit": head_commit,
        "subject": _git_show_subject(repo_path, head_commit),
        "files": _git_show_files(repo_path, head_commit),
        "diff": patch["text"],
        "truncated": patch["truncated"],
        "byte_count": patch["byte_count"],
    }


def _repo_path_for_git_payload(graph: Any, repo_id: str) -> tuple[Path, str | None]:
    repos = [p.to_dict() for p in graph.payloads.values() if p.payload_type == "repo"]
    selected = None
    if repo_id:
        selected = next((repo for repo in repos if str(repo.get("repo_id") or "") == repo_id), None)
    elif len(repos) == 1:
        selected = repos[0]

    if selected is None:
        return Path(), (
            f"cannot resolve local repo for repo_id {repo_id!r}; "
            "the run may not contain a repo registry entry"
        )

    local_path = selected.get("local_path")
    if not isinstance(local_path, str) or not local_path:
        return Path(), (
            f"repo {repo_id!r} has no local_path; git diff is only available in live local runs"
        )
    path = Path(local_path).expanduser()
    if not path.exists():
        return Path(), f"repo local_path does not exist: {path}"
    return path, None


def _max_bytes(raw: object) -> int:
    if raw is None:
        return 300_000
    try:
        if isinstance(raw, int):
            value = raw
        elif isinstance(raw, str):
            value = int(raw)
        else:
            return 300_000
    except (TypeError, ValueError):
        return 300_000
    return max(8_000, min(value, 1_500_000))


def _git_show_patch(
    repo_path: Path,
    commit: str,
    *,
    max_bytes: int,
) -> tuple[dict[str, Any], str | None]:
    result = subprocess.run(
        [
            "git",
            "show",
            "--format=",
            "--patch",
            "--find-renames",
            "--no-ext-diff",
            commit,
        ],
        cwd=str(repo_path),
        capture_output=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        return {}, stderr or f"git show failed for {commit}"
    raw = result.stdout
    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    return {
        "text": raw.decode("utf-8", errors="replace"),
        "truncated": truncated,
        "byte_count": len(result.stdout),
    }, None


def _git_show_files(repo_path: Path, commit: str) -> list[str]:
    result = subprocess.run(
        ["git", "show", "--format=", "--name-only", "--no-ext-diff", commit],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [line for line in result.stdout.splitlines() if line.strip()]


def _git_show_subject(repo_path: Path, commit: str) -> str:
    result = subprocess.run(
        ["git", "show", "--no-patch", "--format=%s", commit],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


_GIT_DIFF_ELEMENT_SCRIPT = r"""
(function () {
  const tagName = "arctx-git-diff-view";

  class GitDiffView extends HTMLElement {
    set payload(value) {
      this._payload = value;
      this.render();
    }

    set display(value) {
      this._display = value;
      this.render();
    }

    connectedCallback() {
      this.render();
    }

    render() {
      if (!this.isConnected || !this._payload) return;
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      const payload = this._payload;
      this.shadowRoot.innerHTML = `
        <style>
          :host {
            display: block;
            margin-top: 8px;
            font-family: system-ui, -apple-system, sans-serif;
          }
          button {
            padding: 5px 10px;
            border: 1px solid #cbd5e1;
            background: #fff;
            color: #0f172a;
            border-radius: 5px;
            cursor: pointer;
            font-size: 12px;
          }
          button:disabled { opacity: .55; cursor: default; }
          .error { margin: 6px 0 0; color: #dc2626; font-size: 12px; }
          .meta {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 6px;
            margin: 8px 0;
            font-size: 12px;
            color: #475569;
          }
          .meta strong { display: block; color: #0f172a; overflow-wrap: anywhere; }
          details { margin: 8px 0; font-size: 12px; color: #475569; }
          summary { cursor: pointer; }
          ul { padding-left: 18px; margin: 6px 0; }
          pre {
            max-height: 520px;
            overflow: auto;
            white-space: pre;
            background: #0f172a;
            color: #e2e8f0;
            border: 1px solid #334155;
            border-radius: 6px;
            padding: 8px;
            font-size: 11px;
          }
          .muted { color: #94a3b8; font-size: 12px; margin: 6px 0 0; }
        </style>
        <button type="button">load diff</button>
        <div class="body"></div>
      `;
      this.shadowRoot.querySelector("button").addEventListener("click", () => {
        this.loadDiff(payload.target_id);
      });
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
      const files = Array.isArray(data.files) ? data.files : [];
      return `
        <div class="meta">
          <span>
            commit
            <strong>${escapeHtml(String(data.head_commit || "").slice(0, 12))}</strong>
          </span>
          <span>files<strong>${files.length}</strong></span>
          <span>bytes<strong>${escapeHtml(String(data.byte_count || 0))}</strong></span>
        </div>
        ${data.truncated ? `<p class="muted">diff truncated for display</p>` : ""}
        ${files.length ? `
          <details>
            <summary>changed files</summary>
            <ul>${files.map((file) => `<li>${escapeHtml(String(file))}</li>`).join("")}</ul>
          </details>
        ` : ""}
        <pre>${escapeHtml(data.diff || "(empty diff)")}</pre>
      `;
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function install(api) {
    if (!customElements.get(tagName)) customElements.define(tagName, GitDiffView);
    api.registerPayloadElement("git_change", { tagName });
  }

  if (window.arctxWeb) install(window.arctxWeb);
  else {
    window.arctxWebExtensions = window.arctxWebExtensions || [];
    window.arctxWebExtensions.push(install);
  }
})();
"""


__all__ = ["GitWebExtension"]
