#!/usr/bin/env python3
"""Print fidelity verification (dev-only).
Browser print: the editor page printed by headless Chromium with print_background=False
(= "Background graphics" unchecked) and CSS @page size, like Ctrl/Cmd+P.
Server PDF: GET /api/documents/{id}/pdf and /api/share/{token}/pdf.
Each page is rasterized with pdftoppm; 4 corners + 4 edge midpoints must equal the paper colour.
Also checks pdffonts (embedded), pdftotext (real text, Page X of Y) and page counts.
Run: python tests/print_verify.py [--browser-only|--server-only]"""
import io
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
from PIL import Image
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_autosave import ENV, APP  # noqa: E402

PAPER = {"light": (0xF2, 0xEC, 0xE0), "dark": (0x1C, 0x18, 0x15)}
TOL = 3
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}  {name}  {detail}")


def sample_pages(pdf: bytes):
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "x.pdf"
        p.write_bytes(pdf)
        subprocess.run(["pdftoppm", "-r", "40", "-png", str(p), str(Path(t) / "pg")], check=True)
        pages = []
        for f in sorted(Path(t).glob("pg-*.png")):
            im = Image.open(f).convert("RGB")
            w, h = im.size
            pts = {"TL": (1, 1), "TR": (w - 2, 1), "BL": (1, h - 2), "BR": (w - 2, h - 2),
                   "T": (w // 2, 1), "B": (w // 2, h - 2), "L": (1, h // 2), "R": (w - 2, h // 2)}
            pages.append({k: im.getpixel(v) for k, v in pts.items()})
        return pages


def pdf_info(pdf: bytes):
    with tempfile.TemporaryDirectory() as t:
        p = Path(t) / "x.pdf"
        p.write_bytes(pdf)
        fonts = subprocess.run(["pdffonts", str(p)], capture_output=True, text=True).stdout
        text = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, text=True).stdout
        info = subprocess.run(["pdfinfo", str(p)], capture_output=True, text=True).stdout
    pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    rows = [ln.split() for ln in fonts.splitlines()[2:] if ln.strip()]
    # pdffonts columns: name type encoding emb sub uni object ID  -> 'emb' is the 4th from the end
    embedded = all(r[-5] == "yes" for r in rows) if rows else False
    return pages, rows, embedded, text


def verify(label, pdf, theme, expect_pages=None, expect_footer=False):
    pages = sample_pages(pdf)
    want = PAPER[theme]
    bad = [(i + 1, k, v) for i, pg in enumerate(pages) for k, v in pg.items()
           if any(abs(a - b) > TOL for a, b in zip(v, want))]
    for i, pg in enumerate(pages):
        print(f"      p{i + 1}: " + " ".join(f"{k}={'#%02X%02X%02X' % v}" for k, v in pg.items()))
    check(f"{label}: all 8 edge points on {len(pages)} page(s) == paper #{'%02X%02X%02X' % want}", not bad, str(bad[:4]))
    n, fonts, embedded, text = pdf_info(pdf)
    check(f"{label}: fonts embedded ({', '.join(sorted({r[0].split('+')[-1] for r in fonts}))})", embedded)
    check(f"{label}: real text extractable", "TEST_PRINT_CLIENT" in text)
    if expect_pages:
        check(f"{label}: page count {n} {expect_pages[0]}..{expect_pages[1]}", expect_pages[0] <= n <= expect_pages[1])
    if expect_footer:
        found = [i for i in range(1, n + 1) if re.search(rf"PAGE\s*{i}\s*OF\s*{n}\b", text, re.I)]
        check(f"{label}: 'Page X of Y' footer on every page", len(found) == n, f"found={found} pages={n}")
    return n


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    s = requests.Session()
    assert s.post(f"{APP}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]}).ok
    made = []
    try:
        cases = []
        for theme in ("light", "dark"):
            for n_items, pages in ((1, (1, 1)), (15, (2, 3)), (60, (3, 6))):
                d = s.post(f"{APP}/api/documents", json={"type": "invoice"}).json()
                made.append(d["id"])
                items = [{"description": f"Service line {i + 1}", "sub": "Detail text", "qty": 1, "rate": 100 + i} for i in range(n_items)]
                s.put(f"{APP}/api/documents/{d['id']}", json={"theme": theme, "line_items": items,
                                                               "data": {"bill_to_name": "TEST_PRINT_CLIENT"}})
                cases.append((d, theme, n_items, pages))
        if mode != "--server-only":
            print("\n== Browser print (Chromium, background graphics OFF, CSS @page) ==")
            with sync_playwright() as p:
                b = p.chromium.launch()
                ctx = b.new_context(viewport={"width": 1440, "height": 900})
                ctx.add_cookies([{"name": c.name, "value": c.value, "url": APP} for c in s.cookies])
                page = ctx.new_page()
                for d, theme, n_items, pages in cases:
                    # "frame" = the Firefox/Safari layout (@page margin 0 + repeating spacer rows), forced in Chromium
                    for size, pm in (("A4", "paged"), ("Letter", "paged"), ("A4", "frame")):
                        if (size == "Letter" or pm == "frame") and n_items != 15:
                            continue
                        page.goto(f"{APP}/documents/{d['id']}?printmode={pm}", wait_until="networkidle")
                        if size == "Letter":
                            page.click("[data-testid=page-size-select]")
                            page.click("[data-testid=page-size-letter]")
                        page.wait_for_selector("[data-testid=document-canvas]")
                        page.evaluate("document.fonts.ready")
                        page.wait_for_timeout(400)
                        pdf = page.pdf(prefer_css_page_size=True, print_background=False)
                        verify(f"print[{pm}] {theme} {size} {n_items} items", pdf, theme, pages)
                b.close()
        if mode != "--browser-only":
            print("\n== Server PDF (GET /api/documents/{id}/pdf) ==")
            for d, theme, n_items, pages in cases:
                for size in ("A4", "Letter"):
                    if size == "Letter" and n_items != 15:
                        continue
                    r = s.get(f"{APP}/api/documents/{d['id']}/pdf", params={"size": size}, timeout=60)
                    check(f"server {theme} {size} {n_items}: 200 application/pdf", r.status_code == 200 and r.content[:4] == b"%PDF", f"{r.status_code} {r.text[:120] if r.status_code != 200 else ''}")
                    if r.status_code == 200:
                        cd = r.headers.get("content-disposition", "")
                        check(f"server {theme} {size} {n_items}: filename", d["number"] in cd and "filename*=UTF-8''" in cd, cd)
                        verify(f"server {theme} {size} {n_items} items", r.content, theme, pages, expect_footer=True)
            d = cases[0][0]
            tok = s.post(f"{APP}/api/documents/{d['id']}/share").json()["token"]
            r = requests.get(f"{APP}/api/share/{tok}/pdf", timeout=60)
            check("share PDF: 200 application/pdf (no auth)", r.status_code == 200 and r.content[:4] == b"%PDF", str(r.status_code))
            if r.status_code == 200:
                verify("share light A4", r.content, "light", (1, 1), expect_footer=True)
    finally:
        for i in made:
            s.delete(f"{APP}/api/documents/{i}")
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed" + (f"; FAILED: {failed}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
