# arctx-web

Web GUI for arctx runs (React + React Flow + Vite). One frontend, two data
modes — the UI only talks to a `RunClient`, so the same components serve both:

- **Live mode (read + write)** — talks to `arctx serve`'s HTTP API. Add nodes
  and steps, attach payloads to a node or step, and cut records from the canvas.
- **Static / share mode (read-only)** — renders a run document embedded in the
  page (`<script id="arctx-run" type="application/json">…</script>`). No backend.

The data contract is exactly `arctx export --format json`
(`arctx.core.run.export.json_document`), mirrored in `src/types.ts`.

## Live mode

In one terminal, serve a run:

```sh
arctx serve --run <RUN_ID>          # default http://127.0.0.1:8787
```

In another, start the frontend (the Vite dev server proxies API routes to
`arctx serve`):

```sh
cd web
npm install
npm run dev                         # http://localhost:5173
```

Point at a non-default backend with `VITE_ARCTX_API` (dev proxy) or the `?api=`
query param (built app), e.g. `?api=http://127.0.0.1:9000`.

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
extension payloads. When served through `arctx-web`, third-party renderer
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
      fields: [
        { label: "score", value: payload.content?.score },
        { label: "unit", value: payload.content?.unit },
      ],
      sections: [{ title: "content", kind: "json", value: payload.content }],
    }));
  });
</script>
```

If the app has already loaded, call `window.arctxWeb.registerPayloadRenderer`
directly.

## Scripts

- `npm run dev` — dev server
- `npm run build` — typecheck + production build to `dist/`
- `npm run typecheck` — types only
