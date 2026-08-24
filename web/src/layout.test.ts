// Regression tests for the graph layout.
//
// The layout is the one part of the web GUI with no visible failure mode: a
// wrong position is still a position, so a regression shows up as "the canvas
// got hard to read" weeks later rather than as an error. The two fixes that
// motivated these tests (#54, #55) were verified by measuring one real run by
// hand; what follows pins the properties those measurements stood for, on
// fixtures small enough to reason about.
//
// Assertions are written in the layout's own units (LAYER_GAP, ROW_GAP) rather
// than in pixels, so tuning the grid does not break them — only changing what
// the layout *does* should.

import { describe, expect, it } from "vitest";

import {
  CHAIN_WRAP_LENGTH,
  FAN_STACK_LIMIT,
  LAYER_GAP,
  MAX_STACK_HEIGHT,
  ROW_GAP,
  layout,
  type LayoutDirection,
  type LayoutOpts,
  type Pos,
} from "./layout";
import type { RecordProvenance, RunDocument, RunGroup, RunLane } from "./types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

type Edge = [string | string[], string];

interface Spec {
  edges: Edge[];
  /** Defaults to the first edge's first input. */
  root?: string;
  /** lane id -> member node ids. Members get provenance + a lane group. */
  lanes?: Record<string, string[]>;
  /** Cut these nodes; descendants inherit, as `arctx.core.cuts` computes it. */
  cutNodes?: string[];
}

function asList(value: string | string[]): string[] {
  return Array.isArray(value) ? value : [value];
}

function makeDoc(spec: Spec): RunDocument {
  const order: string[] = [];
  const see = (id: string) => {
    if (!order.includes(id)) order.push(id);
  };

  const first = spec.edges[0];
  const root = spec.root ?? (first ? asList(first[0])[0] : "n_root");
  see(root);
  for (const [from, to] of spec.edges) {
    asList(from).forEach(see);
    see(to);
  }

  // A cut node takes everything downstream of it with it. The export document
  // carries the resolved flag per record, so resolve it here too.
  const inactive = new Set(spec.cutNodes ?? []);
  for (let changed = true; changed; ) {
    changed = false;
    for (const [from, to] of spec.edges) {
      if (inactive.has(to)) continue;
      if (asList(from).some((id) => inactive.has(id))) {
        inactive.add(to);
        changed = true;
      }
    }
  }

  const laneEntries = Object.entries(spec.lanes ?? {});
  const provenance: Record<string, RecordProvenance> = {};
  for (const [laneId, memberIds] of laneEntries) {
    for (const nodeId of memberIds) {
      provenance[nodeId] = {
        record_id: nodeId,
        lane_id: laneId,
        user_id: "test",
        event_id: `we:${nodeId}`,
        event_type: "add_step",
      };
    }
  }

  const lanes: RunLane[] = laneEntries.map(([laneId]) => ({
    lane_id: laneId,
    run_id: "run_test",
    created_by: "test",
    status: "open",
    name: laneId,
  }));

  const groups: RunGroup[] = laneEntries.map(([laneId, memberIds]) => ({
    group_id: `lane:${laneId}`,
    kind: "lane",
    lane_id: laneId,
    label: laneId,
    node_ids: memberIds,
    step_ids: [],
  }));

  const nodes = order.map((nodeId) => ({
    node_id: nodeId,
    metadata: {},
    inactive: inactive.has(nodeId),
    directly_cut: inactive.has(nodeId),
  }));

  const steps = spec.edges.map(([from, to]) => ({
    step_id: `t:${to}`,
    input_node_ids: asList(from),
    output_node_id: to,
    metadata: {},
    inactive: inactive.has(to),
    directly_cut: inactive.has(to),
  }));

  return {
    arctx_export_version: 1,
    run_id: "run_test",
    root_node_id: root,
    counts: { nodes: nodes.length, steps: steps.length, payloads: 0 },
    nodes,
    steps,
    payloads: [],
    lanes,
    groups,
    record_provenance: provenance,
  };
}

const DEFAULTS: LayoutOpts = {
  collapsedLaneIds: new Set<string>(),
  showCuts: false,
  direction: "right",
};

function positionsFor(spec: Spec, opts: Partial<LayoutOpts> = {}): Record<string, Pos> {
  return layout(makeDoc(spec), { ...DEFAULTS, ...opts });
}

/** `parent -> c0, c1, ... cN-1`, all leaves. */
function fanEdges(parent: string, prefix: string, count: number): Edge[] {
  return Array.from({ length: count }, (_, index) => [parent, `${prefix}${index}`] as Edge);
}

/** `from -> p0 -> p1 -> ... -> pN-1`, one link per layer. */
function chainEdges(from: string, prefix: string, count: number): Edge[] {
  const ids = Array.from({ length: count }, (_, index) => `${prefix}${index}`);
  return ids.map((id, index) => [index === 0 ? from : ids[index - 1], id] as Edge);
}

// ---------------------------------------------------------------------------
// Assertions
// ---------------------------------------------------------------------------

function distinct(values: number[]): number[] {
  return [...new Set(values)].sort((a, b) => a - b);
}

function xs(positions: Record<string, Pos>, ids: string[]): number[] {
  return ids.map((id) => positions[id].x);
}

function ys(positions: Record<string, Pos>, ids: string[]): number[] {
  return ids.map((id) => positions[id].y);
}

/** Two nodes drawn at the same point are one node the reader cannot see. */
function expectNoOverlap(positions: Record<string, Pos>): void {
  const seen = new Map<string, string>();
  const collisions: string[] = [];
  for (const [nodeId, pos] of Object.entries(positions)) {
    const key = `${Math.round(pos.x)},${Math.round(pos.y)}`;
    const other = seen.get(key);
    if (other) collisions.push(`${other} and ${nodeId} at (${key})`);
    else seen.set(key, nodeId);
  }
  expect(collisions).toEqual([]);
}

// ---------------------------------------------------------------------------

describe("the visible graph", () => {
  it("drops cut records unless cuts are shown", () => {
    const spec: Spec = {
      edges: [["a", "b"], ["b", "c"], ["a", "d"]],
      cutNodes: ["b"],
    };

    const hidden = positionsFor(spec);
    expect(Object.keys(hidden).sort()).toEqual(["a", "d"]);

    const shown = positionsFor(spec, { showCuts: true });
    expect(Object.keys(shown).sort()).toEqual(["a", "b", "c", "d"]);
  });

  it("contracts a collapsed lane into one pseudo-node", () => {
    const spec: Spec = {
      edges: [["a", "b"], ["b", "c"], ["c", "d"]],
      lanes: { work: ["b", "c", "d"] },
    };

    const expanded = positionsFor(spec);
    expect(Object.keys(expanded).sort()).toEqual(["a", "b", "c", "d"]);

    const collapsed = positionsFor(spec, { collapsedLaneIds: new Set(["work"]) });
    expect(Object.keys(collapsed).sort()).toEqual(["a", "lane:work"]);
    expect(collapsed["lane:work"].x).toBeGreaterThan(collapsed.a.x);
  });

  it("lays 'down' out as the transpose of 'right'", () => {
    const spec: Spec = { edges: [...chainEdges("a", "n", 4), ...fanEdges("n1", "leaf", 3)] };

    const right = positionsFor(spec, { direction: "right" as LayoutDirection });
    const down = positionsFor(spec, { direction: "down" as LayoutDirection });

    for (const [nodeId, pos] of Object.entries(right)) {
      expect(down[nodeId]).toEqual({ x: pos.y, y: pos.x });
    }
  });

  it("is deterministic", () => {
    const spec: Spec = {
      edges: [...chainEdges("a", "n", 5), ...fanEdges("n2", "leaf", 40)],
      lanes: { one: ["n0", "n1", "n2"], two: ["n3", "n4"] },
    };
    expect(positionsFor(spec)).toEqual(positionsFor(spec));
  });
});

describe("chains", () => {
  it("places each link one layer right of the last, on one row", () => {
    const ids = ["n0", "n1", "n2", "n3"];
    const positions = positionsFor({ edges: chainEdges("a", "n", 4) });

    expect(distinct(ys(positions, ids))).toHaveLength(1);
    for (let index = 1; index < ids.length; index += 1) {
      expect(positions[ids[index]].x - positions[ids[index - 1]].x).toBe(LAYER_GAP);
    }
    expectNoOverlap(positions);
  });

  it("wraps a long chain instead of running off the canvas", () => {
    const length = CHAIN_WRAP_LENGTH * 3;
    const ids = Array.from({ length }, (_, index) => `n${index}`);
    const positions = positionsFor({ edges: chainEdges("a", "n", length) });

    // The whole run is one chain, so the canvas is as wide as one wrapped row
    // plus the root's own column — not as wide as the chain is long.
    expect(distinct(xs(positions, ids)).length).toBeLessThanOrEqual(CHAIN_WRAP_LENGTH + 1);
    expect(distinct(ys(positions, ids)).length).toBeGreaterThan(1);
    expectNoOverlap(positions);
  });
});

describe("fans", () => {
  it("stacks a fan up to the limit in a single column, as it always did", () => {
    const ids = Array.from({ length: FAN_STACK_LIMIT }, (_, index) => `leaf${index}`);
    const positions = positionsFor({ edges: fanEdges("a", "leaf", FAN_STACK_LIMIT) });

    expect(distinct(xs(positions, ids))).toHaveLength(1);
    expect(distinct(ys(positions, ids))).toHaveLength(FAN_STACK_LIMIT);

    // Consecutive rows, no gaps: a small fan reads as a list.
    const rows = distinct(ys(positions, ids));
    for (let index = 1; index < rows.length; index += 1) {
      expect(rows[index] - rows[index - 1]).toBe(ROW_GAP);
    }
    expectNoOverlap(positions);
  });

  it("packs a fan past the limit into a block, not a column", () => {
    const count = FAN_STACK_LIMIT + 1;
    const ids = Array.from({ length: count }, (_, index) => `leaf${index}`);
    const positions = positionsFor({ edges: fanEdges("a", "leaf", count) });

    expect(distinct(xs(positions, ids)).length).toBeGreaterThan(1);
    expect(distinct(ys(positions, ids)).length).toBeLessThan(count);
    expectNoOverlap(positions);
  });

  it("keeps a fan of chains attached to the heads it fans from", () => {
    // A sweep whose trials take more than one step each. A chain is one row
    // tall, so classifying block members by span would pack the heads and
    // strand every tail in the catch-all pass at the bottom of the lane.
    const chains = 10;
    const heads = Array.from({ length: chains }, (_, index) => `h${index}`);
    const positions = positionsFor({
      edges: [
        ...heads.flatMap((head) => [["a", head] as Edge, ...chainEdges(head, `${head}_`, 2)]),
      ],
    });

    for (const head of heads) {
      expect(positions[`${head}_0`]).toEqual({
        x: positions[head].x + LAYER_GAP,
        y: positions[head].y,
      });
      expect(positions[`${head}_1`]).toEqual({
        x: positions[head].x + 2 * LAYER_GAP,
        y: positions[head].y,
      });
    }
    expect(distinct(ys(positions, heads))).toHaveLength(chains);
    expectNoOverlap(positions);
  });

  it("keeps a big fan roughly square and far shorter than a row per leaf", () => {
    // The shape that started this: one node carrying a whole sweep.
    const count = 387;
    const ids = Array.from({ length: count }, (_, index) => `leaf${index}`);
    const positions = positionsFor({ edges: fanEdges("a", "leaf", count) });

    const rows = distinct(ys(positions, ids));
    const cols = distinct(xs(positions, ids));

    expect(cols.length).toBeGreaterThan(1);
    expect(rows.length).toBeLessThan(count / 8);

    const height = rows[rows.length - 1] - rows[0];
    const width = cols[cols.length - 1] - cols[0];
    expect(height).toBeLessThan(count * ROW_GAP * 0.1);
    expect(width / height).toBeGreaterThan(0.4);
    expect(width / height).toBeLessThan(2.5);

    expectNoOverlap(positions);
  });
});

describe("branch points", () => {
  it("places every child of a branch point in the layer right after it", () => {
    // Each child branches again, so none of them is a leaf to be packed.
    const children = ["b", "c", "d"];
    const positions = positionsFor({
      edges: [
        ...children.map((child) => ["a", child] as Edge),
        ...children.flatMap((child) => fanEdges(child, `${child}x`, 2)),
      ],
    });

    for (const child of children) {
      expect(positions[child].x - positions.a.x).toBe(LAYER_GAP);
    }
    expect(distinct(ys(positions, children))).toHaveLength(children.length);
    expectNoOverlap(positions);
  });

  it("puts a sibling branch directly under a leaf block, not after a hole", () => {
    // A node with a big fan of leaves *and* a branching sibling: the rows the
    // fan reserves must be the block's rows, not one per leaf, or the sibling
    // lands a screen further down.
    const fanCount = 40;
    const leafIds = Array.from({ length: fanCount }, (_, index) => `leaf${index}`);
    const positions = positionsFor({
      edges: [...fanEdges("a", "leaf", fanCount), ["a", "sib"], ...fanEdges("sib", "sibx", 2)],
    });

    const blockRows = distinct(ys(positions, leafIds));
    const blockBottom = blockRows[blockRows.length - 1];

    expect(blockRows.length).toBeLessThan(fanCount);
    expect(positions.sib.y).toBeGreaterThan(blockBottom);
    expect(positions.sib.y - blockBottom).toBeLessThanOrEqual(2 * ROW_GAP);
    expectNoOverlap(positions);
  });
});

describe("lane blocks", () => {
  const laneNodes = (count: number) =>
    Array.from({ length: count }, (_, index) => `lane${index}`);

  function siblingLanes(count: number): Spec {
    const ids = laneNodes(count);
    return {
      edges: [["root", "base"], ...ids.map((id) => ["base", id] as Edge)],
      root: "root",
      lanes: {
        base: ["root", "base"],
        ...Object.fromEntries(ids.map((id) => [id, [id]])),
      },
    };
  }

  it("leaves a narrow layer of lanes as one column", () => {
    const ids = laneNodes(3);
    const positions = positionsFor(siblingLanes(3));

    expect(distinct(xs(positions, ids))).toHaveLength(1);
    expect(distinct(ys(positions, ids))).toHaveLength(3);
    expectNoOverlap(positions);
  });

  it("packs a wide layer of lanes into sub-columns instead of one hairline", () => {
    // A real run had 69 lanes at one depth: as a single column that is a
    // 23,000px ribbon nothing can read.
    const count = 69;
    const ids = laneNodes(count);
    const positions = positionsFor(siblingLanes(count));

    expect(distinct(xs(positions, ids)).length).toBeGreaterThan(1);

    const bottom = Math.max(...Object.values(positions).map((pos) => pos.y));
    expect(bottom).toBeLessThan(MAX_STACK_HEIGHT * 1.5);
    expectNoOverlap(positions);
  });

  it("places a child lane strictly right of the lane it branched from", () => {
    const positions = positionsFor({
      edges: [["a", "b"], ["b", "c"], ["c", "d"]],
      lanes: { first: ["a", "b"], second: ["c", "d"] },
    });

    expect(Math.min(positions.c.x, positions.d.x)).toBeGreaterThan(
      Math.max(positions.a.x, positions.b.x),
    );
    expectNoOverlap(positions);
  });
});
