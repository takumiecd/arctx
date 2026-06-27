import { useEffect, useState, useRef, type CSSProperties } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { pickClient } from "./api";
import { Graph, type Selection } from "./Graph";
import { Panel } from "./Panel";
import { laneColors, laneOptions, type LaneColorOverrides } from "./model";
import type { RunDocument } from "./types";

const client = pickClient();

type ThemePreference = "light" | "dark" | "system";

function getInitialPreference(): ThemePreference {
  const stored = window.localStorage.getItem("arctx.theme");
  if (stored === "dark" || stored === "light" || stored === "system") return stored;
  return "system";
}

function resolveTheme(pref: ThemePreference): "light" | "dark" {
  if (pref !== "system") return pref;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function App() {
  const [selection, setSelection] = useState<Selection>(null);
  const [collapsedLaneIds, setCollapsedLaneIds] = useState<Set<string>>(() => new Set());
  const [laneColorOverrides, setLaneColorOverrides] = useState<LaneColorOverrides>({});
  const [laneColorRunId, setLaneColorRunId] = useState<string | null>(null);
  const [newLaneName, setNewLaneName] = useState("");
  const [newRunName, setNewRunName] = useState("");
  const [showCuts, setShowCuts] = useState<boolean>(false);
  const [activeLaneId, setActiveLaneId] = useState<string | null>(null);
  const [showLanesMenu, setShowLanesMenu] = useState<boolean>(false);
  const [showExtsMenu, setShowExtsMenu] = useState<boolean>(false);
  const [showRunsMenu, setShowRunsMenu] = useState<boolean>(false);
  const [themePref, setThemePref] = useState<ThemePreference>(getInitialPreference);
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">(() => {
    const t = resolveTheme(getInitialPreference());
    document.documentElement.setAttribute("data-theme", t);
    return t;
  });
  const popoverRef = useRef<HTMLDivElement>(null);
  const extPopoverRef = useRef<HTMLDivElement>(null);
  const runsPopoverRef = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();

  const invalidate = () => qc.invalidateQueries({ queryKey: ["run"] });

  // ── Theme persistence ─────────────────────────────────────────
  useEffect(() => {
    const resolved = resolveTheme(themePref);
    setResolvedTheme(resolved);
    document.documentElement.setAttribute("data-theme", resolved);
    window.localStorage.setItem("arctx.theme", themePref);
  }, [themePref]);

  // Track OS preference changes when in "system" mode
  useEffect(() => {
    if (themePref !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => {
      const resolved = resolveTheme("system");
      setResolvedTheme(resolved);
      document.documentElement.setAttribute("data-theme", resolved);
    };
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [themePref]);

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

  const { data: extensionsData } = useQuery({
    queryKey: ["extensions"],
    queryFn: () => client.getExtensions(),
    enabled: client.writable && Boolean(data),
  });

  const { data: runsData } = useQuery({
    queryKey: ["runs"],
    queryFn: () => client.listRuns(),
    enabled: client.writable,
  });

  // Switch the live API to another run. Reset all per-run UI state, point the
  // client at the new run, and refetch everything for it.
  const switchRun = (runId: string) => {
    setShowRunsMenu(false);
    if (runId === data?.run_id) return;
    client.activeRunId = runId;
    setActiveLaneId(null);
    setSelection(null);
    setCollapsedLaneIds(new Set());
    setNewLaneName("");
    qc.invalidateQueries();
  };

  const createRun = useMutation({
    mutationFn: (name: string) => client.createRun({ run_id: name }),
    onSuccess: (res) => {
      setNewRunName("");
      qc.invalidateQueries({ queryKey: ["runs"] });
      switchRun(res.run_id);
    },
  });

  const toggleExtension = useMutation({
    mutationFn: ({ name, enabled }: { name: string; enabled: boolean }) =>
      enabled ? client.disableExtension(name) : client.enableExtension(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["extensions"] });
      invalidate();
    },
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
      const target = event.target as Node;
      if (popoverRef.current && !popoverRef.current.contains(target)) {
        setShowLanesMenu(false);
      }
      if (extPopoverRef.current && !extPopoverRef.current.contains(target)) {
        setShowExtsMenu(false);
      }
      if (runsPopoverRef.current && !runsPopoverRef.current.contains(target)) {
        setShowRunsMenu(false);
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

  const actionError = (createLane.error ?? createStep.error ?? toggleExtension.error) as Error | null;
  const dark = resolvedTheme === "dark";
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
        <strong>arctx</strong>{" "}
        {client.writable ? (
          <span className="lane-selector-popover" ref={runsPopoverRef}>
            <button
              type="button"
              className="lane-trigger-button"
              onClick={() => setShowRunsMenu(!showRunsMenu)}
              title="switch run"
            >
              <code>{data.run_id}</code> ▾
            </button>
            {showRunsMenu && (
              <div className="lane-dropdown-menu">
                {!runsData || runsData.length === 0 ? (
                  <div className="lane-dropdown-empty">no runs found</div>
                ) : (
                  <div className="lane-list">
                    {runsData.map((run) => {
                      const current = run.run_id === data.run_id;
                      return (
                        <div
                          key={run.run_id}
                          className={`lane-menu-item${current ? " active" : ""}`}
                        >
                          <button
                            type="button"
                            className="lane-activate-btn"
                            onClick={() => switchRun(run.run_id)}
                            title={run.requirement_id || run.run_id}
                          >
                            <span className="lane-name">{run.run_id}</span>
                            {current && <span className="active-badge">current</span>}
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}
                <div className="lane-dropdown-divider" />
                <form
                  className="lane-create-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const name = newRunName.trim();
                    if (name) createRun.mutate(name);
                  }}
                >
                  <input
                    aria-label="new run id"
                    placeholder="new run id"
                    value={newRunName}
                    onChange={(event) => setNewRunName(event.currentTarget.value)}
                  />
                  <button disabled={createRun.isPending || !newRunName.trim()} type="submit">
                    + run
                  </button>
                </form>
                {createRun.error && (
                  <div className="lane-dropdown-empty" style={{ color: "var(--color-error)" }}>
                    {(createRun.error as Error).message}
                  </div>
                )}
              </div>
            )}
          </span>
        ) : (
          <code>{data.run_id}</code>
        )}
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
                          style={laneChipStyle(data, laneId, laneColorOverrides, dark)}
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
                              value={laneColors(data, laneId, laneColorOverrides, dark).laneColor}
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
                              if (res.lane?.lane_id) {
                                setActiveLaneId(res.lane.lane_id);
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
          <div className="lane-selector-popover" ref={extPopoverRef}>
            <button
              type="button"
              className="lane-trigger-button"
              onClick={() => setShowExtsMenu(!showExtsMenu)}
            >
              {(() => {
                const total = extensionsData?.extensions?.length ?? 0;
                const enabled = extensionsData?.extensions?.filter((ext) => ext.enabled).length ?? 0;
                return total > 0 ? `extensions (${enabled}) ▾` : "extensions ▾";
              })()}
            </button>
            {showExtsMenu && (
              <div className="lane-dropdown-menu" style={{ minWidth: "220px" }}>
                <div style={{ padding: "8px 12px", fontWeight: "600", fontSize: "12px", color: "var(--color-text-muted)", borderBottom: "1px solid var(--color-border)" }}>
                  enable/disable extensions
                </div>
                {(!extensionsData || !Array.isArray(extensionsData.extensions) || extensionsData.extensions.length === 0) ? (
                  <div className="lane-dropdown-empty">no extensions found</div>
                ) : (
                  <div className="lane-list" style={{ marginTop: "4px" }}>
                    {extensionsData.extensions.map((ext) => (
                      <div
                        key={ext.name}
                        className="lane-menu-item"
                        style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 12px" }}
                      >
                        <span style={{ fontSize: "13px", fontWeight: "500", color: "var(--color-text-secondary)" }}>{ext.name}</span>
                        <label style={{ display: "inline-flex", alignItems: "center", cursor: "pointer" }}>
                          <input
                            type="checkbox"
                            checked={ext.enabled}
                            disabled={toggleExtension.isPending}
                            onChange={() => toggleExtension.mutate({ name: ext.name, enabled: ext.enabled })}
                            style={{ width: "auto", margin: 0 }}
                          />
                        </label>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        <label className="show-cuts-toggle" title="Show cut (inactive) nodes and steps">
          <input
            type="checkbox"
            checked={showCuts}
            onChange={(event) => setShowCuts(event.currentTarget.checked)}
          />
          <span>show cuts</span>
        </label>
        <span className="theme-switcher" role="radiogroup" aria-label="Theme">
          {(["light", "system", "dark"] as const).map((opt) => (
            <button
              key={opt}
              type="button"
              className={`theme-switcher-btn${themePref === opt ? " active" : ""}`}
              onClick={() => setThemePref(opt)}
              title={opt === "system" ? "Follow system" : opt === "light" ? "Light" : "Dark"}
              aria-label={opt === "system" ? "Follow system" : opt === "light" ? "Light" : "Dark"}
              role="radio"
              aria-checked={themePref === opt}
            >
              {opt === "light" ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
              ) : opt === "dark" ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>
              )}
            </button>
          ))}
        </span>
        {client.writable && (
          <span className="muted hint"> · drag from a node to make a step</span>
        )}
        {actionError && <span className="error"> {actionError.message}</span>}
      </header>
      <main>
        <div className="canvas">
          <Graph
            doc={data}
            selection={selection}
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
            dark={dark}
          />
        </div>
        <Panel
          doc={data}
          selection={selection}
          client={client}
          onSelect={setSelection}
          laneColorOverrides={laneColorOverrides}
          dark={dark}
        />
      </main>
    </div>
  );
}

function laneChipStyle(
  doc: RunDocument,
  laneId: string,
  laneColorOverrides: LaneColorOverrides,
  dark: boolean,
): CSSProperties {
  const colors = laneColors(doc, laneId, laneColorOverrides, dark);
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
