# Agency Document Studio

Internal web app for creating, managing and exporting business documents
(invoices, quotations, proposals, agreements…). React (CRA/craco) + FastAPI + MongoDB.

See `HANDOFF.md` for the full project overview.

---

## Print / Save as PDF (browser print, vector)

Two ways to get a PDF, both rendered from the **same** React canvas and CSS:
**Download PDF** (one click, server-side headless Chromium, see below) and **Print…** (the browser's
own print engine, `window.print()`). Neither uses html2canvas/jsPDF or rasterisation. Both give true
vector PDFs: selectable/searchable text, embedded Poppins + IBM Plex Mono, crisp hairlines at any zoom.

### How it works

| Piece | File |
|---|---|
| The document that prints **is** the on-screen canvas | `frontend/src/components/DocumentCanvas.js` (`data-print-target`) |
| Print stylesheet: hides all app chrome, resets zoom/transform on ancestors, pagination rules | `frontend/src/styles/print.css` |
| Runtime `@page` rules (A4 / Letter, margins, paper colour, page numbers) | `frontend/src/lib/print.js` + `frontend/src/hooks/usePrintSetup.js` |
| "Download PDF ▾" split button (server PDF, A4/Letter, Print…, Word) | `frontend/src/components/DownloadMenu.js` (editor + public share page) |
| Server-PDF render target | `frontend/src/pages/PrintView.js` (`/print/:id`) + `backend/pdf_export.py` |
| Self-hosted fonts (`font-display: block`, OFL) | `frontend/public/fonts/` |

* **Page size**: the A4 / US Letter selector in the editor toolbar (saved per document as
  `page_size`) and on the share page drives `@page { size }`.
* **Margins**: 14 mm top, 16 mm left/right/bottom (same as the former server template).
  The on-screen paper uses the same padding, so line breaks on screen match the PDF.
* **Colours**: `print-color-adjust: exact` (+ `-webkit-` prefix) on the paper and everything in it.
* **Pagination**: line-item table headers repeat on every page (`thead { display: table-header-group }`),
  rows never split (`tr { break-inside: avoid }`), the totals + payment block is one unbreakable
  `.closing` group, the signature block never splits, headings stay with their text,
  `orphans/widows: 3`, and the closing footer line is never left alone on a page.
* **Before `window.print()`** the app waits for every font face it uses (`document.fonts.load` +
  `document.fonts.ready`) and for every image in the document to load/decode. Ctrl/Cmd+P also
  works (the `@page` rules are installed while the editor / share page is open).
* **Logo**: upload only (Settings → Brand). SVG (stays vector) or PNG/JPEG/WebP up to 2 MB,
  stored as a data URI at its original resolution (no re-encoding). Remote URLs are rejected by
  the API (`PUT /api/profile`) and ignored by the canvas. Script-bearing SVGs are rejected.

### Two page-setup strategies

| Mode | Used for | How margins / full bleed work | Page numbers |
|---|---|---|---|
| `paged` | Chromium: Chrome, Edge, Brave, Opera (desktop + Android) | Real `@page` margins; `@page { background }` paints the paper colour into the margins → dark theme is edge-to-edge | `@page @bottom-center` "Page X of Y" |
| `frame` | Firefox, Safari, all iOS browsers, anything else | `@page { margin: 0 }` so the paper colour covers the whole sheet; margins are recreated by a wrapper table whose spacer `<thead>`/`<tfoot>` rows repeat on every page (14 mm / 16 mm) + 16 mm side padding | none |

Force a mode for testing with `?printmode=paged` or `?printmode=frame` on the editor/share URL.

### No print-dialog settings needed

The app's only hint is **"Choose Save as PDF as the destination."** Users are never asked to enable
"Background graphics" or turn off "Headers and footers":

* `print-color-adjust: exact` (+ `-webkit-`) is set on `html`, `body`, the paper and every element in it,
  so backgrounds print even with "Background graphics" **unchecked** (verified: all PDF checks run with
  `print_background=False`).
* The full sheet, including the margin area, is filled with the paper colour: `usePrintSetup` puts
  `html.doc-print-light` / `html.doc-print-dark` on `<html>` while a document page is open (removed when you
  leave it), and `print.css` paints `html`/`body` with that colour in `@media print`. In Chromium, `@page`
  also gets the paper colour.
* `@page size` follows the editor's A4 / US Letter selector. Margins come from `@page`, and the browser's
  default headers/footers don't appear because the margin area is taken by the app's own `@page` rules.

### Browser behaviour and limitations

* **Chrome / Edge (Chromium 131+)**: fully supported and **verified** (see below), with
  "Background graphics" off: every corner and edge midpoint of every page is the paper colour.
* **Firefox**: uses `frame` mode. Firefox does not implement `@page` margin boxes
  (Mozilla bug 1854974), so **no page numbers**. Full bleed relies on `@page { margin: 0 }`
  and the repeating spacer rows. **Untested in real Firefox.** Headless Firefox can't produce PDFs
  here, so only the frame mechanism itself was verified, rendered by Chromium. Firefox may still
  require "Print backgrounds" for colours on some versions. If so, use **Download PDF**.
* **Safari (macOS / iOS)**: uses `frame` mode, so **no page numbers**. Safari 18.2+ does support
  margin boxes, but full bleed through `@page { background }` hasn't been confirmed in WebKit,
  so the safer frame mode is used. WebKit's support for repeating `<tfoot>` and for
  `break-inside: avoid` on grid containers has historically been weaker than Chromium's, so
  the bottom spacer or some keep-together rules may be ignored on some versions.
  **Untested in real Safari.** Safari may still require "Print backgrounds". If so, use **Download PDF**.
* All browsers: the browser's own "Margins" setting should stay on **Default**. The app defines
  the margins via `@page`. Choosing "None" or "Custom" overrides them.
* Very long single blocks (for example one section with several pages of text) do break across
  pages. That is intentional; only rows, totals/payment, signature and header blocks are kept whole.

### Verification (dev only)

`scripts/verify_print.py` creates throw-away documents (invoice with 1 / 15 / 60 line items,
US Letter invoice, dark invoice opened on the public share page at a narrow 600 px viewport so the
on-screen zoom is active, INR invoice with Indian digit grouping + PNG logo, five-page proposal with
pricing + signatures). It then opens **Download PDF ▾ → Print…** in the real app
(with `window.print` stubbed, to check fonts and images were ready) and prints the page with headless
Chromium. Paged mode is tested for every document; frame mode is also tested for three of them.
Afterwards it deletes the documents and restores the numbering counters.

Requirements (dev machine only, **not** in the backend image):

```bash
pip install playwright pymongo requests pillow && playwright install chromium
apt-get install -y poppler-utils        # pdftotext pdffonts pdfimages pdfinfo pdftoppm
python scripts/verify_print.py          # report -> test_reports/print_verification.json, PDFs -> /tmp/print-verify
```

Checks per PDF: page size; page count; real extractable text (`pdftotext`); all fonts embedded
and only Poppins / IBM Plex Mono (`pdffonts`); no raster images except an uploaded raster logo at
its original pixel size (`pdfimages`); every line item present exactly once with its description
and detail on the same page; table header on every page that contains line items; totals + billing
note + payment block on one page; both signature lines on one page; no page containing only the
footer; "Page X of Y" on every page (paged mode); every glyph inside the 14/16/16/16 mm box
(`pdftotext -bbox`); content spans the full text width (proves no zoom leaked into print);
paper colour on every edge pixel of every page (full bleed); fonts self-hosted, no external font
requests.

Latest run (headless Chromium, background graphics OFF): **10/10 PDFs pass** (7 documents in paged
mode, plus 3 of them in frame mode).

`tests/print_verify.py` covers browser print **and** server PDFs: light + dark invoices with 1 / 15 / 60
line items (A4, plus Letter for 15), 4 corners + 4 edge midpoints sampled on every page (`pdftoppm`),
`pdffonts` (all embedded), `pdftotext` (real text, "Page X of Y" on every server page), page counts.
Output of the last run: `test_reports/print_verify_output.txt` (102/102).

---

## One-click Download PDF (server-side, headless Chromium)

The primary action is a split button, **Download PDF ▾**. The main click downloads the server PDF in the size
selected in the editor. The menu has *Download PDF (A4)*, *Download PDF (US Letter)*, *Print…* (browser print)
and *Download Word (.docx)* (editor only; the public share page shows only the PDF and Print items). On mobile
it collapses to a single **Download** button that opens the same menu.

How it works: there is **no second HTML template**.
1. The editor flushes any pending autosave, then calls `GET /api/documents/{id}/pdf?size=A4|Letter`
   (or `GET /api/share/{token}/pdf` on the public page).
2. The backend signs a **print token** (JWT `type=print`, bound to one document id, valid 60 s) and opens
   `FRONTEND_URL/print/{id}?size=…#t=<token>` in a shared headless Chromium. The token is in the URL
   **fragment**, so it is never sent to or logged by the frontend host, and the page strips it from the URL
   right away. The backend never logs the URL.
3. The `/print` route renders the same `DocumentCanvas` + CSS as the editor. It fetches data from
   `GET /api/print/{id}` with an `X-Print-Token` header. That endpoint accepts **only** print tokens for that
   id, and every other endpoint rejects them. Waits for fonts and images, then sets `html[data-print-ready]`.
4. `page.pdf()` uses the CSS `@page` size and margins plus `print_background`. "Page X of Y" comes from
   Playwright's footer template in the 16 mm bottom margin, painted in the paper colour. A future in-page
   footer will sit inside the content box, so the two can't overlap. Header/footer templates can't use web
   fonts (Chromium limitation), so the page number uses the system mono font (Liberation Mono in the image).
   The document itself uses the embedded, self-hosted Poppins / IBM Plex Mono.
5. Response: `Content-Disposition: attachment; filename="INV-0012 - Client.pdf"; filename*=UTF-8''…`.
   Illegal filename characters and control characters are stripped, whitespace is collapsed, the client
   part is capped at 60 characters, and if there's no client the name is `INV-0012.pdf`.

Limits: one browser instance is reused (memory-safe flags), at most **2 renders at once** (`PDF_MAX_CONCURRENT`;
others wait up to 15 s, then get 503), **30 s render timeout** (`PDF_RENDER_TIMEOUT_S`, then 504). Health:
`GET /api/health/pdf`. In the UI: a loading state; after 6 s it says "Waking up server…" (free hosts sleep);
on failure or timeout, an error toast with a **Print instead** action that opens browser print.

`FRONTEND_URL` (required, startup fails without it) must be the public frontend URL. In production
that's the Vercel domain. `vercel.json` sends `X-Robots-Tag: noindex` and `Referrer-Policy: no-referrer` for `/print/*`.

## Backend image

`backend/Dockerfile`: `python:3.11-slim` plus Playwright's headless-shell Chromium (`playwright install
--with-deps --only-shell chromium`) and fonts. Runs as the unprivileged `app` user. Host on a **Docker host
(Render or Railway)**, not Vercel serverless. Give it at least 512 MB of RAM (1 GB recommended for parallel renders).

---

## Deployment, database and security

- **DEPLOY.md**: Vercel (frontend, `/api` rewrite proxy, security headers) + Docker backend on Render/Railway + Atlas, with the full environment-variable list and the `/api/health` health check.
- **DATABASE.md**: migrating local data to Atlas (dry-run first), scheduled encrypted backups, restore procedure.
- **PRE_LAUNCH_CHECKLIST.md**: deferred security items (credential rotation, history scrub, …).
