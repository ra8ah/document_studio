#!/usr/bin/env python3
"""axe-core WCAG 2.x A/AA check on login, dashboard, documents list and editor (light + dark app theme).
Fails on any critical/serious violation. Dev-only: uses frontend/node_modules/axe-core.
Run: python tests/a11y_axe.py   (report -> test_reports/a11y_axe.json)"""
import json
import sys
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_autosave import ENV, APP  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
AXE = (ROOT / "frontend/node_modules/axe-core/axe.min.js").read_text()
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]


def run_axe(page):
    page.add_script_tag(content=AXE)
    return page.evaluate("(tags) => axe.run(document, { runOnly: { type: 'tag', values: tags } })", TAGS)


def main():
    s = requests.Session()
    assert s.post(f"{APP}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]}).ok
    d = s.post(f"{APP}/api/documents", json={"type": "invoice"}).json()
    report, bad = [], []
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            for theme in ("light", "dark"):
                anon = b.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
                anon.add_init_script(f"localStorage.setItem('app-theme', '{theme}')")
                ctx = b.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce")
                ctx.add_init_script(f"localStorage.setItem('app-theme', '{theme}')")
                ctx.add_cookies([{"name": c.name, "value": c.value, "url": APP} for c in s.cookies])
                pages = [("login", anon, "/login", "[data-testid=login-submit-button]"),
                         ("dashboard", ctx, "/", "h1"),
                         ("documents", ctx, "/documents", "[data-testid=doc-search-input]"),
                         ("editor", ctx, f"/documents/{d['id']}", "[data-testid=document-canvas]")]
                for name, c, path, sel in pages:
                    page = c.new_page()
                    page.goto(APP + path, wait_until="networkidle")
                    page.wait_for_selector(sel)
                    page.wait_for_timeout(600)
                    r = run_axe(page)
                    v = [{"id": x["id"], "impact": x["impact"], "help": x["help"], "nodes": len(x["nodes"]),
                          "targets": [n["target"] for n in x["nodes"][:3]]} for x in r["violations"]]
                    serious = [x for x in v if x["impact"] in ("critical", "serious")]
                    report.append({"page": name, "theme": theme, "passes": len(r["passes"]), "violations": v})
                    print(f"{'PASS' if not serious else 'FAIL'}  {name:10} {theme:5}  passes={len(r['passes'])}  "
                          f"violations={[(x['id'], x['impact'], x['nodes']) for x in v]}")
                    if serious:
                        bad.append((name, theme, serious))
                    page.close()
                anon.close()
                ctx.close()
            b.close()
    finally:
        s.delete(f"{APP}/api/documents/{d['id']}")
        s.delete(f"{APP}/api/documents/{d['id']}/permanent")
    (ROOT / "test_reports/a11y_axe.json").write_text(json.dumps(report, indent=2))
    for name, theme, ser in bad:
        for x in ser:
            print(f"  -> {name}/{theme}: {x['id']} ({x['impact']}) {x['help']} :: {x['targets']}")
    print(f"\n{'ALL OK' if not bad else f'{len(bad)} page/theme combos with critical/serious violations'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
