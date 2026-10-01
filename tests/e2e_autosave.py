#!/usr/bin/env python3
"""E2E (headless Chromium) for editor autosave, draft restore, retry/"Not saved", 409, Clear & start fresh + Undo.
Dev-only. Needs: pip install playwright pymongo requests && playwright install chromium.
Credentials/URLs from env or backend/.env + frontend/.env (never printed). Cleans up and restores counters.
Run: python tests/e2e_autosave.py"""
import os
import re
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright, expect
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent


def envfile(p):
    out = {}
    if p.exists():
        for line in p.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"')
    return out


ENV = {**envfile(ROOT / "backend/.env"), **envfile(ROOT / "frontend/.env"), **os.environ}
APP = ENV["REACT_APP_BACKEND_URL"].rstrip("/")
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}  {name}{('  ' + detail) if detail and not cond else ''}")


def field(page, name):
    return page.locator(f'[data-testid=document-canvas] [data-field="{name}"]').first


def type_into(page, name, text):
    f = field(page, name)
    f.click()
    page.keyboard.press("Control+A")
    page.keyboard.type(text)


def main():
    db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
    counters = list(db.counters.find())
    s = requests.Session()
    assert s.post(f"{APP}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]}).ok
    made = []
    try:
        d = s.post(f"{APP}/api/documents", json={"type": "invoice"}).json()
        made.append(d["id"])
        url = f"{APP}/documents/{d['id']}"
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport={"width": 1440, "height": 900})
            ctx.add_cookies([{"name": c.name, "value": c.value, "url": APP} for c in s.cookies])
            page = ctx.new_page()
            status = page.locator("[data-testid=save-status]")

            # 1. refresh BEFORE autosave can land (saves blocked) -> draft restore prompt
            page.goto(url, wait_until="networkidle")
            # simulate the tab dying before autosave lands (unload save fails too)
            ctx.route(re.compile(r".*/api/documents/[0-9a-f]{24}$"), lambda r: r.abort() if r.request.method == "PUT" else r.continue_())
            type_into(page, "bill_to_name", "Draft Corp")
            page.wait_for_timeout(300)
            ctx.clear_cookies()  # keepalive/unload saves bypass route interception: make them fail with 401
            page.close()
            ctx.add_cookies([{"name": c.name, "value": c.value, "url": APP} for c in s.cookies])
            ctx.unroute(re.compile(r".*/api/documents/[0-9a-f]{24}$"))
            page = ctx.new_page()
            status = page.locator("[data-testid=save-status]")
            page.goto(url, wait_until="networkidle")
            dlg = page.locator("[data-testid=draft-restore-dialog]")
            check("draft prompt shown after refresh", dlg.is_visible())
            check("server copy untouched before restore", "Draft Corp" not in field(page, "bill_to_name").inner_text())
            page.click("[data-testid=draft-restore]")
            check("draft restored into canvas", field(page, "bill_to_name").inner_text() == "Draft Corp", repr(field(page, "bill_to_name").inner_text()))
            expect(status).to_have_attribute("data-state", "saved", timeout=10000)
            srv = s.get(f"{APP}/api/documents/{d['id']}").json()
            check("restored draft autosaved to server", srv["data"]["bill_to_name"] == "Draft Corp")

            # 2. type, wait for autosave, refresh -> persists, no prompt
            type_into(page, "bill_to_name", "Persist Ltd")
            expect(status).to_have_attribute("data-state", "saved", timeout=10000)
            check("status text 'Saved · just now'", "Saved · just now" in status.inner_text())
            page.reload(wait_until="networkidle")
            check("autosaved content persists after refresh", field(page, "bill_to_name").inner_text() == "Persist Ltd")
            check("no draft prompt when nothing unsaved", not page.locator("[data-testid=draft-restore-dialog]").is_visible())
            data = s.get(f"{APP}/api/documents/{d['id']}").json()["data"]
            check("hidden fields kept after saves", all(k in data for k in ("label", "reference_label", "logo_url")) and data["label"] == "Invoice")

            # 3. network failure -> retries -> "Not saved" + Retry; then recovers
            calls = {"n": 0}

            def fail(route):
                if route.request.method == "PUT":
                    calls["n"] += 1
                    return route.abort("internetdisconnected")
                return route.continue_()
            page.route(re.compile(r".*/api/documents/[0-9a-f]{24}$"), fail)
            type_into(page, "bill_to_name", "Offline Inc")
            expect(status).to_have_attribute("data-state", "saving", timeout=5000)
            expect(status).to_have_attribute("data-state", "error", timeout=20000)
            check("retried with backoff (5 attempts)", calls["n"] == 5, f"attempts={calls['n']}")
            check("'Not saved' + Retry visible", "Not saved" in status.inner_text() and page.locator("[data-testid=save-retry]").is_visible())
            page.unroute(re.compile(r".*/api/documents/[0-9a-f]{24}$"))
            page.click("[data-testid=save-retry]")
            expect(status).to_have_attribute("data-state", "saved", timeout=10000)
            check("Retry saves once back online", s.get(f"{APP}/api/documents/{d['id']}").json()["data"]["bill_to_name"] == "Offline Inc")

            # 4. stale tab -> 409 dialog -> Reload
            s.put(f"{APP}/api/documents/{d['id']}", json={"data": {"bill_to_name": "Other Tab"}})
            type_into(page, "bill_to_name", "Stale Edit")
            page.wait_for_selector("[data-testid=conflict-dialog]", timeout=10000)
            check("409 shows 'changed elsewhere' dialog", page.locator("[data-testid=conflict-dialog]").is_visible())
            page.click("[data-testid=conflict-reload]")
            page.wait_for_timeout(1500)
            check("Reload shows the other tab's version", field(page, "bill_to_name").inner_text() == "Other Tab")

            # 5. Clear & start fresh (blank) -> Undo
            page.click("[data-testid=reset-button]")
            page.click("[data-testid=reset-blank]")
            page.wait_for_timeout(800)
            check("blank reset empties content", field(page, "bill_to_name").inner_text().strip() == "")
            check("number kept after reset", page.locator("[data-testid=doc-number]").inner_text() == d["number"])
            page.get_by_role("button", name="Undo").click()
            page.wait_for_timeout(1200)
            check("Undo restores previous content", field(page, "bill_to_name").inner_text() == "Other Tab")
            srv = s.get(f"{APP}/api/documents/{d['id']}").json()
            check("Undo persisted on server", srv["data"]["bill_to_name"] == "Other Tab" and srv["number"] == d["number"])

            # 6. delete uses AlertDialog (no window.confirm)
            page.click("[data-testid=more-menu]")
            page.click("[data-testid=delete-doc]")
            check("delete opens AlertDialog", page.locator("[data-testid=delete-dialog]").is_visible())
            page.keyboard.press("Escape")
            b.close()
    finally:
        for i in made:
            s.delete(f"{APP}/api/documents/{i}")
        db.counters.delete_many({})
        if counters:
            db.counters.insert_many(counters)
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f"; FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
