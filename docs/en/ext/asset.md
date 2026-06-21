# Attachments / Media (`asset`) — core payload

`asset` lets you manage and attach external files—images, videos, PDFs, text documents—to Nodes and Steps in the ARCTX graph. It is a **core standard payload** (`AssetPayload`), not an extension: it is always available (no `--extension` needed) and lives in core because its visibility rules (which records may reference an asset by URL) depend on core lineage.

---

## Key Features & Design Principles

1. **Portable Artifact Storage**:
   Attached files are copied directly into the run's `artifacts/` subdirectory (e.g. `runs/<run_id>/artifacts/`). This ensures that copying or sharing the run directory preserves all media assets.
2. **Decoupled Architecture**:
   The API and Web GUI are decoupled from the specific `asset` extension namespace. Media assets are uploaded through the core `/artifacts/upload` API and referenced as portable relative paths (`/artifacts/art_...`) in Markdown.
3. **Inline Markdown Rendering**:
   Images and video attachments automatically render as inline previews in the Web GUI's Markdown views.

---

## GUI Usage (Browser)

The easiest way to attach files is directly from input forms (such as **Note (Markdown)** or Custom JSON fields):

1. Select a Node or Step and open the **Attach Payload** form.
2. Under the **Note (Markdown)** preset, click the **"📎 Attach File"** button below the textarea.
3. Select your file.
4. Once uploaded, a Markdown link is automatically inserted at your cursor:
   * Images: `![filename.png](/artifacts/art_<uuid>_filename.png)`
   * Other files: `[filename.pdf](/artifacts/art_<uuid>_filename.pdf)`
5. Click **attach payload**. The markdown renderer will render the image preview inline.

---

## CLI Usage

Use `arctx asset` to copy and attach files to Nodes/Steps via CLI.

### 1. Attach a File (`arctx asset attach`)
Copies the specified file to the run's `artifacts/` folder and creates an `AssetPayload`:

```bash
# Attach an image to a node
arctx asset attach path/to/chart.png --target n_abc123

# Steps work too
arctx asset attach path/to/report.pdf --target t_xyz789
```

### 2. List Attached Assets
Lists all `AssetPayload` entries attached to a Node or Step:

```bash
arctx asset list --target n_abc123
```

### 3. Show Asset Details
Displays metadata (size, mime type, local path) for a specific asset payload:

```bash
arctx asset show pl_xyz456
```

---

## Python API

Programmatically attach files using the core verb `handle.attach_asset(...)`:

```python
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

# Attach a chart to a node
payload = handle.attach_asset(
    "n_abc123",
    "path/to/chart.png",
)

# Retrieve the relative path
print(payload.path) # e.g. artifacts/ast_xxx_chart.png
```

### Visibility (where an asset can be referenced)

An asset is referenceable from the node/step it is attached to **and that record's descendants** (records reachable forward). Equivalently, a record may reference only assets attached to **itself or its ancestors** — never a sibling's or descendant's assets. The set visible from a record is served by `GET /assets/visible?from=<id>`, with the rule computed in `arctx.core.lineage`.
