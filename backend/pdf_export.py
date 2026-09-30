"""Server-side PDF generation using headless Chromium (Playwright)."""
from playwright.async_api import async_playwright

PAGE_FORMAT = {"A4": "A4", "Letter": "Letter"}

# Memory-safe flags so Chromium fits small (512MB) free-tier instances.
_LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
]

_pw = None
_browser = None
_lock = None


async def _get_browser():
    """Launch Chromium once and reuse it across requests (low memory)."""
    global _pw, _browser, _lock
    import asyncio
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _browser is None or not _browser.is_connected():
            if _pw is None:
                _pw = await async_playwright().start()
            _browser = await _pw.chromium.launch(args=_LAUNCH_ARGS)
    return _browser


async def html_to_pdf(html: str, page_size: str = "A4") -> bytes:
    fmt = PAGE_FORMAT.get(page_size, "A4")
    browser = await _get_browser()
    context = await browser.new_context()
    try:
        page = await context.new_page()
        await page.set_content(html, wait_until="networkidle")
        try:
            await page.evaluate("() => document.fonts && document.fonts.ready")
            await page.wait_for_timeout(300)
        except Exception:
            pass
        footer = (
            "<div style=\"width:100%;font-size:8px;font-family:'IBM Plex Mono',monospace;"
            "color:#78746C;text-align:center;padding:2px 16mm 0;\">"
            "Page <span class=\"pageNumber\"></span> of <span class=\"totalPages\"></span></div>"
        )
        return await page.pdf(
            format=fmt,
            print_background=True,
            prefer_css_page_size=True,
            display_header_footer=True,
            header_template="<span></span>",
            footer_template=footer,
            margin={"top": "14mm", "bottom": "16mm", "left": "16mm", "right": "16mm"},
        )
    finally:
        await context.close()


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
