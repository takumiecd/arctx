# arctx web

Web GUI for ARCTX experiment graphs (React + React Flow + Vite). It visualizes
hypotheses, trials, results, lanes, and cut branches from an arctx run.

One frontend, two data modes — the UI only talks to a `RunClient`, so the same
components serve both:

- **Live mode (read + write)** — talks to `arctx serve`'s HTTP API. Add nodes
  and steps, create lanes, attach payloads to a node or step, and cut records
  from the canvas. Asset content and git diffs are resolved from the repository
  by the server on demand, so they are only available here.
- **Static / share mode (read-only)** — renders a run document embedded in the
  page (`<script id="arctx-run" type="application/json">…</script>`). No backend,
  so assets show their `(commit, path)` reference rather than their content.

The data contract is exactly `arctx export --format json`
(`arctx.core.run.export.json_document`), mirrored in `src/types.ts`.

![arctx web GUI demo](../examples/demo_web.gif)

*Click nodes to inspect git changes, benchmark payloads, and cut reasons. Toggle "show cuts" to reveal abandoned branches.*

## Live mode

In one terminal, start the bundled GUI:

```sh
arctx web --run <RUN_ID>            # default http://127.0.0.1:8788
```

For frontend development, run the Vite dev server separately and proxy API
routes to `arctx serve`:

```sh
cd web
npm install
npm run dev                         # http://localhost:5173
```

Point at a non-default backend with `VITE_ARCTX_API` (dev proxy) or the `?api=`
query param (built app), e.g. `?api=http://127.0.0.1:9000`.

When served by `arctx web`, manual node positions are persisted in
`<run_dir>/web_layouts.json` through `/web/layout`. Plain `arctx serve` does not
provide that endpoint, so the frontend simply uses automatic layout there.

The detail panel on the right can be resized by dragging its left edge. The
chosen width is saved in the browser for the next visit.
Live mode also shows the current lane from `arctx serve` in the header.

## Lanes and search

Lanes are flat, git-branch-like work units — there is no lane hierarchy. The
left sidebar is the GUI form of `arctx explore`: open lanes first with their
one-line current summary (the latest `arctx lane summarize` / `lane close`
summary), closed lanes folded behind a toggle. Selecting a lane makes it
current, pans the canvas to it, and shows its purpose, status, and full current
summary in the detail panel.

The search box is `explore --query`: whitespace-separated terms matched
case-insensitively with AND semantics across lane names, lane purposes, and the
payloads each lane owns. It runs entirely against the loaded run document — no
server round-trip — and each hit links to the records it matched.

## Assets and git changes

An asset is a reference to a git object, `(commit, path)`, not a copied file.
Attach one with `arctx asset attach <TARGET_ID> <PATH>` after committing the
file. In live mode the panel resolves it through `GET /asset`,
`/asset/entries`, and `/asset/content`: images render inline, text files show a
preview, and a directory asset can be browsed one level at a time. A commit
missing from the local clone reports that status instead of failing.

`git_change` records carry only the branch and commit hashes; the subject, file
list, diff stat, and patch are derived from the repository at view time through
`POST /web/ext/git/diff` (mounted by `arctx web`). Commits absent from this
clone show `(commit not available locally)`.

## Markdown notes

Generic node/step payloads render `content.markdown`, `content.md`, or
Markdown-looking `content.text` as Markdown. This is useful for notes, math
discussion, and LLM-authored explanations:

```sh
arctx attach <NODE_OR_STEP_ID> --type note --field 'markdown=# Derivation

We want to compare $f(x)$ and $g(x)$.

$$
f(x) = x^2 + 1
$$

- record the assumption
- keep the failed branch visible'
```

Markdown is rendered with GitHub-flavored Markdown support, including tables,
task lists, fenced code blocks, and `$...$` / `$$...$$` math rendered through
KaTeX. Raw HTML in Markdown is not enabled.

## Static / share mode

Build the app, then drop a run document into the page as
`<script id="arctx-run" type="application/json">…</script>`. The app detects it
and renders read-only — suitable for sharing a single self-contained HTML file.

```sh
npm run build                       # -> dist/
```

## Payload display extensions

Payload rendering is owned by the web app. The run JSON keeps raw payloads; the
frontend chooses how to display them by `payload_type`, or by
`payload_type:type` for generic `node_payload` / `step_payload` records.
Unknown payloads fall back to raw JSON.

Built-in renderers cover core payloads plus the standard `git` and `command`
extension payloads. When served through `arctx web`, third-party renderer
scripts are loaded from the `arctx_web.extensions` entry point group for
extensions enabled on the run. Extra renderers can also be registered from any
script loaded by the page:

```html
<script>
  window.arctxWebExtensions = window.arctxWebExtensions || [];
  window.arctxWebExtensions.push((api) => {
    api.registerPayloadRenderer("step_payload:benchmark", (payload) => ({
      title: "benchmark",
      summary: payload.content?.name,
      graphLabel: payload.content?.name,
      media: [
        {
          kind: "image",
          src: payload.content?.plot,
          alt: "benchmark plot",
          caption: "latest run",
        },
      ],
      fields: [
        { label: "score", value: payload.content?.score },
        { label: "unit", value: payload.content?.unit },
      ],
      sections: [
        { title: "content", kind: "json", value: payload.content, collapsed: true },
        { title: "samples", kind: "table", value: payload.content?.samples },
      ],
    }));
  });
</script>
```

If the app has already loaded, call `window.arctxWeb.registerPayloadRenderer`
directly.

Inline image sources are restricted to `data:` image URIs. Repository files are
assets: commit them and use `arctx asset attach`, which renders through the
asset viewer above. Sections support `json`, `list`, `text`, `table`, `markdown`,
`diff`, and `image`; markdown is rendered as safe text, not raw HTML.

For trusted local extensions that need richer UI, register a custom element.
The web app still owns the card shell and raw JSON fallback; the custom element
only renders the payload-specific body.

```html
<script>
  customElements.define("myext-report", class extends HTMLElement {
    set payload(value) {
      this.textContent = `score: ${value.score}`;
    }
  });

  window.arctxWebExtensions = window.arctxWebExtensions || [];
  window.arctxWebExtensions.push((api) => {
    api.registerPayloadElement("myext_report", {
      tagName: "myext-report",
      fallbackRenderer: (payload) => ({
        title: "report",
        summary: String(payload.score),
      }),
    });
  });
</script>
```

## Scripts

- `npm run dev` — dev server
- `npm run build` — typecheck + production build to `dist/`
- `npm run typecheck` — types only
