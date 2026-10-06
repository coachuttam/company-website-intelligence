"""JavaScript-rendering fallback for pages whose static HTML doesn't carry the real content
(PRD CRL-04, behaviour B-16): "Fetch static pages first. Use a JavaScript renderer only when
static content is insufficient, and flag the page." wi/crawl/fetch.py's httpx-only crawl is
the baseline; this module is only reached when that baseline's own cleaned text looks too
thin to be the real page -- the classic single-page-app shell, e.g.
`<div id="root"></div><script src="bundle.js"></script>`, where the actual content only
exists after JavaScript runs client-side.

(fetch.py's module docstring previously mis-cited this as "EXT-05" -- that PRD ID is actually
"keep provider and model configurable", unrelated. The real requirement is CRL-04.)

Two pieces, split the same way wi/extract/llm.py splits the ChatCompleter Protocol from
OpenAIChatCompleter:
  - needs_fallback() is pure and deterministic, with no dependency on Playwright being
    installed at all. This is what crawl_site() can check on every page, always.
  - render_with_playwright() is the actual browser automation. It imports playwright lazily,
    exactly like OpenAIChatCompleter lazily imports `openai`, so nothing in the test suite or
    the rest of the pipeline needs the package installed just to import this module. Playwright
    stays commented out in requirements-optional.txt, and config.yaml's
    crawl.js_fallback_enabled stays false, until someone opts in with
    `pip install -r requirements-optional.txt` and `playwright install chromium`.

wi/crawl/fetch.py's crawl_site() takes the renderer as an injectable callable (`js_renderer`),
exactly like wi/extract/pipeline.py's extract_claims() takes a ChatCompleter -- so tests
inject a fake renderer and never launch a real browser, and run_site.py is the one place that
decides whether to wire up the real one (only when crawl.js_fallback_enabled is true).
"""
from __future__ import annotations

import sys
from typing import Optional

from wi.crawl.clean import extract_fallback_text

DEFAULT_MIN_TEXT_CHARS = 200
DEFAULT_TIMEOUT_S = 15.0


def visible_text_length(html: str) -> int:
    """How much real, visible text this HTML carries once scripts, styles, nav, header, footer
    and noscript fallbacks are stripped.

    Fixed 2026-09-26: this used to strip only script/style/noscript itself, with a docstring
    claiming parity with wi/crawl/clean.py's fallback text extraction that the code didn't
    actually have -- a real drift bug, not just a stale comment. Found live on darwinbox.com:
    with js_fallback_enabled turned on, the fallback still never triggered, because Darwinbox's
    global nav + footer + cookie banner boilerplate alone was well over the 200-char threshold,
    even though the real cleaned content (what clean_page() actually hands the LLM) was only
    235 characters. Now delegates to clean.py's extract_fallback_text() directly instead of
    keeping a separate, driftable copy of the same tag-stripping list."""
    return len(extract_fallback_text(html))


def needs_fallback(html: Optional[str], min_text_chars: int = DEFAULT_MIN_TEXT_CHARS) -> bool:
    """True when the static fetch's own content is too thin to be the real page -- the exact
    trigger condition CRL-04 asks for ("use a JS renderer only when static content is
    insufficient"). No HTML at all (a failed fetch) always counts as insufficient."""
    if not html:
        return True
    return visible_text_length(html) < min_text_chars


def render_with_playwright(url: str, timeout_s: float = DEFAULT_TIMEOUT_S) -> Optional[str]:
    """Loads `url` in headless Chromium and returns the fully-rendered HTML, or None if
    rendering fails for any reason. Deliberately never raises: a failed fallback should leave
    the original static fetch in place (degrade gracefully, per PRD Section 9), not crash the
    crawl. Requires the `playwright` package and `playwright install chromium`; the import is
    lazy so nothing else in this codebase needs Playwright installed to run.

    Fixed 2026-09-26 (part 1), found live on darwinbox.com right after B-31 fixed
    needs_fallback() to correctly trigger this function: even triggered, the fallback still
    produced no improvement, because the single `wait_until="networkidle"` requirement
    discarded an already-rendered page whenever the site never went fully network-idle within
    timeout_s -- an ordinary occurrence on any real page with a chat widget, analytics
    beacons, or ad trackers polling forever. Changed the required step to `"load"`, with
    networkidle demoted to a best-effort follow-up wait (B-32).

    Fixed 2026-09-26 (part 2, B-33): `"load"` turned out to be too strict as well -- on a real
    re-run against darwinbox.com/cortex, `page.goto(..., wait_until="load")` still timed out
    completely, even at a bumped 30s timeout. `"load"` requires literally every subresource on
    the page (images, fonts, ad pixels, third-party tracking/chat-widget scripts) to finish;
    if even one of those hangs -- extremely common when a headless browser trips some
    anti-automation heuristic and gets a stalled/never-answered response for just that one
    request -- `"load"` never fires no matter how long the timeout is. `"domcontentloaded"`
    (fires once the HTML document itself is parsed, which is what actually determines whether
    the page navigated and its DOM -- including anything an SPA framework has rendered into it
    by then -- exists) is the step CRL-04 actually needs and is far more reliable for
    real-world scraping. `"load"` and `"networkidle"` are both now best-effort follow-up waits
    after domcontentloaded succeeds, each independently swallowing only its own timeout, so a
    render can still pick up extra hydration/settling time when the page cooperates without
    ever being torpedoed by one hung subresource. Any non-timeout failure (browser launch, a
    genuine navigation error like DNS failure) still falls through to the broad `except
    Exception` below and returns None as before, now printing the real exception to stderr
    instead of a silent None -- previously that made every render failure indistinguishable
    from "not needed" or "succeeded but no fallback benefit", which is exactly what made this
    whole chain of bugs (B-31, B-32, B-33) slow to diagnose from a live run's output alone."""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                page = browser.new_page()
                # The only wait that must actually succeed: the document parsed and its DOM
                # (including whatever an SPA framework has rendered by this point) exists.
                page.goto(url, timeout=timeout_s * 1000, wait_until="domcontentloaded")
                for state in ("load", "networkidle"):
                    try:
                        page.wait_for_load_state(state, timeout=timeout_s * 1000)
                    except PlaywrightTimeoutError:
                        break  # best-effort only -- keep whatever's already rendered
                return page.content()
            finally:
                browser.close()
    except Exception as e:
        print(f"[js_fallback] render_with_playwright failed for {url}: {e!r}", file=sys.stderr)
        return None
