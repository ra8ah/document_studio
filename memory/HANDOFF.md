# Handoff notes (keep updated every session)

## State (2026-06)
- Editor autosave/draft/409/reset/undo: DONE. `python tests/e2e_autosave.py` -> 18/18.
- Backend: `cd backend && REACT_APP_BACKEND_URL=<frontend/.env value> python -m pytest tests -q -n0` -> 122/122.
  (Without REACT_APP_BACKEND_URL exported the tests hit http://localhost:8001 and Secure cookies are dropped -> mass 401s.)

## Root causes fixed this session
1. React 19 re-applies `dangerouslySetInnerHTML` on EVERY render (new object) -> typed text in canvas fields was wiped
   whenever the editor re-rendered (e.g. save status change). Fix: `Editable` in DocumentCanvas.js sets innerHTML once
   in useLayoutEffect on mount; editor remounts canvas via `canvasKey` when content must be replaced. NEVER go back to
   dangerouslySetInnerHTML for contentEditable fields.
2. Spurious autosave on load (StrictMode double effects fired canvas onChange on mount). Fix: canvas structural effect
   uses identity check of rows/sections; editor markDirty treats the first snapshot after (re)mount as the baseline.
3. Draft prompt shown even when the unload keepalive save landed: on load, draft equal to server content is discarded silently.
4. Status change now flushes pending edits first (status bumps updated_at -> would cause false 409).

## Testing gotchas
- Playwright cannot intercept/offline-block `fetch(keepalive)` sent during unload; e2e simulates a dead tab by
  clearing cookies before page.close() so the unload save gets 401.
- Overlay `fixed inset-0 bg-black/80` in e2e = the draft-restore AlertDialog (was opening because of bug 2).

## Rules
- Never use window.confirm; use AlertDialog. Document number is not editable on canvas; server ignores data.number (PROTECTED_DATA_KEYS).
- Dashboard: never sum currencies; backend returns *_by_currency, headline = default currency.
