// Resizable-width behavior for the detail panel: a draggable handle on the
// left edge, with the chosen width persisted in localStorage.

import { useEffect, useState, type PointerEvent as ReactPointerEvent } from "react";

export function useResizablePanelWidth(): [
  number,
  (event: ReactPointerEvent<HTMLDivElement>) => void,
] {
  const [width, setWidth] = useState(() => {
    const raw = window.localStorage.getItem("arctx.panelWidth");
    const saved = raw ? Number(raw) : NaN;
    return Number.isFinite(saved) ? clampPanelWidth(saved) : 420;
  });

  useEffect(() => {
    window.localStorage.setItem("arctx.panelWidth", String(width));
  }, [width]);

  const startResize = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    document.body.classList.add("resizing-panel");

    const onMove = (moveEvent: PointerEvent) => {
      setWidth(clampPanelWidth(startWidth + startX - moveEvent.clientX));
    };
    const onUp = () => {
      document.body.classList.remove("resizing-panel");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
  };

  return [width, startResize];
}

function clampPanelWidth(width: number): number {
  const max = Math.max(360, window.innerWidth - 280);
  return Math.min(Math.max(width, 300), Math.min(900, max));
}

export function PanelResizeHandle({
  onPointerDown,
}: {
  onPointerDown: (event: ReactPointerEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      className="panel-resize-handle"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize detail panel"
      onPointerDown={onPointerDown}
    />
  );
}
