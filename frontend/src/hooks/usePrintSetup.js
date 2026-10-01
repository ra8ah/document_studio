import { useEffect } from "react";
import { buildPageCss, resolvePrintMode } from "@/lib/print";

/**
 * Installs the @page rules (size, margins, paper colour, page numbers) for the
 * document currently on screen, so both the Print button and Ctrl/Cmd+P produce
 * the same output. Removed again when the page unmounts.
 */
export default function usePrintSetup({ size, theme }) {
  useEffect(() => {
    const mode = resolvePrintMode();
    const el = document.createElement("style");
    el.id = "doc-print-page";
    el.textContent = buildPageCss({ size, theme, mode });
    document.head.appendChild(el);
    const html = document.documentElement;
    html.dataset.printMode = mode;
    return () => {
      el.remove();
      if (!document.getElementById("doc-print-page")) delete html.dataset.printMode;
    };
  }, [size, theme]);
}
