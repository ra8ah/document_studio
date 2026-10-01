import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { Minus, Plus, Maximize2 } from "lucide-react";

const MM = 96 / 25.4;
export const PAGE_W = { A4: 210 * MM, Letter: 215.9 * MM };
const STEPS = [0.5, 0.67, 0.75, 0.9, 1, 1.1, 1.25, 1.5, 2];

/** zoom state: "fit" (fit width of the container, max 100%) or a fixed factor */
export function useZoom(containerRef, size) {
  const [mode, setMode] = useState("fit");
  const [fit, setFit] = useState(1);
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    const measure = () => setFit(Math.max(0.2, Math.min(1, (el.clientWidth - 24) / PAGE_W[size === "Letter" ? "Letter" : "A4"])));
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [containerRef, size]);
  const scale = mode === "fit" ? fit : mode;
  const step = (dir) => {
    const next = dir > 0 ? STEPS.find((s) => s > scale + 0.001) : [...STEPS].reverse().find((s) => s < scale - 0.001);
    if (next) setMode(next);
  };
  return { scale, mode, setMode, step };
}

/** transform: scale with a wrapper sized to the scaled box, so surrounding layout stays correct (no CSS zoom) */
export function ZoomFrame({ scale, children }) {
  const inner = useRef(null);
  const [box, setBox] = useState({ w: 0, h: 0 });
  useLayoutEffect(() => {
    const el = inner.current;
    const measure = () => setBox({ w: el.offsetWidth, h: el.offsetHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return (
    <div className="zoom-frame mx-auto" style={{ width: box.w * scale || undefined, height: box.h * scale || undefined }} data-testid="zoom-frame" data-scale={scale.toFixed(2)}>
      <div ref={inner} style={{ width: "max-content", transform: `scale(${scale})`, transformOrigin: "top left" }}>{children}</div>
    </div>
  );
}

export function ZoomControls({ zoom }) {
  const btn = "h-8 min-w-8 px-2 rounded-full hover:bg-foreground/5 border border-foreground/15 text-xs font-medium inline-flex items-center justify-center gap-1";
  return (
    <div className="flex items-center gap-1" role="group" aria-label="Zoom" data-testid="zoom-controls">
      <button className={btn} onClick={() => zoom.step(-1)} aria-label="Zoom out" data-testid="zoom-out"><Minus size={14} aria-hidden="true" /></button>
      <span className="w-12 text-center text-xs tabular-nums" aria-live="polite" data-testid="zoom-level">{Math.round(zoom.scale * 100)}%</span>
      <button className={btn} onClick={() => zoom.step(1)} aria-label="Zoom in" data-testid="zoom-in"><Plus size={14} aria-hidden="true" /></button>
      <button className={`${btn} ${zoom.mode === "fit" ? "bg-foreground/10" : ""}`} onClick={() => zoom.setMode("fit")} aria-pressed={zoom.mode === "fit"} data-testid="zoom-fit"><Maximize2 size={12} aria-hidden="true" /> Fit</button>
      <button className={`${btn} ${zoom.mode === 1 ? "bg-foreground/10" : ""}`} onClick={() => zoom.setMode(1)} aria-pressed={zoom.mode === 1} data-testid="zoom-100">100%</button>
    </div>
  );
}
