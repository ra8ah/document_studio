import { useEffect } from "react";
import { buildPageCss, resolvePrintMode } from "@/lib/print";

const THEME_CLASSES = ["doc-print-light", "doc-print-dark"];

/**
 * Installs the @page rules (size, margins, paper colour, page numbers) and the html.doc-print-<theme>
 * class (full-sheet paper colour in print) for the document on screen. Removed when the page unmounts.
 */
export default function usePrintSetup({ size, theme, mode: forcedMode }) {
  useEffect(() => {
    const mode = forcedMode || resolvePrintMode();
    const t = theme === "dark" ? "dark" : "light";
    const el = document.createElement("style");
    el.id = "doc-print-page";
    el.textContent = buildPageCss({ size, theme: t, mode });
    document.head.appendChild(el);
    const html = document.documentElement;
    html.dataset.printMode = mode;
    html.classList.remove(...THEME_CLASSES);
    html.classList.add(`doc-print-${t}`);
    return () => {
      el.remove();
      if (!document.getElementById("doc-print-page")) {
        delete html.dataset.printMode;
        html.classList.remove(...THEME_CLASSES);
      }
    };
  }, [size, theme, forcedMode]);
}
