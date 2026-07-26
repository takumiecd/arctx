// Shared types for the detail/action panel modules.

import type { RunClient } from "../api";
import type { RunDocument } from "../types";
import type { Selection } from "../Graph";
import type { LaneColorOverrides } from "../model";

export interface Props {
  doc: RunDocument;
  selection: Selection;
  client: RunClient;
  onSelect: (sel: Selection) => void;
  laneColorOverrides: LaneColorOverrides;
  dark: boolean;
}

export type RecordSelection = Extract<Exclude<Selection, null>, { kind: "node" | "step" }>;
export type BulkSelection = Extract<Exclude<Selection, null>, { kind: "records" }>;

export interface AttachTarget {
  key: string;
  label: string;
  selection: RecordSelection;
}

export interface DetailUnit {
  stepId: string | null;
  outputNodeId: string;
  selected: RecordSelection;
}


export type Tab = "content" | "flow" | "edit";
export type AttachPreset = "note" | "git_change" | "diagram" | "command_run" | "custom";
