# Deploy: Vercel (frontend) + Docker backend on Render or Railway + MongoDB Atlas

```
browser ──► https://<app>.vercel.app ──┬── /*      static React build (Vercel CDN)
                                       └── /api/*  rewrite (server-side proxy) ──► https://<backend-host>/api/*
                                                                                        │
                                                                                 MongoDB Atlas
```

The browser only ever talks to the Vercel domain. `/api` is proxied by Vercel, so the auth cookies
are **first-party** (`SameSite=Lax; Secure; HttpOnly; Path=/`). That keeps sessions working across
reloads in Chrome, Safari (ITP) and Firefox (Total Cookie Protection), with no third-party cookies.

## 1. Database: MongoDB Atlas

Follow **DATABASE.md §1–2**: create the cluster and users, then migrate the existing data with the
dry-run-first script. Note the URI and the database name (e.g. `document_studio`).

## 2. Backend: Docker on Render or Railway

The image is `backend/Dockerfile`: `python:3.11-slim`, installs **only** `requirements-deploy.txt`,
runs as the unprivileged user `app`, listens on `$PORT`, and has no browser or Chromium.
Its health check is **`GET /api/health`** (200 = API up and MongoDB reachable).

### Render
1. New → **Web Service** → connect the repo, or **Blueprint**, which reads `render.yaml`.
2. Runtime **Docker**, Root Directory **`backend`**, Dockerfile path `./Dockerfile`.
3. Health Check Path **`/api/health`**.
4. Add the environment variables from §4. Render injects `PORT`.
5. Deploy, then `curl https://<service>.onrender.com/api/health` should return `{"status":"ok","database":"ok"}`.
   The free tier sleeps when idle, and the first request after a sleep can take ~30–60 s, which can
   hit Vercel's proxy timeout. Use a paid instance for production.

### Railway
1. New Project → Deploy from GitHub repo → service settings → **Root Directory `backend`**.
   Railway detects the Dockerfile.
2. Settings → Deploy → **Healthcheck Path `/api/health`**.
3. Variables: add everything from §4. Railway injects `PORT`.
4. Settings → Networking → **Generate Domain**, then check `/api/health` as above.

## 3. Frontend: Vercel

1. In **`frontend/vercel.json`**, replace `REPLACE-WITH-BACKEND-HOST` in the **first** rewrite with
   your backend host (e.g. `document-studio-api.onrender.com`) and commit. Rule order matters:
   `/api/(.*)` must stay first; the SPA fallback `/(.*) → /index.html` comes second.
   The install step refuses to build while the placeholder is still there.
2. Vercel → Add New Project → import the repo → **Root Directory = `frontend`**.
   Framework preset "Create React App" or "Other". `vercel.json` already sets:
   - install: `node scripts/prepare-vercel-install.js && yarn install`. This drops the Emergent-only
     `@emergentbase/*` dev tooling for this build, because yarn 1 aborts the whole install if any
     tarball (even an optional one) fails to download.
   - build: `yarn build && node scripts/check-build.js`. The check fails the deploy if the built
     `index.html` contains Emergent assets, analytics or inline scripts.
3. Environment variables: leave **`REACT_APP_BACKEND_URL` unset** (or empty), so the app calls the
   relative `/api`. Nothing else is needed on Vercel.
4. Deploy, then set the backend's `CORS_ORIGINS` to the final Vercel URL(s) (§4) and redeploy the backend.

### Security headers (set in `frontend/vercel.json`)
- `Content-Security-Policy`: `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
  img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self';
  form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests`.
  - Fonts are self-hosted and the production build has no inline scripts (`INLINE_RUNTIME_CHUNK=false`
    is forced in `craco.config.js`).
  - `'unsafe-inline'` is for **styles only**: React `style` attributes and the runtime `@page` print
    rules need it.
  - `data:` images are for uploaded logos.
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`, a restrictive `Permissions-Policy`,
  `Strict-Transport-Security: max-age=63072000; includeSubDomains` (add `preload` only if you mean it),
  `Cross-Origin-Opener-Policy: same-origin`.

## 4. Environment variables

### Backend (Render / Railway)

| Variable | Required | Example / default | Notes |
|---|---|---|---|
| `MONGO_URL` | yes | `mongodb+srv://studio_app:…@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority` | Atlas app user (readWrite) |
| `DB_NAME` | yes | `document_studio` | |
| `JWT_SECRET` | yes | 64+ random chars (`python -c "import secrets;print(secrets.token_urlsafe(64))"`) | changing it logs everyone out |
| `ADMIN_EMAIL` | yes | your login email | admin is seeded/updated at startup |
| `ADMIN_PASSWORD` | yes | a strong password | see PRE_LAUNCH_CHECKLIST.md |
| `CORS_ORIGINS` | yes | `https://<app>.vercel.app,https://studio.example.com` | comma-separated, exact origins; startup **fails** if missing or `*` |
| `COOKIE_SAMESITE` | no | `lax` (default) | `lax` with the Vercel proxy; `none` only if the browser calls the backend cross-site directly; `strict` also works |
| `MONGO_MAX_POOL_SIZE` | no | `20` | Atlas M0 allows 500 connections in total |
| `MONGO_SERVER_SELECTION_TIMEOUT_MS` | no | `5000` | |
| `PORT` | injected | — | set by Render/Railway |

### Frontend (Vercel)

| Variable | Value |
|---|---|
| `REACT_APP_BACKEND_URL` | **unset / empty**: the app calls the relative `/api` |

## 5. Smoke test after deploy

1. `curl -s https://<backend-host>/api/health` returns `{"status":"ok","database":"ok"}`.
2. `curl -sI https://<app>.vercel.app` shows the CSP, HSTS and X-Frame-Options headers.
3. Log in on the Vercel URL, then reload the page: you are still logged in. Repeat in Chrome, Safari
   and Firefox. After 60 minutes the access cookie expires; the app silently calls `/api/auth/refresh`
   (refresh cookie: 7 days) and keeps the session.
4. Create a client and an invoice, edit, save, reload, share link (open it in a private window),
   Print / Save as PDF, Word export, dashboard numbers.
5. DevTools → Application → Cookies: `access_token` / `refresh_token` on the **Vercel** domain,
   `HttpOnly`, `Secure`, `SameSite=Lax`, `Path=/`.

## 6. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Backend exits at boot with `CORS_ORIGINS is required` / `must not contain "*"` | set explicit origins (§4) |
| `/api/health` returns 503 | Atlas Network Access doesn't allow the backend's IPs, wrong URI/password (URL-encode it), or the cluster is paused |
| Vercel build fails with "first rewrite must proxy /api…" | replace `REPLACE-WITH-BACKEND-HOST` in `frontend/vercel.json` |
| Vercel build fails in `check-build` | something reintroduced inline scripts or Emergent assets into `public/index.html` outside the `emergent:dev-only` markers |
| Login works but a reload logs you out | the browser is calling the backend cross-site: keep `REACT_APP_BACKEND_URL` empty and use the `/api` rewrite |
| 504 on the first request | backend cold start (Render free tier) |
| Startup log `index documents [('number', 1)]: …duplicate key…` | legacy data has duplicate document numbers; fix them, then restart |

## 7. Backups

Atlas M0 has no backups. Set up the scheduled export in **DATABASE.md §3** and practise a restore (§4).
