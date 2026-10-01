import { useEffect, useState } from "react";

const MM = 96 / 25.4;
const PAGE_H = { A4: 297, Letter: 279.4 };
const TOP = 14, BOTTOM = 16; // == @page margins (lib/print.js PAGE_MARGINS)

/** Dashed on-screen guides where the printed pages will split (approximate: rows are never split, so a
 * break can come slightly earlier). Hidden in print via data-print-hide. */
export default function PageGuides({ rootRef, size }) {
  const [h, setH] = useState(0);
  useEffect(() => {
    const el = rootRef.current;
    if (!el) return undefined;
    const ro = new ResizeObserver(() => setH(el.offsetHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, [rootRef]);
  const content = (PAGE_H[size === "Letter" ? "Letter" : "A4"] - TOP - BOTTOM) * MM;
  const lines = [];
  for (let k = 1; TOP * MM + k * content < h - BOTTOM * MM - 2; k++) lines.push(TOP * MM + k * content);
  return (
    <div aria-hidden="true" data-print-hide data-testid="page-guides" data-count={lines.length}>
      {lines.map((y, i) => (
        <div key={i} className="page-guide" style={{ top: y }} data-testid={`page-guide-${i + 2}`}>
          <span>Page {i + 2}</span>
        </div>
      ))}
    </div>
  );
}
