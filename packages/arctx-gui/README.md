# arctx-gui

Web GUI surface for ARCTX. A thin Python package that serves the built React
frontend (`gui/`) together with the run HTTP API, then opens a browser — the
batteries-included counterpart to the raw `arctx serve` data API.

```sh
pip install arctx-gui
arctx-gui --run <RUN_ID>        # serves http://127.0.0.1:8788 and opens a browser
```

It depends on `arctx-cli` and reuses its `arctx serve` dispatcher, so the HTTP
API contract has a single source of truth. This package only adds static-asset
serving and browser launching.

## Frontend assets

The React app lives in the repo's `gui/` directory. Its build output is copied
into `arctx_gui/static/` at packaging time and shipped in the wheel. From a
source checkout you can either bundle it or rely on the `gui/dist` fallback:

```sh
python -m arctx_gui.bundle                 # npm build + copy into the package
# or
npm --prefix gui run build                 # arctx-gui falls back to gui/dist
# or
ARCTX_GUI_STATIC=/path/to/dist arctx-gui   # point at any prebuilt dist
```

## Options

- `--run` / `--store-dir` / `--user` / `--work-session` — same resolution as the CLI
- `--host` (default `127.0.0.1`) / `--port` (default `8788`)
- `--no-browser` — don't open a browser
- `--cors-origin` — `Access-Control-Allow-Origin` value (default `*`)

## Relationship to other surfaces

- `arctx serve` (in **arctx-cli**) — the dependency-free JSON API primitive that
  every GUI frontend shares.
- `arctx-gui` (this package) — bundles a frontend and serves it alongside that API.
