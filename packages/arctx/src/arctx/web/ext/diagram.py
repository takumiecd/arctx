"""Web UI extension for diagram payloads."""

from __future__ import annotations

from arctx.web.extensions import WebExtensionBase


class DiagramWebExtension(WebExtensionBase):
    def scripts(self) -> list[str]:
        return [_DIAGRAM_ELEMENT_SCRIPT]


_DIAGRAM_ELEMENT_SCRIPT = r"""
(function () {
  const tagName = "arctx-diagram-preview";
  class DiagramPreview extends HTMLElement {
    set payload(value) { this._payload = value; this.render(); }
    connectedCallback() { this.render(); }
    render() {
      if (!this.isConnected || !this._payload) return;
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      const payload = this._payload;
      const nodes = Array.isArray(payload.nodes) ? payload.nodes : [];
      const edges = Array.isArray(payload.edges) ? payload.edges : [];
      const source = typeof payload.source === "string" ? payload.source : "";
      const nodeHtml = nodes.map((node) => `<span class="node">${escapeHtml(labelForNode(node))}</span>`).join("");
      const edgeHtml = edges.map((edge) => `<span class="edge">${escapeHtml(labelForEdge(edge))}</span>`).join("");
      this.shadowRoot.innerHTML = `
        <style>
          :host { display: block; margin-top: 8px; font-family: system-ui, -apple-system, sans-serif; }
          .summary { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; font-size: 12px; color: #475569; }
          .summary strong { display: block; color: #0f172a; }
          .graph { margin-top: 8px; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; background: #f8fafc; }
          .node { display: inline-block; margin: 3px; padding: 3px 7px; border: 1px solid #94a3b8; border-radius: 5px; background: #fff; font-size: 12px; }
          .edge { display: block; margin: 3px 0; color: #475569; font-size: 12px; }
          pre { margin: 8px 0 0; white-space: pre-wrap; overflow-wrap: anywhere; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; font-size: 11px; color: #0f172a; }
        </style>
        <div class="summary">
          <span>format<strong>${escapeHtml(String(payload.format || "diagram"))}</strong></span>
          <span>nodes<strong>${nodes.length}</strong></span>
          <span>edges<strong>${edges.length}</strong></span>
        </div>
        ${nodes.length || edges.length ? `<div class="graph">${nodeHtml}${edgeHtml}</div>` : ""}
        ${source ? `<pre>${escapeHtml(source)}</pre>` : ""}
      `;
    }
  }
  function labelForNode(node) { if (!node || typeof node !== "object") return ""; return node.label || node.name || node.id || JSON.stringify(node); }
  function labelForEdge(edge) { if (!edge || typeof edge !== "object") return ""; const from = edge.from || edge.source || "?"; const to = edge.to || edge.target || "?"; const label = edge.label ? ` (${edge.label})` : ""; return `${from} -> ${to}${label}`; }
  function escapeHtml(value) { return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;"); }
  function install(api) { if (!customElements.get(tagName)) customElements.define(tagName, DiagramPreview); api.registerPayloadElement("diagram", { tagName }); }
  if (window.arctxWeb) install(window.arctxWeb); else { window.arctxWebExtensions = window.arctxWebExtensions || []; window.arctxWebExtensions.push(install); }
})();
"""
