# Deploy: Vercel (frontend) + Railway/Render (backend) + MongoDB Atlas

This app is full-stack. Vercel hosts ONLY the React frontend. The FastAPI backend
needs a real container host (it runs headless Chromium for PDF export), and MongoDB
must be hosted on Atlas.

---

## Step 1 — MongoDB Atlas (database)
1. Create a free account at https://www.mongodb.com/atlas and create a free (M0) cluster.
2. Database Access → add a user (username + password).
3. Network Access → allow access from anywhere: `0.0.0.0/0`.
4. Cluster → Connect → Drivers → copy the connection string, e.g.:
   `mongodb+srv://USER:PASSWORD@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority`
   Keep this — it is your `MONGO_URL`.

## Step 2 — Backend on Railway (recommended) or Render
The repo already contains `backend/Dockerfile` and `backend/requirements-deploy.txt`.

### Railway
1. https://railway.app → New Project → Deploy from GitHub repo → pick your repo.
2. In the service Settings → set **Root Directory** = `backend` (so it uses `backend/Dockerfile`).
3. Add environment variables (Variables tab):
   - `MONGO_URL`   = your Atlas string from Step 1
   - `DB_NAME`     = `agency_studio`  (any name you like)
   - `JWT_SECRET`  = a long random string
   - `ADMIN_EMAIL` = your login email
   - `ADMIN_PASSWORD` = your login password
   - `CORS_ORIGINS`   = your Vercel URL (fill after Step 3, e.g. `https://your-app.vercel.app`)
4. Deploy. Railway gives a public URL like `https://your-backend.up.railway.app`.
   Test it: open `https://your-backend.up.railway.app/api/dashboard` (should ask auth / return JSON error, not 404).

### Render (alternative)
1. https://render.com → New → Web Service → connect repo.
2. Root Directory = `backend`, Environment = **Docker**.
3. Add the same env vars as above. Deploy → note the `https://...onrender.com` URL.

## Step 3 — Frontend on Vercel
1. https://vercel.com → Add New → Project → import your GitHub repo.
2. Set **Root Directory** = `frontend`.  (Framework: Create React App; `vercel.json` already sets build = `yarn build`, output = `build`, and SPA rewrites.)
3. Environment Variables → add:
   - `REACT_APP_BACKEND_URL` = your backend URL from Step 2 (NO trailing slash), e.g. `https://your-backend.up.railway.app`
   > CRA embeds this at BUILD time, so it must be set before you build. If you change it later, redeploy.
4. Deploy → you get `https://your-app.vercel.app`.

## Step 4 — Wire the two domains together (important)
1. Copy your Vercel URL and set it as `CORS_ORIGINS` on the backend (Railway/Render), then redeploy the backend.
   - Must be the exact origin, e.g. `https://your-app.vercel.app` (comma-separate if multiple).
   - Do NOT use `*` here — login cookies require an exact origin when frontend and backend are on different domains.
2. Both frontend and backend are HTTPS (they are, by default) — required, because auth uses secure `SameSite=None` cookies.
3. Open your Vercel URL and log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`.

---

## Environment variables — quick reference
Backend (Railway/Render):
- `MONGO_URL`, `DB_NAME`, `JWT_SECRET`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `CORS_ORIGINS`
Frontend (Vercel):
- `REACT_APP_BACKEND_URL`

## Troubleshooting
- **Login works then "logs out" on refresh**: `CORS_ORIGINS` doesn't exactly match your Vercel URL, or one side isn't HTTPS. Fix `CORS_ORIGINS`, redeploy backend.
- **Frontend build fails on Vercel** fetching `@emergentbase/overlay` / `@emergentbase/visual-edits`: these are Emergent dev tools. If they block the build, remove those two lines from `frontend/package.json` devDependencies, commit, redeploy.
- **PDF export fails on backend**: ensure the backend host builds from `backend/Dockerfile` (Docker environment), not a plain Python buildpack — Chromium needs the Docker image's system libraries.
- **404 on page refresh (Vercel)**: the included `vercel.json` rewrites handle SPA routing; make sure Root Directory = `frontend`.

## Simpler alternative
Emergent's built-in **Deploy/Publish** button runs this exact stack (FastAPI + React +
MongoDB + Chromium) together with managed env vars and database — no Atlas/Railway setup needed.
