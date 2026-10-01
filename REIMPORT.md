# Re-importing this project into a NEW Emergent account

The goal: the new account should reuse the SAME admin login and JWT secret
(so it does NOT generate new ones), while still using the new environment's
own database URL and preview URL.

## What carries over automatically
`backend/.env` IS committed to the repo (we added a `!backend/.env` exception in
`.gitignore`). It contains the keys that must stay the same:

- `JWT_SECRET`        — keep identical so tokens/logins stay consistent
- `ADMIN_EMAIL`       — your admin login email
- `ADMIN_PASSWORD`    — your admin login password
- `CORS_ORIGINS`, `FRONTEND_URL`
- `MONGO_URL=mongodb://localhost:27017`, `DB_NAME` — standard local Mongo (same on every Emergent pod)
- `PLAYWRIGHT_BROWSERS_PATH=/pw-browsers`

Because these are in the committed `backend/.env`, the new account's backend
starts up, re-seeds the SAME admin (the startup seeder just matches the hash to
`ADMIN_PASSWORD`), and you log in with the same credentials. No new secret is created.

## What you MUST set fresh in the new account
- `frontend/.env` → `REACT_APP_BACKEND_URL` must be the NEW account's preview URL.
  (This file is intentionally NOT committed, so it won't overwrite the new URL.)
  The Emergent template normally provides this automatically.

## First-run steps on the new account
1. Import the GitHub repo.
2. Backend deps + Chromium for PDF export:
   `cd /app/backend && pip install -r requirements.txt && playwright install chromium`
   (or `pip install -r requirements-deploy.txt` for the lean set)
3. Frontend deps: `cd /app/frontend && yarn install`
4. Restart services: `sudo supervisorctl restart backend frontend`
5. Log in with the same `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `backend/.env`.

## SECURITY WARNING
`backend/.env` now contains real secrets (JWT secret + admin password) in the
repo. KEEP THE GITHUB REPOSITORY PRIVATE. If it is ever public, rotate
`JWT_SECRET` and `ADMIN_PASSWORD` immediately.
