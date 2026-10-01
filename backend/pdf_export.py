"""Server-side PDF: headless Chromium renders the frontend's /print/:id route (same React components + CSS
as the editor), so there is no second template that can drift. One shared browser, max N concurrent renders."""
import asyncio
import logging
import os

from playwright.async_api import async_playwright

logger = logging.getLogger("agency.pdf")

PAPER = {"light": "#F2ECE0", "dark": "#1C1815"}
MUTED = {"light": "#78746C", "dark": "#A8A29A"}
# Must equal PAGE_MARGINS in frontend/src/lib/print.js. Bottom margin hosts the "Page X of Y" footer;
# the in-page document footer lives inside the content box, so the two can never overlap.
MARGIN = {"top": "14mm", "right": "16mm", "bottom": "16mm", "left": "16mm"}
RENDER_TIMEOUT_S = float(os.environ.get("PDF_RENDER_TIMEOUT_S", "30"))
MAX_CONCURRENT = int(os.environ.get("PDF_MAX_CONCURRENT", "2"))
QUEUE_WAIT_S = 15

# memory-safe flags for small (512MB) containers
_LAUNCH_ARGS = ["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--no-zygote",
                "--disable-extensions", "--disable-background-networking", "--mute-audio"]

_pw = None
_browser = None
_launch_lock = asyncio.Lock()
_sem = asyncio.Semaphore(MAX_CONCURRENT)
_active = 0


class PdfBusy(Exception):
    pass


class PdfTimeout(Exception):
    pass


async def _get_browser():
    global _pw, _browser
    async with _launch_lock:
        if _browser is None or not _browser.is_connected():
            if _pw is None:
                _pw = await async_playwright().start()
            _browser = await _pw.chromium.launch(args=_LAUNCH_ARGS)
    return _browser


def _footer(theme: str) -> str:
    # header/footer templates can't use the page's CSS or web fonts (Chromium limitation): system mono font,
    # band painted with the paper colour
    bg, fg = PAPER[theme], MUTED[theme]
    return (
        "<style>html,body{margin:0;padding:0}</style>"
        f"<div style=\"width:100%;margin:0 0 -1px;padding:0 0 6mm;background:{bg};color:{fg};"
        "-webkit-print-color-adjust:exact;print-color-adjust:exact;"
        "font:7px 'Liberation Mono','DejaVu Sans Mono',monospace;letter-spacing:.12em;text-transform:uppercase;text-align:center;\">"
        "Page <span class=\"pageNumber\"></span> of <span class=\"totalPages\"></span></div>"
    )


async def _render(url: str, size: str, theme: str) -> bytes:
    browser = await _get_browser()
    ctx = await browser.new_context(viewport={"width": 1200, "height": 1600}, java_script_enabled=True)
    try:
        page = await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded")
        # the print route sets data-print-ready after data, fonts and images have loaded
        await page.wait_for_selector("html[data-print-ready]", state="attached")
        if await page.evaluate("document.documentElement.dataset.printReady") != "1":
            raise RuntimeError("print route failed to load the document")
        return await page.pdf(
            format="Letter" if size == "Letter" else "A4",
            print_background=True,
            prefer_css_page_size=True,
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=_footer(theme),
            margin=MARGIN,
        )
    finally:
        await ctx.close()


async def render_pdf(url: str, size: str, theme: str) -> bytes:
    """url contains a short-lived token in its #fragment: never log it."""
    global _active
    theme = "dark" if theme == "dark" else "light"
    try:
        await asyncio.wait_for(_sem.acquire(), QUEUE_WAIT_S)
    except asyncio.TimeoutError:
        raise PdfBusy()
    _active += 1
    try:
        return await asyncio.wait_for(_render(url, size, theme), RENDER_TIMEOUT_S)
    except asyncio.TimeoutError:
        raise PdfTimeout()
    finally:
        _active -= 1
        _sem.release()


def status() -> dict:
    return {"browser": "running" if (_browser is not None and _browser.is_connected()) else "idle",
            "active_renders": _active, "max_concurrent": MAX_CONCURRENT, "timeout_s": RENDER_TIMEOUT_S}


async def shutdown():
    global _pw, _browser
    try:
        if _browser is not None:
            await _browser.close()
    finally:
        _browser = None
        if _pw is not None:
            await _pw.stop()
            _pw = None
