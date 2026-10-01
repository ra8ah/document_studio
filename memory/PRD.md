# PRD — Agency Document Studio

## Original problem statement
Internal, premium web app for a digital agency to create, manage and export professional business documents in a few clicks. Must match the agency site's visual identity (cream/ink/accent editorial style, Poppins + IBM Plex Mono) and use the supplied invoice HTML template as the master design for all generated documents. 12 document types, each with light + dark paper variants. Never use the words "freelancer" or "solo". No hard-coded personal/client data — everything editable and DB-backed.

## User choices (gathered)
1. Branding configured later in Settings (no hard-coded name).
2. No email sending — share via private link + download/print.
3. Server-side PDF (headless Chromium) — yes.
4. DOCX export — yes.
5. Multi-currency, selectable manually (Intl formatting).

## Architecture
- **Frontend**: React 19 (CRA/craco), Tailwind + shadcn/ui, react-router 7, axios (withCredentials), sonner toasts. Cream/ink theme tokens + app dark mode. Document canvas mirrors the print template CSS for pixel-consistent inline editing (contenteditable, DOM-scrape on save).
- **Backend**: FastAPI + Motor (MongoDB). JWT httpOnly cookie auth (SameSite=None, Secure), single admin seeded from env. Server-side PDF via Playwright chromium (`PLAYWRIGHT_BROWSERS_PATH=/pw-browsers`). DOCX via python-docx. Shared Python renderer builds print-ready HTML (A4/Letter) for PDF + public share view.
- **DB collections**: users, profile (singleton), clients, documents, packages, counters, login_attempts.

## Core requirements (static)
Single admin login · Dashboard (revenue, outstanding, unpaid, overdue, recent) · 3-click doc creation · Command palette (Cmd+K) · Business profile settings (brand, contact, tax, bank, defaults, numbering prefixes) · Clients CRUD + search + client doc history · Inline-editable documents with line items, live totals, discount/tax (% or fixed), multi-currency, auto-numbering · Status tracking (draft/sent/viewed/paid/overdue/cancelled) · One-click convert (quotation→invoice, proposal→SOW, invoice→receipt) + duplicate + mark-paid→receipt · Saved packages · Recurring invoices · PDF (A4/Letter) + DOCX export · Private share links · Search/filter/sort · CSV/JSON export · Responsive + app dark mode.

## Implemented (2026-06)
- Auth (JWT cookies, admin seed), all 13 document types (financial / content / letterhead layouts), light + dark paper variants.
- 2026-06: Added **Expense Report** (13th type, financial layout, prefix EXP): relabelled Submitted to / From / Date, Purpose, Reimburse to + Notes, "Total reimbursable" block (no due date / PAID stamp). Verified: A4/Letter PDF + DOCX 200.
- Dashboard, Clients + detail, Settings (incl. packages + data export), Documents list with filters/sort, New Document flow, full Document Editor (inline edit, line items, discount/tax, currency, theme, status, export, share, duplicate, convert, mark-paid, delete), public Share view.
- Server PDF (A4 + Letter) and DOCX, CSV/JSON export, recurring draft generation, command palette.
- Verified: backend 23/23 pytest pass; frontend E2E flows 100%.

## 2026-06 (this fork)
- Editor integrity: React19 dangerouslySetInnerHTML reset bug fixed (typed text wiped on re-render), no spurious autosave on load, draft/409/reset+Undo verified (tests/e2e_autosave.py 18/18).
- Print: full-sheet paper colour (html.doc-print-<theme>), no print-dialog steps; one-click server PDF via headless Chromium rendering the frontend /print/:id route (60s print token in #fragment, 2 concurrent, 30s timeout, Page X of Y footer, filename "INV-0012 - Client.pdf"); split Download PDF menu (A4/Letter/Print…/Word). tests/print_verify.py 102/102, scripts/verify_print.py 10/10.
- Lifecycle: auto overdue (+ back to sent), activity log, soft delete + Trash (restore / permanent / 30-day purge), client delete blocked -> archive/unarchive, bulk status/trash/CSV, real command-palette search (/api/search) with Recent.
- UX: skeletons, page-break guides, transform-based zoom (editor + share), mobile read-only view, shortcuts dialog (?), prefers-color-scheme + reduced motion, PWA (manifest + static-only SW, prod only).
- A11y: aria labels, canvas role=textbox, login autocomplete/show-password/aria-live error, focus rings, AA contrast; tests/a11y_axe.py 0 violations (4 pages x light/dark).
- Backend pytest 148/148 (run with REACT_APP_BACKEND_URL exported).

## Pending owner action
- Add WEBHOOK_CRON_SECRET to backend env (agent was told not to edit backend/.env) so the hourly cron (.emergent/crons.yml -> POST /api/cron/maintenance) is authorised. Overdue/purge also run at startup and on reads.
- Production: FRONTEND_URL = Vercel domain; backend on a Docker host (Render/Railway) for Chromium.

## Backlog / next
- P1: Client portal, online payments (Stripe), e-signatures, richer reports/analytics.
- P2: Email delivery (Resend), logo file upload to object storage, per-type template customization UI, saved document themes.

## Test credentials
See /app/memory/test_credentials.md — admin bxibichvzpd@indogmail.com / Agency@Studio2026.
