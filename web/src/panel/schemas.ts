// Dynamic field schemas for the "attach payload" preset picker in the Edit
// tab. Each preset (other than "custom") renders its fields from here.

import type { RunDocument } from "../types";

export interface FieldDef {
  key: string;
  label: string;
  type: "text" | "number" | "textarea" | "select";
  placeholder?: string;
  defaultValue?: any;
  options?: (doc: RunDocument) => { value: string; label: string }[];
}

export interface PayloadSchema {
  type: string;
  label: string;
  fields: FieldDef[];
}

export const PAYLOAD_SCHEMAS: Record<string, PayloadSchema> = {
  note: {
    type: "note",
    label: "Note (Markdown)",
    fields: [
      { key: "text", label: "Note Text", type: "textarea", placeholder: "Markdown supported text..." }
    ]
  },
  git_change: {
    type: "git_change",
    label: "Git Change (Git Integration)",
    fields: [
      { key: "branch", label: "Branch", type: "text", defaultValue: "main" },
      { key: "head_commit", label: "Commit SHA", type: "text", placeholder: "Head commit hash..." }
    ]
  },
  diagram: {
    type: "diagram",
    label: "Diagram (Mermaid / Graphviz)",
    fields: [
      { key: "title", label: "Title", type: "text", placeholder: "Diagram Title" },
      { key: "format", label: "Format", type: "select", options: () => [{ value: "mermaid", label: "Mermaid" }, { value: "graphviz", label: "Graphviz" }] },
      { key: "source", label: "Source Code", type: "textarea", placeholder: "graph TD; A-->B" }
    ]
  },
  command_run: {
    type: "command_run",
    label: "Command Run (Execution Log)",
    fields: [
      { key: "command", label: "Command", type: "text", placeholder: "npm test" },
      { key: "exit_code", label: "Exit Code", type: "number", defaultValue: 0 },
      { key: "cwd", label: "Working Directory (Cwd)", type: "text" },
      { key: "stdout", label: "Stdout", type: "textarea" },
      { key: "stderr", label: "Stderr", type: "textarea" }
    ]
  }
};
