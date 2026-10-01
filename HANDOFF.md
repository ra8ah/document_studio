# HANDOFF — Agency Document Studio (read me first)

This is the single source of truth for the project. A new Emergent session should
read this top-to-bottom, then `REIMPORT.md`, `DEPLOY.md`, and `/app/memory/PRD.md`.

---

## 1. What this app is
A premium **internal tool for a digital agency** to create, manage and export
professional business documents (invoices, quotations, proposals, etc.). It mimics
the agency's editorial brand (cream paper, near-black ink, orange-red accent #C04C20,
Poppins + IBM Plex Mono, mono numbered labels, dark pill buttons) and uses a shared
invoice-template design system for all generated documents.

Rules baked in: never use the words "freelancer"/"solo"; no hard-coded client data
(everything comes from Settings + user input); NDA / Service Agreement / SOW carry a
"have a lawyer review" note.

## 2. Current status
- Fully working MVP, verified by the testing agent across 4 iterations (backend 23/23
  pytest; frontend E2E 100%).
- Default currency = **INR (₹)** with correct Indian digit grouping (multi-currency supported).
- Invoices paginate for A4/Letter with repeated table headers, uncut rows, "Page X of Y",
  and a redesigned bottom section (Billing note + right-aligned totals + big TOTAL DUE +
  payment details/terms + footer). The top "amount due" was intentionally removed (no duplication).

## 3. Tech stack & architecture
- **Frontend**: React 19 (CRA via **craco** — use **yarn**, never npm), Tailwind + shadcn/ui,
  react-router 7, axios (`withCredentials`), sonner toasts. App has its own cream/dark theme.
- **Backend**: FastAPI + Motor (MongoDB). JWT auth in **httpOnly cookies** (SameSite=None, Secure),
  single admin seeded from env. Server-side PDF via **Playwright headless Chromium**; DOCX via python-docx.
- **DB**: MongoDB (local `mongodb://localhost:27017`, db `test_database`).
- All backend routes are under **`/api`**. Frontend calls `${REACT_APP_BACKEND_URL}/api`.
- Services run under **supervisor** (`backend` on :8001, `frontend` on :3000). Restart:
  `sudo supervisorctl restart backend frontend`.

## 4. File map
Backend (`/app/backend`):
- `server.py` — FastAPI app, all routes, startup seed + indexes, dashboard, exports, recurring.
- `auth.py` — bcrypt hashing, JWT access/refresh, cookie helpers, `seed_admin` (idempotent; resets admin password to match `ADMIN_PASSWORD` on boot).
- `models.py` — Pydantic models (PyObjectId/BaseDocument, BusinessProfile, ClientIn, DocumentIn/Update, PackageIn). Default currency INR.
- `renderer.py` — currency formatting (`fmt_money`, Indian grouping), `compute_totals`, `TYPE_META`, and `render_document()` → full print-ready HTML per type (financial / content / letterhead), light + dark. Print CSS: `@page` size, `thead{display:table-header-group}`, `tr{break-inside:avoid}` for pagination.
- `docdata.py` — `build_default_data()` prefills a new doc from profile + client; per-type content sections; `default_line_items()`.
- `pdf_export.py` — `html_to_pdf()` reuses ONE Chromium instance (memory-safe flags `--no-sandbox --disable-dev-shm-usage --disable-gpu`), adds page-number footer + A4/Letter margins. `shutdown()` closes it.
- `docx_export.py` — `build_docx()` basic Word export.
- `requirements.txt` — full frozen set (has Emergent-only pkgs; use for Emergent only).
- `requirements-deploy.txt` — lean set for external hosting.
- `Dockerfile` — backend image for Railway/Render/Cloud Run/Koyeb (installs Chromium).
- `.env` — committed (see §6).

Frontend (`/app/frontend/src`):
- `App.js` — routes + AuthProvider + ThemeProvider + Protected wrapper.
- `context/AuthContext.js`, `context/ThemeContext.js`.
- `lib/api.js` (axios, `withCredentials`), `lib/format.js` (CURRENCIES [INR first], `money()`, DOC_TYPES, STATUS_META, fmtDate).
- `components/Layout.js` (sidebar + topbar + Cmd/Ctrl+K), `components/CommandPalette.js`,
  `components/DocumentCanvas.js` (THE inline-editable document, forwardRef with `collect()`/`addLineItem()`/`addSection()`; DOM-scrape on save; live totals).
- `styles/document.css` — on-screen canvas CSS mirroring the print template (`.doc-light`/`.doc-dark`).
- `pages/`: Login, Dashboard, Clients, ClientDetail, Settings, DocumentsList, NewDocument, DocumentEditor, ShareView.
- `vercel.json` — frontend deploy config (SPA rewrites).

Docs at `/app`: `HANDOFF.md` (this), `REIMPORT.md`, `DEPLOY.md`, `memory/PRD.md`, `auth_testing.md`.

## 5. Credentials
- Admin: `bxibichvzpd@indogmail.com` / `Agency@Studio2026` (from `backend/.env`; change via `ADMIN_PASSWORD` + restart).

## 6. Environment variables
Backend `/app/backend/.env` (COMMITTED, so keys persist across re-imports — keep repo private):
`MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `FRONTEND_URL`, `PLAYWRIGHT_BROWSERS_PATH=/pw-browsers`.
Frontend `/app/frontend/.env` (NOT committed): `REACT_APP_BACKEND_URL` — must be each environment's own URL.
See `REIMPORT.md` for the new-account procedure.

## 7. Data model (MongoDB collections)
- `users` — admin (email, password_hash, role).
- `profile` — singleton (`_id:"singleton"`): agency name, logo_url, tagline, address, email, phone, website, legal_name, tax_ids, bank details, upi, payment_links, default_currency, default_terms, default_notes, `prefixes` (per-type numbering).
- `clients` — name, company, address, email, phone, tax_id, currency, notes.
- `documents` — type, number, status, client_id/name, theme (light/dark), currency, `data` (all editable text incl. `sections` for content docs, `billing_note`), `line_items[{description,sub,qty,rate}]`, `discount`/`tax` {enabled,mode(percent|fixed),value,label}, `recurring`, `share_token`, `paid_date`, timestamps.
- `packages` — saved reusable line items.
- `counters` — per-type auto-increment for numbering.

## 8. Document types (12) & conversions
invoice, quotation, receipt (financial layout) · proposal, statement_of_work, service_agreement, nda, project_status, maintenance_plan, welcome_doc, thank_you_doc (content layout) · letterhead.
Each: light + dark variant. One-click conversions: quotation→invoice, proposal→statement_of_work, invoice→receipt. Duplicate any. Mark-paid on invoice auto-creates a receipt.

## 9. Key API endpoints (all under /api)
- Auth: `POST /auth/login`, `GET /auth/me`, `POST /auth/logout`, `POST /auth/refresh`.
- Profile: `GET/PUT /profile`.
- Clients: `GET/POST /clients`, `GET/PUT/DELETE /clients/{id}`, `GET /clients/{id}/documents`.
- Documents: `GET/POST /documents`, `GET/PUT/DELETE /documents/{id}`, `POST /documents/{id}/status|duplicate|convert|mark-paid|share`, `GET /documents/{id}/pdf?size=A4|Letter`, `GET /documents/{id}/docx`.
- Share (public): `GET /share/{token}`, `GET /share/{token}/pdf`.
- Packages: `GET/POST /packages`, `DELETE /packages/{id}`.
- Dashboard: `GET /dashboard`. Recurring: `POST /recurring/run`. Exports: `GET /export/documents.csv|.json`, `/export/clients.csv`. Meta: `GET /meta/types`.

## 10. Gotchas / notes for the next agent
- **Screenshot tool + cookie auth**: the screenshot tool re-navigates to `page_url` for its own capture, so it can't show authenticated pages for this cookie-auth app (you'll just see /login). Use the **testing_agent** for authed UI flows, or curl with a cookie jar for backend.
- **PDF layout is tuned tightly for A4/Letter** — if you add rows/spacing to the financial template, re-check single-page vs multi-page by rendering the PDF (pymupdf to PNG). Changes must be mirrored in BOTH `renderer.py` (print) and `styles/document.css` (screen).
- **Playwright browsers** live at `/pw-browsers` (env `PLAYWRIGHT_BROWSERS_PATH`); run `playwright install chromium` after a fresh import.
- Single-admin app (no self-signup yet). Auth is an integration — route any auth change through `integration_expert`.
- Content-doc layout = editable `sections` (label/heading/body); financial = line items + discount/tax + billing note.

## 11. Deployment
See `DEPLOY.md`. Summary: frontend→Vercel, backend→Cloud Run/Koyeb/Railway (needs the Dockerfile for Chromium), DB→MongoDB Atlas. Or use Emergent's one-click **Deploy** for the whole stack. Cross-domain splits require exact `CORS_ORIGINS` (not `*`) because of cookie auth.

## 12. Backlog / suggested next features
- Total-block spacing polish; subtle table row tint; running "Invoice # · Client" header + "continued" note on pages 2+; amount-in-words + GSTIN/HSN columns.
- Self-service signup / multiple team accounts (with per-user data scoping) — pending user decision.
- Emergent-managed Google sign-in (was requested, then paused).
- Online payments (Stripe/Razorpay "Pay now"), e-signatures, client portal, richer reports.
- Email delivery (Resend) for "send by email" (currently share-link + download/print only).
