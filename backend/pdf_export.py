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
            footer = (
                "<div style=\"width:100%;font-size:8px;font-family:'IBM Plex Mono',monospace;"
                "color:#78746C;text-align:center;padding:2px 16mm 0;\">"
                "Page <span class=\"pageNumber\"></span> of <span class=\"totalPages\"></span></div>"
            )
            pdf = await page.pdf(
                format=fmt,
                print_background=True,
                prefer_css_page_size=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=footer,
                margin={"top": "14mm", "bottom": "16mm", "left": "16mm", "right": "16mm"},
            )
            return pdf
        finally:
            await browser.close()
