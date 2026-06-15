# arctx-gui

Web GUI for arctx runs (React + React Flow + Vite). One frontend, two data
modes — the UI only talks to a `RunClient`, so the same components serve both:

- **Live mode (read + write)** — talks to `arctx serve`'s HTTP API. Add steps,
  attach notes, and cut records from the canvas.
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
cd gui
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

## Scripts

- `npm run dev` — dev server
- `npm run build` — typecheck + production build to `dist/`
- `npm run typecheck` — types only
