/*
 * Client-side printing via the browser's native print engine (vector output).
 *
 * Two page-setup strategies, chosen per engine:
 *  - "paged" (Chromium: Chrome, Edge, Opera, Brave …)
 *      @page has real margins (14mm top, 16mm sides/bottom), the @page box itself
 *      carries the paper colour (so the margins are painted too → full bleed) and
 *      page numbers come from the @bottom-center margin box.
 *  - "frame" (Firefox, Safari and anything else)
 *      @page margin is 0 (so the root background covers the whole sheet → full bleed)
 *      and the margins are recreated by a wrapper table whose <thead>/<tfoot> spacer
 *      rows repeat on every printed page + 16mm side padding. No page numbers.
 *
 * Override for testing with ?printmode=paged|frame in the URL.
 */

export const PAGE_MARGINS = { top: "14mm", right: "16mm", bottom: "16mm", left: "16mm" };

const PAPER = {
  light: { paper: "#F2ECE0", muted: "#78746C" },
  dark: { paper: "#1C1815", muted: "#A8A29A" },
};

const FONT_FACES = [
  "400 1em Poppins", "500 1em Poppins", "600 1em Poppins", "700 1em Poppins",
  '400 1em "IBM Plex Mono"', '500 1em "IBM Plex Mono"', '600 1em "IBM Plex Mono"',
];
// Sample text touching both the latin and latin-ext subsets (₹ lives in latin-ext).
const FONT_SAMPLE = "Aa0₹€£";

export function isChromium() {
  if (typeof navigator === "undefined") return false;
  const brands = navigator.userAgentData?.brands;
  if (brands && brands.some((b) => /Chromium/i.test(b.brand))) return true;
  const ua = navigator.userAgent || "";
  // iOS browsers are all WebKit underneath, regardless of branding.
  if (/CriOS|EdgiOS|FxiOS|Firefox\//.test(ua)) return false;
  return /Chrome\/|Chromium\/|Edg\//.test(ua);
}

export function resolvePrintMode() {
  try {
    const forced = new URLSearchParams(window.location.search).get("printmode");
    if (forced === "paged" || forced === "frame") return forced;
  } catch { /* ignore */ }
  return isChromium() ? "paged" : "frame";
}

export function buildPageCss({ size = "A4", theme = "light", mode = "paged" }) {
  const { paper, muted } = PAPER[theme === "dark" ? "dark" : "light"];
  const sizeKw = size === "Letter" ? "letter" : "A4";
  const m = PAGE_MARGINS;
  const margin = `margin: ${m.top} ${m.right} ${m.bottom} ${m.left};`;
  // "server": headless Chromium adds "Page X of Y" via its footer template, so no CSS margin box here
  if (mode === "server") return `@page { size: ${sizeKw}; ${margin} background: ${paper}; }`;
  if (mode === "frame") return `@page { size: ${sizeKw}; margin: 0; }`;
  return `@page {
  size: ${sizeKw};
  ${margin}
  background: ${paper};
  @bottom-center {
    content: "Page " counter(page) " of " counter(pages);
    font-family: "IBM Plex Mono", ui-monospace, monospace;
    font-size: 6.5pt;
    letter-spacing: .12em;
    text-transform: uppercase;
    color: ${muted};
  }
}`;
}

function waitForImage(img) {
  if (img.complete && img.naturalWidth > 0) {
    return img.decode ? img.decode().catch(() => {}) : Promise.resolve();
  }
  if (img.complete) return Promise.resolve(); // broken image: don't block printing
  return new Promise((res) => {
    img.addEventListener("load", res, { once: true });
    img.addEventListener("error", res, { once: true });
  });
}

/** Resolve once every font face and image the printed document needs is ready. */
export async function waitForPrintAssets(root) {
  if (document.fonts) {
    await Promise.all(FONT_FACES.map((f) => document.fonts.load(f, FONT_SAMPLE).catch(() => {})));
    await document.fonts.ready;
  }
  const imgs = root ? [...root.querySelectorAll("img")] : [];
  await Promise.all(imgs.map(waitForImage));
  // Let layout settle (two frames) before the print snapshot.
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
}

export async function printDocument() {
  const target = document.querySelector("[data-print-target]");
  if (document.activeElement && typeof document.activeElement.blur === "function") document.activeElement.blur();
  try { window.getSelection()?.removeAllRanges(); } catch { /* ignore */ }
  await waitForPrintAssets(target);
  window.print();
}

export const LOGO_DATA_URI = /^data:image\/(svg\+xml|png|jpeg|webp);base64,/;
export const isSafeLogo = (v) => typeof v === "string" && LOGO_DATA_URI.test(v);
