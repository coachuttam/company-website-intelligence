"""PDF export for the profile page (B-108): prints the rendered HTML with headless Chromium.

Playwright is optional (requirements-optional.txt, then `playwright install chromium`), so it is
imported only inside write_pdf: the HTML renderer keeps working without it. The page is loaded
from a string with network access blocked, so nothing external is fetched while printing.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_PAGE = re.compile(rb"/Type\s*/Page(?![A-Za-z])")


def count_pdf_pages(data: bytes) -> int:
    """Number of page objects in a PDF file's bytes (Chromium writes them uncompressed)."""
    return len(_PAGE.findall(data))


def write_pdf(page_html: str, out_path: Any) -> int:
    """Print `page_html` to `out_path` (A4, print stylesheet, light colours). Returns the page
    count. Raises RuntimeError when Playwright or its Chromium is not installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("PDF export needs playwright: pip install playwright && playwright install chromium") from exc
    out = Path(out_path)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(color_scheme="light", java_script_enabled=False)
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content(page_html, wait_until="load")
            page.emulate_media(media="print", color_scheme="light")
            page.pdf(path=str(out), format="A4", print_background=True, prefer_css_page_size=True)
        finally:
            browser.close()
    return count_pdf_pages(out.read_bytes())
