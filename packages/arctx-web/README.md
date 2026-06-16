# arctx-web

Web GUI surface for ARCTX. A thin Python package that serves the built React
frontend (`web/`) together with the run HTTP API, then opens a browser — the
batteries-included counterpart to the raw `arctx serve` data API.

```sh
pip install arctx-web
arctx-web --run <RUN_ID>        # serves http://127.0.0.1:8788 and opens a browser
```

It depends on `arctx-cli` and reuses its `arctx serve` dispatcher, so the HTTP
API contract has a single source of truth. This package only adds static-asset
serving and browser launching.

## Frontend assets

The React app lives in the repo's `web/` directory. Its build output is copied
into `arctx_web/static/` at packaging time and shipped in the wheel. From a
source checkout you can either bundle it or rely on the `web/dist` fallback:

```sh
python -m arctx_web.bundle                 # npm build + copy into the package
# or
npm --prefix web run build                 # arctx-web falls back to web/dist
# or
ARCTX_WEB_STATIC=/path/to/dist arctx-web   # point at any prebuilt dist
```

## Options

- `--run` / `--store-dir` / `--user` / `--work-session` — same resolution as the CLI
- `--host` (default `127.0.0.1`) / `--port` (default `8788`)
- `--no-browser` — don't open a browser
- `--cors-origin` — `Access-Control-Allow-Origin` value (default `*`)

## Saved graph layout

Graph node positions are web view state, so `arctx-web` stores them outside the
core append-only run graph in `<run_dir>/web_layouts.json`. The browser reads
and writes the default layout through:

```http
GET /web/layout
PUT /web/layout
```

If that endpoint is unavailable, such as when developing against plain
`arctx serve`, the frontend falls back to automatic layout and skips
persistence.

## Web extensions

`arctx-web` owns browser-side extension behavior. The core run JSON still
contains raw payload records; the frontend decides how to display those
payloads. Built-in renderers handle core, `git`, and `command` payloads.

Third-party extensions can ship web renderers through the
`arctx_web.extensions` entry point group. The entry point name must match the
ARCTX extension name stored in the run's `extensions.json`; `arctx-web` loads
only renderers for extensions enabled on the current run and injects their
scripts into `index.html`.

```toml
[project.entry-points."arctx_web.extensions"]
myext = "my_arctx_ext.web:MyExtWeb"
```

```python
class MyExtWeb:
    def scripts(self) -> list[str]:
        return [
            """
            window.arctxWebExtensions = window.arctxWebExtensions || [];
            window.arctxWebExtensions.push((api) => {
              api.registerPayloadRenderer("myext_experiment", (payload) => ({
                title: "experiment",
                summary: payload.name,
                graphLabel: payload.name,
                media: [{ kind: "image", src: payload.plot, alt: "experiment plot" }],
                fields: [{ label: "score", value: payload.score }],
                sections: [
                  { title: "raw", kind: "json", value: payload, collapsed: true },
                ],
              }));
            });
            """
        ]
```

Renderer images may use `data:image/png|jpeg|webp` or run artifacts such as
`artifact://plots/loss.png`. `arctx-web` serves those from
`<run_dir>/artifacts/plots/loss.png` through `/artifacts/plots/loss.png`.
Sections support `json`, `list`, `text`, `table`, `markdown`, `diff`, and
`image`; markdown is rendered as safe text.

Trusted local extensions can also register a custom element for a richer body
renderer:

```javascript
customElements.define("myext-report", class extends HTMLElement {
  set payload(value) {
    this.textContent = `score: ${value.score}`;
  }
});

window.arctxWebExtensions.push((api) => {
  api.registerPayloadElement("myext_report", {
    tagName: "myext-report",
    fallbackRenderer: (payload) => ({ title: "report", summary: String(payload.score) }),
  });
});
```

## Relationship to other surfaces

- `arctx serve` (in **arctx-cli**) — the dependency-free JSON API primitive that
  every GUI frontend shares.
- `arctx-web` (this package) — bundles a frontend and serves it alongside that API.
