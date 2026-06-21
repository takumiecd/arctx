import { useEffect, useState, useRef, type CSSProperties } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { pickClient } from "./api";
import { Graph, type Selection } from "./Graph";
import { Panel } from "./Panel";
import { laneColors, laneOptions, type LaneColorOverrides } from "./model";
import type { RunDocument } from "./types";

const client = pickClient();

export function App() {
  const [selection, setSelection] = useState<Selection>(null);
  const [collapsedLaneIds, setCollapsedLaneIds] = useState<Set<string>>(() => new Set());
  const [laneColorOverrides, setLaneColorOverrides] = useState<LaneColorOverrides>({});
  const [laneColorRunId, setLaneColorRunId] = useState<string | null>(null);
  const [newLaneName, setNewLaneName] = useState("");
  const [showCuts, setShowCuts] = useState<boolean>(false);
  const [activeLaneId, setActiveLaneId] = useState<string | null>(null);
  const [showLanesMenu, setShowLanesMenu] = useState<boolean>(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();
  const invalidate = () => qc.invalidateQueries({ queryKey: ["run"] });
  const { data, isLoading, error } = useQuery({
    queryKey: ["run"],
    queryFn: () => client.getRun(),
    refetchInterval: client.writable ? 5000 : false,
  });
  const { data: savedLayout } = useQuery({
    queryKey: ["web-layout"],
    queryFn: () => client.getLayout(),
    enabled: Boolean(data),
  });

  // Standalone node creation isn't tied to a selection, so it lives in the
  // header rather than the per-selection panel.
  const addNode = useMutation({
    mutationFn: () => client.addNode({}),
    onSuccess: invalidate,
  });
  const createLane = useMutation({
    mutationFn: (name: string) => client.createLane({ name }),
    onSuccess: () => {
      setNewLaneName("");
      invalidate();
    },
  });

  // Step creation by dragging on the canvas. Output node omitted -> new node;
  // present -> connect into that existing node.
  const createStep = useMutation({
    mutationFn: ({ inputs, output }: { inputs: string[]; output?: string }) =>
      client.addStep({ input_node_ids: inputs, output_node_id: output, type: "step" }),
  });
  const saveLayout = useMutation({
    mutationFn: (nodes: Record<string, { x: number; y: number }>) =>
      client.saveLayout({ view: "default", nodes }),
  });

  useEffect(() => {
    if (!data) return;
    setLaneColorOverrides(readLaneColorOverrides(data.run_id));
    setLaneColorRunId(data.run_id);
  }, [data?.run_id]);

  useEffect(() => {
    if (data?.current_lane_id && !activeLaneId) {
      setActiveLaneId(data.current_lane_id);
    }
  }, [data?.current_lane_id, activeLaneId]);

  useEffect(() => {
    client.activeLaneId = activeLaneId;
  }, [activeLaneId]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (popoverRef.current && !popoverRef.current.contains(event.target as Node)) {
        setShowLanesMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside, { capture: true });
    return () => {
      document.removeEventListener("mousedown", handleClickOutside, { capture: true });
    };
  }, []);

  useEffect(() => {
    const runId = data?.run_id;
    if (!runId || laneColorRunId !== runId) return;
    window.localStorage.setItem(
      laneColorStorageKey(runId),
      JSON.stringify(laneColorOverrides),
    );
  }, [data?.run_id, laneColorOverrides, laneColorRunId]);

  if (isLoading) return <div className="center">loading run…</div>;
  if (error) return <div className="center error">{(error as Error).message}</div>;
  if (!data) return <div className="center">no run</div>;

  const actionError = (addNode.error ?? createLane.error ?? createStep.error) as Error | null;
  const lanes = laneOptions(data);
  const currentLaneId = activeLaneId || data.current_lane_id;
  const currentLaneName =
    (activeLaneId
      ? lanes.find((l) => l.lane_id === activeLaneId)?.label || activeLaneId
      : data.current_lane_name) || "none";
  const knownLaneIds = new Set(lanes.map((lane) => lane.lane_id).filter(Boolean) as string[]);
  const visibleCollapsedLaneIds = new Set(
    [...collapsedLaneIds].filter((laneId) => knownLaneIds.has(laneId)),
  );
  const sortedLanes = [...lanes].sort((a, b) => {
    const aCollapsed = visibleCollapsedLaneIds.has(a.lane_id);
    const bCollapsed = visibleCollapsedLaneIds.has(b.lane_id);
    if (aCollapsed === bCollapsed) {
      return a.label.localeCompare(b.label);
    }
    return aCollapsed ? 1 : -1;
  });
  const toggleLane = (laneId: string) => {
    setCollapsedLaneIds((prev) => {
      const next = new Set(prev);
      if (next.has(laneId)) {
        next.delete(laneId);
      } else {
        next.add(laneId);
        setSelection(null);
      }
      return next;
    });
  };
  const setLaneColor = (laneId: string, color: string) => {
    setLaneColorOverrides((prev) => ({ ...prev, [laneId]: color }));
  };

  return (
    <div className="layout">
      <header>
        <strong>arctx</strong> <code>{data.run_id}</code>
        <span className="muted">
          {" "}
          · {data.counts.nodes} nodes · {data.counts.steps} steps
          {!client.writable && " · read-only"}
        </span>
        {client.writable && (
          <div className="lane-selector-popover" ref={popoverRef}>
            <button
              type="button"
              className="lane-trigger-button"
              onClick={() => setShowLanesMenu(!showLanesMenu)}
            >
              current lane: <strong>{currentLaneName}</strong> ▾
            </button>
            {showLanesMenu && (
              <div className="lane-dropdown-menu">
                {lanes.length === 0 ? (
                  <div className="lane-dropdown-empty">no lanes yet</div>
                ) : (
                  <div className="lane-list">
                    {sortedLanes.map((lane) => {
                      const laneId = lane.lane_id;
                      if (!laneId) return null;
                      const collapsed = visibleCollapsedLaneIds.has(laneId);
                      const current = laneId === currentLaneId;
                      return (
                        <div
                          key={lane.group_id}
                          className={`lane-menu-item${current ? " active" : ""}${collapsed ? " menu-collapsed" : ""}`}
                          style={laneChipStyle(data, laneId, laneColorOverrides)}
                        >
                          <button
                            type="button"
                            className={`lane-collapse-toggle-btn${collapsed ? " collapsed" : ""}`}
                            title={collapsed ? "expand lane in canvas" : "collapse lane in canvas"}
                            onClick={() => toggleLane(laneId)}
                          >
                            {collapsed ? "▸" : "▾"}
                          </button>
                          <button
                            type="button"
                            className="lane-activate-btn"
                            onClick={() => {
                              setActiveLaneId(laneId);
                              setShowLanesMenu(false);
                            }}
                          >
                            <span className="lane-color-dot" style={{ backgroundColor: "var(--lane-color)" }} />
                            <span className="lane-name">{lane.label}</span>
                            {current && <span className="active-badge">current</span>}
                          </button>
                          <label className="lane-color-picker" title={`change ${lane.label} color`}>
                            <span className="sr-only">change {lane.label} color</span>
                            <input
                              type="color"
                              value={laneColors(data, laneId, laneColorOverrides).laneColor}
                              onChange={(event) => setLaneColor(laneId, event.currentTarget.value)}
                            />
                          </label>
                        </div>
                      );
                    })}
                  </div>
                )}
                {client.writable && (
                  <>
                    <div className="lane-dropdown-divider" />
                    <form
                      className="lane-create-form"
                      onSubmit={(event) => {
                        event.preventDefault();
                        const name = newLaneName.trim();
                        if (name) {
                          createLane.mutate(name, {
                            onSuccess: (res) => {
                              if (res.lane?.work_session_id) {
                                setActiveLaneId(res.lane.work_session_id);
                              }
                            }
                          });
                        }
                      }}
                    >
                      <input
                        aria-label="new lane name"
                        placeholder="new lane"
                        value={newLaneName}
                        onChange={(event) => setNewLaneName(event.currentTarget.value)}
                      />
                      <button disabled={createLane.isPending || !newLaneName.trim()} type="submit">
                        + lane
                      </button>
                    </form>
                  </>
                )}
              </div>
            )}
          </div>
        )}
        {client.writable && (
          <button className="add-node" disabled={addNode.isPending} onClick={() => addNode.mutate()}>
            + node
          </button>
        )}
        <label className="show-cuts-toggle" title="Show cut (inactive) nodes and steps">
          <input
            type="checkbox"
            checked={showCuts}
            onChange={(event) => setShowCuts(event.currentTarget.checked)}
          />
          <span>show cuts</span>
        </label>
        {client.writable && (
          <span className="muted hint"> · drag from a node to make a step</span>
        )}
        {actionError && <span className="error"> {actionError.message}</span>}
      </header>
      <main>
        <div className="canvas">
          <Graph
            doc={data}
            savedNodePositions={savedLayout?.nodes ?? {}}
            onSelect={setSelection}
            onNodePositionsChanged={(positions) => {
              if (client.writable) saveLayout.mutate(positions);
            }}
            onCreateStep={async (inputs, output) => {
              const res = await createStep.mutateAsync({ inputs, output });
              return { outputNodeId: res.step.output_node_id };
            }}
            onRunChanged={invalidate}
            collapsedLaneIds={visibleCollapsedLaneIds}
            onToggleLane={toggleLane}
            laneColorOverrides={laneColorOverrides}
            writable={client.writable}
            showCuts={showCuts}
          />
        </div>
        <Panel
          doc={data}
          selection={selection}
          client={client}
          onSelect={setSelection}
          laneColorOverrides={laneColorOverrides}
        />
      </main>
    </div>
  );
}

function laneChipStyle(
  doc: RunDocument,
  laneId: string,
  laneColorOverrides: LaneColorOverrides,
): CSSProperties {
  const colors = laneColors(doc, laneId, laneColorOverrides);
  return {
    "--lane-color": colors.laneColor,
    "--lane-bg": colors.laneBg,
  } as CSSProperties;
}

function laneColorStorageKey(runId: string): string {
  return `arctx.laneColors.${runId}`;
}

function readLaneColorOverrides(runId: string): LaneColorOverrides {
  const raw = window.localStorage.getItem(laneColorStorageKey(runId));
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed).filter(
        (entry): entry is [string, string] =>
          typeof entry[1] === "string" && /^#[0-9a-fA-F]{6}$/.test(entry[1]),
      ),
    );
  } catch {
    return {};
  }
}
