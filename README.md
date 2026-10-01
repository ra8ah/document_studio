# Agency Document Studio

Internal web app for creating, managing and exporting business documents
(invoices, quotations, proposals, agreements…). React (CRA/craco) + FastAPI + MongoDB.

See `HANDOFF.md` for the full project overview.

---

## Print / Save as PDF (client-side, vector)

PDFs are produced by the **browser's own print engine** (`window.print()`).
There is no server-side PDF anymore: no Chromium, no Playwright, no html2canvas/jsPDF
or any canvas rasterisation. The result is a true vector PDF: selectable/searchable
text, embedded Poppins + IBM Plex Mono, crisp hairlines at any zoom.

### How it works

| Piece | File |
|---|---|
| The document that prints **is** the on-screen canvas | `frontend/src/components/DocumentCanvas.js` (`data-print-target`) |
| Print stylesheet: hides all app chrome, resets zoom/transform on ancestors, pagination rules | `frontend/src/styles/print.css` |
| Runtime `@page` rules (A4 / Letter, margins, paper colour, page numbers) | `frontend/src/lib/print.js` + `frontend/src/hooks/usePrintSetup.js` |
| "Print / Save as PDF" action + dialog hint | `frontend/src/components/PrintButton.js` (editor + public share page) |
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

### Recommended print-dialog settings (shown in the app's hint)

1. Destination: **Save as PDF**
2. **Background graphics** ON (Firefox/Safari: "Print backgrounds")
3. **Headers and footers** OFF (otherwise the browser adds its own URL/date/title lines)

### Browser behaviour and limitations

* **Chrome / Edge (Chromium 131+)**: fully supported and **verified** (see below).
  If "Background graphics" is left off, Chromium does not paint the `@page` background,
  so the **page margins print white**. This is why the hint asks for it.
* **Firefox**: uses `frame` mode. Firefox does not implement `@page` margin boxes
  (Mozilla bug 1854974), so **no page numbers**. Full bleed relies on `@page { margin: 0 }`
  and the repeating spacer rows. *Not verified in this environment:* headless Firefox can't
  produce PDFs here, so only the frame mechanism itself was verified, rendered by Chromium.
* **Safari (macOS / iOS)**: uses `frame` mode, so **no page numbers**. Safari 18.2+ does support
  margin boxes, but full bleed through `@page { background }` hasn't been confirmed in WebKit,
  so the safer frame mode is used. WebKit's support for repeating `<tfoot>` and for
  `break-inside: avoid` on grid containers has historically been weaker than Chromium's, so
  the bottom spacer or some keep-together rules may be ignored on some versions.
  *Not verified in this environment.*
* All browsers: the browser's own "Margins" setting should stay on **Default**. The app defines
  the margins via `@page`. Choosing "None" or "Custom" overrides them.
* Very long single blocks (for example one section with several pages of text) do break across
  pages. That is intentional; only rows, totals/payment, signature and header blocks are kept whole.

### Verification (dev only)

`scripts/verify_print.py` creates throw-away documents (invoice with 1 / 15 / 60 line items,
US Letter invoice, dark invoice opened on the public share page at a narrow 600 px viewport so the
on-screen zoom is active, INR invoice with Indian digit grouping + PNG logo, five-page proposal with
pricing + signatures). It then clicks **Print / Save as PDF → Open print dialog** in the real app
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

Latest run (headless Chromium 153): **10/10 PDFs pass** (7 documents in paged mode, plus 3 of them
in frame mode).

---

## Backend image

`backend/Dockerfile` is a slim `python:3.11-slim` image (FastAPI, Motor, python-docx) running as an
unprivileged `app` user. There's no browser in the image. DOCX export (`GET /api/documents/{id}/docx`)
is unchanged. The former `/api/documents/{id}/pdf` and `/api/share/{token}/pdf` routes have been removed.
