# Diagrams Extension (`diagram`)

The `diagram` extension allows you to define and render Mermaid or Graphviz graphs inside ARCTX, attaching them to Nodes or Steps as visual workflow documentation.

---

## Features

1. **Format Support**:
   Stores Mermaid or Graphviz source code inside a `DiagramPayload`.
2. **Interactive GUI Rendering**:
   Renders diagrams inline as interactive vector graphs (SVG) within the Web GUI detail panel.
3. **Process Visualization**:
   Allows you to model experiment pipelines, logic trees, or architecture states directly alongside graph nodes.

---

## GUI Usage

1. Select a Node or Step, then click **Attach Payload**.
2. Select **Diagram** from the preset list.
3. Fill in the fields:
   * **Title**: A title for the diagram (e.g. `Experiment Pipeline`).
   * **Format**: Select `mermaid` or `graphviz`.
   * **Source Code**: Paste the diagram specification code.
     * Example (Mermaid):
       ```mermaid
       graph TD
           A[Collect Data] --> B(Preprocess)
           B --> C{Verify}
           C -->|OK| D[Train]
           C -->|NG| E[Re-collect]
       ```
4. Click **attach payload**. The diagram renders directly in the UI.

---

## CLI Usage

You can attach diagrams via `arctx attach` using `--payload-type diagram` and passing fields with `--json`:

```bash
arctx attach n_abc123 \
  --payload-type diagram \
  --json '{
    "title": "Simple Pipeline",
    "format": "mermaid",
    "source": "graph LR; A-->B; B-->C;"
  }'
```

> Note: `--payload-type diagram` produces a proper `DiagramPayload` (the GUI renderer keys on this type). `--type` only sets the generic payload's `type` field, so use `--payload-type` for diagrams.
