"""Server-side PDF generation using headless Chromium (Playwright)."""
from playwright.async_api import async_playwright

PAGE_FORMAT = {"A4": "A4", "Letter": "Letter"}


async def html_to_pdf(html: str, page_size: str = "A4") -> bytes:
    fmt = PAGE_FORMAT.get(page_size, "A4")
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
        try:
            page = await browser.new_page()
            await page.set_content(html, wait_until="networkidle")
            try:
                await page.evaluate("() => document.fonts && document.fonts.ready")
                await page.wait_for_timeout(300)
            except Exception:
                pass
            pdf = await page.pdf(
                format=fmt,
                print_background=True,
                prefer_css_page_size=True,
                margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
            )
            return pdf
        finally:
            await browser.close()
