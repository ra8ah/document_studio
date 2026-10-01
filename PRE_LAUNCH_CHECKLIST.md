# Pre-launch checklist (deferred security items)

These were **deliberately not changed** in the Atlas / Vercel hardening work, so the current
Emergent workspace keeps working. Do all of them before real users or real client data go live.
Order matters: rotate secrets **after** cleaning the repository, so the new values never touch git.

- [ ] **Remove credentials from docs, tests and test reports.** The literal admin email and password
      currently appear in: `HANDOFF.md`, `auth_testing.md`, `memory/PRD.md`, `memory/test_credentials.md`,
      `backend/tests/backend_test.py` (and its `__pycache__/*.pyc`), and `test_reports/iteration_1..4.json`.
      Replace them with environment-variable lookups or placeholders. The newer suites
      (`backend/tests/test_print_api.py`, `test_hardening.py`) already read credentials from the environment.
- [ ] **Stop committing `backend/.env`.** Remove the `!backend/.env` exception from `.gitignore` and
      untrack the file. It is currently untracked in this workspace, but the exception would let it
      be committed again. Keep secrets only in the host's environment settings (Render/Railway,
      GitHub Actions secrets). Also add `.env` to `backend/.dockerignore` so it can never be baked
      into an image.
- [ ] **Scrub git history.** Purge every past version of `backend/.env` and of any file that held
      credentials (`git filter-repo --path backend/.env --invert-paths`, plus `--replace-text` for
      literal values, or BFG). Force-push, ask collaborators to re-clone, and invalidate forks or
      caches you control. Treat everything that was ever committed as public.
- [ ] **Rotate the admin password.** Set a new strong `ADMIN_PASSWORD` in the backend host's
      environment and redeploy. The startup seeder updates the stored hash.
- [ ] **Rotate `JWT_SECRET`.** Generate 64+ random characters and set it on the host. This logs out
      every session, which is intended.
- [ ] **Make `ADMIN_*` mandatory with no defaults.** `backend/auth.py::seed_admin` still falls back
      to built-in defaults when `ADMIN_EMAIL` / `ADMIN_PASSWORD` are unset. Fail at startup instead
      (as `CORS_ORIGINS` already does), and reject weak passwords.
- [ ] Rotate the Atlas database-user passwords if a URI was ever pasted into chat, docs or logs.
- [ ] Keep the GitHub repository private (backups, history and docs describe the system).

When all of this is done, re-run the backend suites and the smoke test in DEPLOY.md §5.
