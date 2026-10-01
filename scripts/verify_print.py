#!/usr/bin/env python3
"""
DEV-ONLY print verification for the client-side "Print / Save as PDF" flow.

Not part of the backend image or its requirements. Needs, on the dev machine only:
    pip install playwright pymongo requests && playwright install chromium
    apt-get install poppler-utils            # pdftotext, pdffonts, pdfimages, pdfinfo, pdftoppm

What it does
  1. Creates throw-away documents through the API (invoice x1 / x15 / x60 line items,
     a multi-page proposal, a dark-theme invoice, an INR invoice with Indian grouping,
     a US Letter invoice). Number counters are snapshotted and restored afterwards,
     and every created document is deleted, so real numbering is not consumed.
  2. Opens each one in the real app (editor, or the public share page), clicks
     "Print / Save as PDF" -> "Open print dialog" (window.print is stubbed so we can
     check fonts + images were ready at the moment it was called), then prints the
     same page with headless Chromium's print engine (= "Save as PDF", background
     graphics on, headers/footers off, CSS page size).
  3. Checks every PDF: vector text (pdftotext), embedded fonts (pdffonts), no raster
     pages (pdfimages), page size, repeated table headers, unsplit rows, totals +
     payment kept together, signature block kept together, page numbers, nothing
     outside the 14/16/16/16 mm margins, and full-bleed paper colour on every edge.

Configuration (env vars): APP_URL (default: REACT_APP_BACKEND_URL from frontend/.env),
VERIFY_EMAIL / VERIFY_PASSWORD (default: read from backend/.env; never printed),
MONGO_URL / DB_NAME (default: backend/.env), OUT_DIR (default /tmp/print-verify).
"""
import base64
import io
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import requests
from PIL import Image
from playwright.sync_api import sync_playwright
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("OUT_DIR", "/tmp/print-verify"))
OUT.mkdir(parents=True, exist_ok=True)


def read_env(path):
    vals = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip().strip('"').strip("'")
    return vals


BENV = read_env(ROOT / "backend/.env")
FENV = read_env(ROOT / "frontend/.env")
APP = os.environ.get("APP_URL") or FENV.get("REACT_APP_BACKEND_URL")
EMAIL = os.environ.get("VERIFY_EMAIL") or BENV.get("ADMIN_EMAIL")
PASSWORD = os.environ.get("VERIFY_PASSWORD") or BENV.get("ADMIN_PASSWORD")
MONGO_URL = os.environ.get("MONGO_URL") or BENV.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or BENV.get("DB_NAME")

MM = 72 / 25.4
MARGIN = {"top": 14 * MM, "right": 16 * MM, "bottom": 16 * MM, "left": 16 * MM}
TOL = 1.5 * MM
PAPER = {"light": (0xF2, 0xEC, 0xE0), "dark": (0x1C, 0x18, 0x15)}
SIZES = {"A4": (595.28, 841.89), "Letter": (612.0, 792.0)}

SVG_LOGO = ("<svg xmlns='http://www.w3.org/2000/svg' width='300' height='80' viewBox='0 0 300 80'>"
            "<circle cx='40' cy='40' r='30' fill='#E0673B'/>"
            "<rect x='85' y='25' width='190' height='30' rx='15' fill='#F2ECE0'/></svg>")
SVG_URI = "data:image/svg+xml;base64," + base64.b64encode(SVG_LOGO.encode()).decode()


def png_logo_uri():
    im = Image.new("RGB", (1200, 300), (192, 76, 32))
    for x in range(0, 1200, 40):
        for y in range(300):
            im.putpixel((x, y), (32, 28, 24))
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


# ------------------------------------------------------------------ API helpers
class Api:
    def __init__(self):
        self.s = requests.Session()
        r = self.s.post(f"{APP}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
        r.raise_for_status()
        self.created = []

    def make(self, dtype, *, theme="light", currency="INR", page_size="A4", items=None,
             data=None, discount=None, tax=None):
        d = self.s.post(f"{APP}/api/documents", json={"type": dtype, "theme": theme, "currency": currency}, timeout=30).json()
        self.created.append(d["id"])
        body = {"data": {**d["data"], **(data or {})}, "currency": currency, "theme": theme, "page_size": page_size}
        if items is not None:
            body["line_items"] = items
        if discount:
            body["discount"] = discount
        if tax:
            body["tax"] = tax
        r = self.s.put(f"{APP}/api/documents/{d['id']}", json=body, timeout=30)
        r.raise_for_status()
        return r.json()

    def share(self, did):
        return self.s.post(f"{APP}/api/documents/{did}/share", timeout=30).json()["token"]

    def cleanup(self):
        for did in self.created:
            self.s.delete(f"{APP}/api/documents/{did}", timeout=30)


def items(n, rate=1500.0):
    return [{"description": f"Line item {i:02d}", "sub": f"Detail {i:02d} scope notes", "qty": 1 + (i % 3), "rate": rate + i}
            for i in range(1, n + 1)]


PROPOSAL_TEXT = (
    "We will plan, design and build the work in short, reviewable iterations. Each iteration ends with a "
    "working preview, a written summary of decisions, and a list of open questions for your team. "
    "Scope changes are captured in writing and estimated before work begins, so budget and timeline stay "
    "predictable. Accessibility, performance and search visibility are treated as acceptance criteria rather "
    "than afterthoughts, and every deliverable is documented so your team can maintain it confidently. "
)


# ------------------------------------------------------------------ PDF analysis
def pdf_pages(path):
    info = run(["pdfinfo", str(path)])
    pages = int(re.search(r"Pages:\s+(\d+)", info).group(1))
    w, h = map(float, re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", info).groups())
    return pages, w, h


def page_text(path, p):
    return run(["pdftotext", "-f", str(p), "-l", str(p), "-layout", str(path), "-"])


def page_words(path):
    xml = run(["pdftotext", "-bbox", str(path), "-"])
    pages = []
    for pg in re.findall(r"<page[^>]*>(.*?)</page>", xml, re.S):
        words = [(float(a), float(b), float(c), float(d), t) for a, b, c, d, t in
                 re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', pg)]
        pages.append(words)
    return pages


def fonts(path):
    out = run(["pdffonts", str(path)]).splitlines()[2:]
    res = []
    for line in out:
        parts = line.split()
        if not parts:
            continue
        # name type... emb sub uni object ID
        res.append({"name": parts[0], "emb": parts[-5], "sub": parts[-4]})
    return res


def images(path):
    out = run(["pdfimages", "-list", str(path)]).splitlines()[2:]
    res = []
    for line in out:
        p = line.split()
        if len(p) > 4:
            res.append({"page": int(p[0]), "w": int(p[3]), "h": int(p[4])})
    return res


def squash(t):
    """pdftotext inserts spaces at kerning/letter-spacing gaps ("Line it em 01"); compare without whitespace."""
    return re.sub(r"\s+", "", t)


def edge_colors(path, pages, theme):
    """Rasterise each page (low dpi, for the check only) and test every edge pixel."""
    want = PAPER[theme]
    bad = []
    prefix = OUT / (path.stem + "-edge")
    subprocess.run(["pdftoppm", "-r", "24", "-png", str(path), str(prefix)], check=True)
    for p in range(1, pages + 1):
        cand = sorted(OUT.glob(f"{prefix.name}-*{p}.png"))
        f = [c for c in cand if int(re.search(r"-(\d+)\.png$", c.name).group(1)) == p][0]
        im = Image.open(f).convert("RGB")
        # crop to the exact page area: pdftoppm rounds the bitmap up, so a fractional last
        # column/row (e.g. 594.96pt -> 198.3px) lies outside the page and is always white
        _, pw, ph = pdf_pages(path)
        im = im.crop((0, 0, int(pw * 24 / 72), int(ph * 24 / 72)))
        w, h = im.size
        edge = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
        off = [im.getpixel(xy) for xy in edge if max(abs(a - b) for a, b in zip(im.getpixel(xy), want)) > 12]
        if off:
            bad.append({"page": p, "off_pixels": len(off), "sample": off[0]})
        f.unlink()
    return bad


def analyse(path, spec):
    r = {"file": str(path), "checks": {}, "ok": True}

    def check(name, ok, detail=None):
        r["checks"][name] = {"ok": bool(ok), **({"detail": detail} if detail is not None else {})}
        if not ok:
            r["ok"] = False

    pages, w, h = pdf_pages(path)
    r["pages"] = pages
    ew, eh = SIZES[spec["size"]]
    check("page_size", abs(w - ew) < 1.5 and abs(h - eh) < 1.5, f"{w:.1f}x{h:.1f}pt (want {spec['size']})")
    if "pages" in spec:
        lo, hi = spec["pages"]
        check("page_count", lo <= pages <= hi, f"{pages} (expected {lo}-{hi})")

    texts = [squash(page_text(path, p)) for p in range(1, pages + 1)]
    full = "\n".join(texts)
    check("real_text", len(full.strip()) > 200 and spec["must_contain"][0] in full, f"{len(full)} chars extracted")
    for s in spec["must_contain"]:
        check(f"text:{s}", squash(s) in full)

    fl = fonts(path)
    names = sorted({f["name"].split("+")[-1] for f in fl})
    check("fonts_embedded", fl and all(f["emb"] == "yes" for f in fl), names)
    check("fonts_only_brand", all(("Poppins" in n or "IBMPlexMono" in n) for n in names), names)

    imgs = images(path)
    exp_imgs = spec.get("images", [])
    check("vector_no_raster_pages", len(imgs) == len(exp_imgs) and all(
        any(i["w"] == e[0] and i["h"] == e[1] for i in imgs) for e in exp_imgs), imgs)

    n = spec.get("items", 0)
    if n:
        found = [sum(t.count(f"Lineitem{i:02d}") for t in texts) for i in range(1, n + 1)]
        check("every_row_once", all(c == 1 for c in found), [i + 1 for i, c in enumerate(found) if c != 1] or "all present")
        split = [i for i in range(1, n + 1)
                 if not any(f"Lineitem{i:02d}" in t and f"Detail{i:02d}" in t for t in texts)]
        check("rows_not_split", not split, split or "none split")
        hdr = [p + 1 for p, t in enumerate(texts) if "Lineitem" in t and "DESCRIPTION" not in t]
        check("header_repeats_on_item_pages", not hdr, hdr or f"header on all {sum('Lineitem' in t for t in texts)} item page(s)")

    for group in spec.get("together", []):
        pg = [p + 1 for p, t in enumerate(texts) if all(squash(g) in t for g in group)]
        check("together:" + "+".join(group), bool(pg), pg)

    # the last page must carry real content, not just the footer line / page number
    last = re.sub(r"PAGE\d+OF\d+", "", texts[-1]).replace(squash("Thank you for working with us."), "")
    check("no_orphaned_footer_page", len(last) > 20, f"{len(last)} chars of content on last page")

    if spec["mode"] == "paged":
        nums = [f"PAGE{p}OF{pages}" in texts[p - 1] for p in range(1, pages + 1)]
        check("page_numbers", all(nums), nums)

    # nothing outside the margins (page numbers live in the bottom margin by design)
    words = page_words(path)
    left, right = MARGIN["left"] - TOL, w - MARGIN["right"] + TOL
    top, bottom = MARGIN["top"] - TOL, h - MARGIN["bottom"] + TOL
    out = []
    maxx = 0
    for p, ws in enumerate(words, 1):
        for x0, y0, x1, y1, t in ws:
            if y0 > bottom and re.fullmatch(r"PAGE|OF|\d+", t):
                continue
            if x0 < left or x1 > right or y0 < top or y1 > bottom or x0 < 0 or x1 > w:
                out.append((p, t, round(x0 / MM, 1), round(y0 / MM, 1), round(x1 / MM, 1), round(y1 / MM, 1)))
            if p == 1:
                maxx = max(maxx, x1)
    check("nothing_clipped_or_outside_margins", not out, out[:6] or "all words inside 14/16/16/16mm box")
    # full-width layout (proves no zoom/transform leaked into print)
    check("full_width_layout", abs(maxx - (w - MARGIN["right"])) < 3 * MM, f"rightmost glyph at {maxx / MM:.1f}mm of {w / MM:.1f}mm")

    bad = edge_colors(path, pages, spec["theme"])
    check("full_bleed_paper_all_edges", not bad, bad or f"{spec['theme']} paper on every edge of {pages} page(s)")
    return r


# ------------------------------------------------------------------ main
def main():
    for t in ("pdftotext", "pdffonts", "pdfimages", "pdfinfo", "pdftoppm"):
        subprocess.run(["which", t], check=True, capture_output=True)
    mongo = MongoClient(MONGO_URL)[DB_NAME]
    counters = list(mongo.counters.find())
    api = Api()
    results = []
    try:
        png_uri = png_logo_uri()
        inv1 = api.make("invoice", items=items(1))
        inv15 = api.make("invoice", items=items(15))
        inv60 = api.make("invoice", items=items(60))
        letter = api.make("invoice", items=items(15), page_size="Letter", currency="USD")
        dark = api.make("invoice", theme="dark", items=items(25), data={"logo_url": SVG_URI})
        inr = api.make("invoice", currency="INR", items=[
            {"description": "Line item 01", "sub": "Detail 01 platform build", "qty": 10, "rate": 1234567.89},
            {"description": "Line item 02", "sub": "Detail 02 retainer", "qty": 1, "rate": 250000},
        ], tax={"enabled": True, "mode": "percent", "value": 18, "label": "GST"}, data={"logo_url": png_uri})
        sections = [{"label": f"{i:02d}", "heading": f"Section heading {i:02d}", "body": PROPOSAL_TEXT * 2} for i in range(1, 11)]
        proposal = api.make("proposal", items=items(6), data={"sections": sections})
        dark_token = api.share(dark["id"])

        fin_together = [["BILLING NOTE", "SUBTOTAL", "TOTAL DUE", "PAYMENT DETAILS", "PAYMENT TERMS"]]
        cases = [
            ("invoice-1-item", f"/documents/{inv1['id']}", {"items": 1, "pages": (1, 1), "together": fin_together}),
            ("invoice-15-items", f"/documents/{inv15['id']}", {"items": 15, "pages": (1, 2), "together": fin_together}),
            ("invoice-60-items", f"/documents/{inv60['id']}", {"items": 60, "pages": (3, 5), "together": fin_together}),
            ("invoice-letter-usd", f"/documents/{letter['id']}", {"items": 15, "size": "Letter", "pages": (1, 2), "together": fin_together,
                                                                   "must_contain": ["Invoice", "$"]}),
            ("invoice-dark-share-narrow", f"/share/{dark_token}", {"items": 25, "theme": "dark", "pages": (2, 3), "together": fin_together,
                                                                    "viewport": (600, 900)}),
            ("invoice-inr-grouping", f"/documents/{inr['id']}", {"items": 2, "pages": (1, 1), "together": fin_together,
                                                                   "images": [(1200, 300)],
                                                                   "must_contain": ["Invoice", "₹1,23,45,678.90", "₹2,50,000.00", "GST"]}),
            ("proposal-multipage", f"/documents/{proposal['id']}", {"items": 6, "pages": (3, 6),
                                                                    "together": [["Service Provider — signature", "Client — signature"]],
                                                                    "must_contain": ["Proposal", "Section heading 10"]}),
        ]
        frame_cases = {"invoice-60-items", "invoice-dark-share-narrow", "proposal-multipage"}

        with sync_playwright() as p:
            browser = p.chromium.launch()
            ctx = browser.new_context()
            # share the API session cookie with the browser
            for c in api.s.cookies:
                ctx.add_cookies([{"name": c.name, "value": c.value, "url": APP}])
            for name, path, spec in cases:
                for mode in ("auto", "frame") if name in frame_cases else ("auto",):
                    spec = {"size": "A4", "theme": "light", "must_contain": ["Invoice"], **spec}
                    vw, vh = spec.get("viewport", (1280, 900))
                    page = ctx.new_page()
                    page.set_viewport_size({"width": vw, "height": vh})
                    font_reqs, foreign = [], []

                    def on_req(req):
                        u = req.url
                        if req.resource_type == "font" or re.search(r"\.(woff2?|ttf|otf)(\?|$)", u):
                            font_reqs.append(u)
                        if not u.startswith(APP) and not u.startswith("data:"):
                            foreign.append(u)
                    page.on("request", on_req)
                    url = APP + path + ("?printmode=frame" if mode == "frame" else "")
                    page.goto(url, wait_until="networkidle")
                    page.wait_for_selector("[data-testid=document-canvas]")
                    page.evaluate("""() => { window.__printCall = null; window.print = () => {
                        const imgs = [...document.querySelectorAll('[data-print-target] img')];
                        window.__printCall = { fonts: document.fonts.status,
                          loaded: [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family + ' ' + f.weight),
                          imgs: imgs.every(i => i.complete && i.naturalWidth > 0), nimgs: imgs.length,
                          mode: document.documentElement.dataset.printMode }; }; }""")
                    t0 = time.time()
                    page.click("[data-testid=print-button]")
                    page.click("[data-testid=print-confirm]")
                    page.wait_for_function("window.__printCall !== null", timeout=15000)
                    call = page.evaluate("window.__printCall")
                    pdf = OUT / f"{name}{'-frame' if mode == 'frame' else ''}.pdf"
                    page.pdf(path=str(pdf), print_background=True, prefer_css_page_size=True)
                    real_mode = "frame" if mode == "frame" else call["mode"]
                    r = analyse(pdf, {**spec, "mode": real_mode})
                    r["name"] = pdf.stem
                    r["print_mode"] = real_mode
                    ok_ready = call["fonts"] == "loaded" and call["imgs"] and len(set(call["loaded"])) >= 7
                    r["checks"]["fonts_and_images_ready_before_print"] = {"ok": ok_ready, "detail": {
                        "fonts_status": call["fonts"], "faces_loaded": sorted(set(call["loaded"])), "images": call["nimgs"],
                        "ms_to_print": int((time.time() - t0) * 1000)}}
                    self_hosted = all("/fonts/" in u and u.startswith(APP) for u in font_reqs)
                    r["checks"]["fonts_self_hosted_no_external_requests"] = {
                        "ok": self_hosted and not any(re.search(r"fonts\.(googleapis|gstatic)", u) for u in foreign),
                        "detail": {"font_requests": len(font_reqs), "external_font_requests": [u for u in foreign if "font" in u]}}
                    if mode == "auto":
                        r["checks"]["chromium_auto_selects_paged_mode"] = {"ok": call["mode"] == "paged", "detail": call["mode"]}
                    r["ok"] = all(c["ok"] for c in r["checks"].values())
                    if name == "invoice-dark-share-narrow" and mode == "auto":
                        # same page, "Background graphics" left OFF: print-color-adjust:exact must still paint
                        pdf2 = OUT / f"{name}-no-bg-option.pdf"
                        page.pdf(path=str(pdf2), print_background=False, prefer_css_page_size=True)
                        n2, _, _ = pdf_pages(pdf2)
                        bad = edge_colors(pdf2, n2, "dark")
                        r["checks"]["dark_without_background_graphics_option"] = {
                            "ok": True, "informational": True,
                            "detail": "full bleed" if not bad else f"edges not painted on {len(bad)} page(s) -> users must enable Background graphics"}
                    # previews for human review
                    subprocess.run(["pdftoppm", "-r", "50", "-png", "-f", "1", "-l", "2", str(pdf), str(OUT / f"{pdf.stem}-preview")], check=True)
                    results.append(r)
                    page.close()
            browser.close()
    finally:
        api.cleanup()
        mongo.counters.delete_many({})
        if counters:
            mongo.counters.insert_many(counters)

    report = {"app": APP, "generated": time.strftime("%Y-%m-%d %H:%M:%S"), "all_ok": all(r["ok"] for r in results), "results": results}
    (ROOT / "test_reports").mkdir(exist_ok=True)
    (ROOT / "test_reports/print_verification.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    for r in results:
        fails = [k for k, v in r["checks"].items() if not v["ok"]]
        print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['name']:<34} mode={r['print_mode']:<5} pages={r['pages']:<2} "
              f"checks={len(r['checks'])}{'  failed=' + ','.join(fails) if fails else ''}")
    print("ALL OK" if report["all_ok"] else "FAILURES", "-> test_reports/print_verification.json ; PDFs in", OUT)
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
