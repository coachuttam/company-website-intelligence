"""Tests for wi.crawl.js_fallback (CRL-04 / B-16) and its wiring into
wi.crawl.fetch.crawl_site. Fully offline: crawl_site's js_renderer is injected as a fake,
never the real Playwright-backed render_with_playwright.
"""
from __future__ import annotations

import httpx

from wi.crawl.fetch import crawl_site
from wi.crawl.js_fallback import needs_fallback, render_with_playwright, visible_text_length

BASE_CONFIG = {
    "crawl": {
        "max_depth": 1,
        "max_pages": 5,
        "request_timeout_s": 10,
        "total_budget_s": 120,
        "rate_limit_rps": 1000,
        "max_raw_bytes": 2_000_000,
        "max_clean_chars": 12000,
        "max_redirects": 5,
        "respect_robots": True,
        "js_fallback_min_text_chars": 50,
    }
}

JS_SHELL_HTML = '<html><body><div id="root"></div><script src="bundle.js"></script></body></html>'
RENDERED_HTML = "<html><body><h1>Real Co</h1><p>" + ("We build things. " * 10) + "</p></body></html>"


def test_visible_text_length_ignores_scripts_and_styles():
    html = "<html><head><style>.a{}</style></head><body><script>x=1</script>Hello world</body></html>"
    assert visible_text_length(html) == len("Hello world")


def test_needs_fallback_true_for_thin_content():
    assert needs_fallback(JS_SHELL_HTML, min_text_chars=50) is True


def test_needs_fallback_false_for_substantial_content():
    assert needs_fallback(RENDERED_HTML, min_text_chars=50) is False


def test_needs_fallback_true_when_html_is_missing():
    assert needs_fallback(None, min_text_chars=50) is True


# Regression for a real bug found on darwinbox.com (2026-09-26): visible_text_length() used to
# strip only script/style/noscript, diverging from wi/crawl/clean.py's own fallback text
# extraction (which also strips nav/header/footer) despite its docstring claiming they matched.
# A nav/footer-heavy SPA shell -- global nav, cookie banner, footer links -- easily has more
# raw boilerplate text than the DEFAULT_MIN_TEXT_CHARS=200 threshold, even when the real
# extractable content is minimal, so the fallback silently never triggered on exactly the kind
# of page CRL-04 asks it to catch.
NAV_HEAVY_JS_SHELL_HTML = (
    "<html><body>"
    "<nav>Home About Products Pricing Careers Blog Contact Sign In Book a Demo</nav>"
    "<header>Darwinbox HR Technology Suite For Growing Businesses</header>"
    '<div id="root"></div><script src="bundle.js"></script>'
    "<footer>Company Product Resources Legal Privacy Policy Terms of Service "
    "Copyright 2026 All rights reserved Follow us on LinkedIn Twitter Facebook</footer>"
    "</body></html>"
)


def test_visible_text_length_ignores_nav_header_and_footer():
    # Matches clean.py's extract_fallback_text() exactly -- only the empty #root div and the
    # script tag sit outside nav/header/footer, so real visible text is 0.
    assert visible_text_length(NAV_HEAVY_JS_SHELL_HTML) == 0


def test_needs_fallback_true_for_nav_heavy_js_shell_at_default_threshold():
    # Before the fix, the raw nav+header+footer boilerplate text alone was well over 200
    # characters, so needs_fallback() returned False here and the fallback never fired.
    assert needs_fallback(NAV_HEAVY_JS_SHELL_HTML) is True


def test_render_with_playwright_returns_none_when_playwright_not_installed(monkeypatch):
    # This project deliberately keeps playwright commented out in requirements-optional.txt
    # until someone opts in -- render_with_playwright must degrade gracefully, not raise,
    # when the import fails.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api" or name.startswith("playwright"):
            raise ImportError("no playwright here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert render_with_playwright("https://example.com/") is None


def _fake_playwright_module(fake_page, fake_timeout_error):
    """Shared scaffolding for the render_with_playwright tests below: a fake
    playwright.sync_api module whose chromium.launch().new_page() returns the given fake page
    object, wired up exactly the way builtins.__import__ hands back a fromlist module."""
    import types

    class FakeBrowser:
        def new_page(self):
            return fake_page

        def close(self):
            pass

    class FakePlaywrightContext:
        def __enter__(self):
            return types.SimpleNamespace(
                chromium=types.SimpleNamespace(launch=lambda: FakeBrowser())
            )

        def __exit__(self, *args):
            return False

    return types.SimpleNamespace(
        sync_playwright=lambda: FakePlaywrightContext(),
        TimeoutError=fake_timeout_error,
    )


def _patch_playwright_import(monkeypatch, fake_module):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "playwright.sync_api":
            return fake_module
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_render_with_playwright_still_returns_content_when_load_and_networkidle_time_out(monkeypatch):
    # Regression for a real bug found live on darwinbox.com right after B-31 made
    # needs_fallback() correctly trigger the fallback: the fallback then fired, but still
    # produced no improvement, because render_with_playwright required full networkidle and
    # that single wait timing out (a page with a chat widget or analytics beacons that never
    # go quiet) discarded an already fully-loaded page (B-32). domcontentloaded is now the
    # only required step; a later "load"/"networkidle" timeout is best-effort and must not
    # lose the already-rendered content.
    class FakeTimeoutError(Exception):
        pass

    class FakePage:
        def goto(self, url, timeout=None, wait_until=None):
            assert wait_until == "domcontentloaded"  # the required step now

        def wait_for_load_state(self, state, timeout=None):
            raise FakeTimeoutError(f"{state} never reached")

        def content(self):
            return "<html><body>real rendered content</body></html>"

    _patch_playwright_import(monkeypatch, _fake_playwright_module(FakePage(), FakeTimeoutError))

    result = render_with_playwright("https://darwinbox.com/", timeout_s=1.0)
    assert result == "<html><body>real rendered content</body></html>"


def test_render_with_playwright_returns_content_even_when_load_event_never_fires(monkeypatch):
    # Regression for a second, real bug found immediately after B-32 on the same
    # darwinbox.com/cortex page: even with a bumped 30s timeout, `page.goto(...,
    # wait_until="load")` never fired at all -- "load" waits on EVERY subresource (images,
    # fonts, tracking/chat-widget scripts), and just one hung request (very common with
    # anti-automation heuristics reacting to headless Chromium) blocks it forever regardless
    # of the timeout. domcontentloaded -- the document itself is parsed, DOM exists -- is what
    # CRL-04 actually needs, so it's now the only required wait; "load" is demoted to a
    # best-effort follow-up exactly like "networkidle" already was (B-32), and a timeout on it
    # must still return the content already on the page rather than None.
    class FakeTimeoutError(Exception):
        pass

    class FakePage:
        def goto(self, url, timeout=None, wait_until=None):
            assert wait_until == "domcontentloaded"

        def wait_for_load_state(self, state, timeout=None):
            if state == "load":
                raise FakeTimeoutError("load never fired -- a subresource hung")
            # networkidle is never reached either in this scenario (see B-33's fix: a "load"
            # timeout stops trying further best-effort waits rather than waiting out a second
            # full timeout for no benefit), so this branch existing at all would be a bug.
            raise AssertionError(f"unexpected wait_for_load_state({state!r}) call")

        def content(self):
            return "<html><body>partially rendered but real content</body></html>"

    _patch_playwright_import(monkeypatch, _fake_playwright_module(FakePage(), FakeTimeoutError))

    result = render_with_playwright("https://darwinbox.com/cortex", timeout_s=1.0)
    assert result == "<html><body>partially rendered but real content</body></html>"


def test_render_with_playwright_returns_none_when_domcontentloaded_itself_fails(monkeypatch):
    # A genuine navigation failure (DNS, connection refused, browser crash) is not the
    # best-effort-wait cases above -- it must still fall through to None, never raise.
    class FakePage:
        def goto(self, url, timeout=None, wait_until=None):
            raise RuntimeError("net::ERR_NAME_NOT_RESOLVED")

    fake_timeout_error = type("FakeTimeoutError", (Exception,), {})
    _patch_playwright_import(monkeypatch, _fake_playwright_module(FakePage(), fake_timeout_error))

    assert render_with_playwright("https://example.com/", timeout_s=1.0) is None


def test_crawl_site_never_calls_renderer_when_none_given():
    # Default behaviour (no js_renderer passed) must be identical to before this feature --
    # a JS-only page just stays as thin static content, never crashes, never renders.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=JS_SHELL_HTML)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)
    client.close()

    assert len(result.pages) == 1
    assert result.pages[0].js_rendered is False
    assert result.pages[0].html == JS_SHELL_HTML


def test_crawl_site_triggers_fallback_only_on_the_js_only_fixture():
    # Homepage is a real static page (plenty of text); /app is the JS-only shell. The
    # fallback must trigger for /app and NOT for the homepage -- CRL-04's own acceptance
    # criterion: "the fallback triggers only on the JS-only fixture."
    real_page_html = "<html><body><h1>Welcome</h1><p>" + ("Plenty of real static text. " * 5) + \
        '</p><a href="/app">App</a></body></html>'
    pages = {
        "https://example.com/": (200, real_page_html),
        "https://example.com/app": (200, JS_SHELL_HTML),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in pages:
            status, body = pages[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    render_calls = []

    def fake_renderer(url: str, timeout_s: float):
        render_calls.append(url)
        return RENDERED_HTML

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client,
                         js_renderer=fake_renderer)
    client.close()

    assert render_calls == ["https://example.com/app"]  # never called for the real page

    by_url = {p.url: p for p in result.pages}
    assert by_url["https://example.com/"].js_rendered is False
    assert by_url["https://example.com/app"].js_rendered is True
    assert by_url["https://example.com/app"].html == RENDERED_HTML


def test_crawl_site_keeps_static_page_when_renderer_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=JS_SHELL_HTML)

    def failing_renderer(url: str, timeout_s: float):
        return None  # render_with_playwright's own contract: None on any failure

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client,
                         js_renderer=failing_renderer)
    client.close()

    assert len(result.pages) == 1
    assert result.pages[0].js_rendered is False
    assert result.pages[0].html == JS_SHELL_HTML  # original static content preserved
