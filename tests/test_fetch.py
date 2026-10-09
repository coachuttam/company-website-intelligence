"""Tests for wi.crawl.fetch. Fully offline: httpx.MockTransport stands in for
the network so these never depend on, or hit, a live site.
"""
from __future__ import annotations

import httpx

from wi.crawl.fetch import (
    CrawlResult,
    FetchResult,
    RobotsGate,
    _is_crawlable_content_type,
    crawl_diagnostics,
    crawl_site,
    extract_links,
    fetch_page,
    is_other_locale_url,
    locale_language,
)

BASE_CONFIG = {
    "crawl": {
        "max_depth": 2,
        "max_pages": 25,
        "request_timeout_s": 10,
        "total_budget_s": 120,
        "rate_limit_rps": 1000,  # fast for tests
        "max_raw_bytes": 2_000_000,
        "max_clean_chars": 12000,
        "max_redirects": 5,
        "respect_robots": True,
    }
}

PAGES = {
    "https://example.com/robots.txt": (
        200,
        "User-agent: *\nDisallow: /private/\n",
    ),
    "https://example.com/": (
        200,
        '<html><head><title>Example Home</title></head><body>'
        '<a href="/about">About</a> <a href="/private/secret">Secret</a> '
        '<a href="https://other.com/x">Other domain</a> '
        '<a href="mailto:hi@example.com">Mail</a>'
        '</body></html>',
    ),
    "https://example.com/about": (
        200,
        '<html><head><title>About</title></head><body>About us text.</body></html>',
    ),
    "https://example.com/private/secret": (
        200,
        "<html><body>Should never be fetched.</body></html>",
    ),
}


def make_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in PAGES:
            status, body = PAGES[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True, max_redirects=5)


def test_robots_gate_blocks_disallowed_path():
    with make_client() as client:
        gate = RobotsGate(client)
        assert gate.can_fetch("https://example.com/about") is True
        assert gate.can_fetch("https://example.com/private/secret") is False


def test_robots_gate_allows_all_when_no_robots_txt():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="no robots here")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        gate = RobotsGate(client)
        assert gate.can_fetch("https://nobots.example/anything") is True


def test_extract_links_same_domain_only():
    html = PAGES["https://example.com/"][1]
    links = extract_links(html, "https://example.com/", ["example.com"])
    assert "https://example.com/about" in links
    assert "https://example.com/private/secret" in links
    assert not any("other.com" in link for link in links)
    assert not any(link.startswith("mailto:") for link in links)


def test_fetch_page_truncates_at_max_raw_bytes():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="x" * 1000)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_page(client, "https://big.example/", max_raw_bytes=100, timeout_s=5)
        assert result.status == "ok"
        assert result.truncated is True
        assert len(result.html) <= 100


def test_fetch_page_reports_http_error_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_page(client, "https://down.example/", max_raw_bytes=1000, timeout_s=5)
        assert result.status == "error"
        assert result.status_code == 500


def test_fetch_page_reports_redirect_limit_exceeded():
    # Always redirect to a new URL -- with max_redirects=2 this chain never resolves, so
    # httpx raises TooManyRedirects. Before this fix that was caught by the generic
    # `except httpx.HTTPError` and looked identical to a DNS failure or a timeout.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": str(request.url) + "x"})

    with httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True,
                       max_redirects=2) as client:
        result = fetch_page(client, "https://redirect.example/", max_raw_bytes=1000, timeout_s=5)
        assert result.status == "error"
        assert result.error_code == "REDIRECT_LIMIT_EXCEEDED"


def test_fetch_page_other_http_errors_get_no_redirect_error_code():
    # A plain connection failure must NOT be mistaken for a redirect-cap breach.
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_page(client, "https://down.example/", max_raw_bytes=1000, timeout_s=5)
        assert result.status == "error"
        assert result.error_code is None


def test_crawl_site_reports_redirect_limit_and_continues_to_other_pages():
    # The redirect-looping page's OWN fetch is reported with the specific error code, but the
    # crawl as a whole degrades gracefully and still fetches the other queued page (Section 9:
    # "Timeout: skip the page, log it, continue with partial data" -- same philosophy applies
    # to a capped-out redirect chain).
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://example.com/":
            return httpx.Response(
                200,
                text='<html><body><a href="/loop">Loop</a> <a href="/about">About</a></body></html>',
            )
        if url == "https://example.com/about":
            return httpx.Response(200, text="<html><body>About us.</body></html>")
        # /loop and everything downstream of it just keeps redirecting forever.
        return httpx.Response(302, headers={"Location": url + "x"})

    config = {**BASE_CONFIG, "crawl": {**BASE_CONFIG["crawl"], "max_redirects": 2, "max_pages": 5}}
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True, max_redirects=2)
    result = crawl_site("https://example.com/", ["example.com"], config, client=client)
    client.close()

    by_url = {p.url: p for p in result.pages}
    assert by_url["https://example.com/loop"].error_code == "REDIRECT_LIMIT_EXCEEDED"
    assert by_url["https://example.com/about"].status == "ok"


def test_crawl_site_respects_robots_and_stays_same_domain():
    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in PAGES:
            status, body = PAGES[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True, max_redirects=5)
    result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)
    client.close()

    fetched_urls = {p.url for p in result.pages}
    assert "https://example.com/" in fetched_urls
    assert "https://example.com/about" in fetched_urls
    assert "https://example.com/private/secret" not in fetched_urls
    assert "https://example.com/private/secret" in result.skipped_by_robots
    assert not any("other.com" in u for u in fetched_urls)


def test_crawl_site_respects_max_pages():
    # A page that always links to itself under a new query-free path would loop forever
    # without max_pages; here we just confirm the cap is honoured on a small fixture.
    config = {**BASE_CONFIG, "crawl": {**BASE_CONFIG["crawl"], "max_pages": 1}}

    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in PAGES:
            status, body = PAGES[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("https://example.com/", ["example.com"], config, client=client)
    client.close()

    assert len(result.pages) == 1


def test_crawl_site_holds_the_cap_on_a_10000_page_site():
    # B-14, taken literally rather than approximated on a 4-page fixture: a homepage that
    # discovers 10,000 links in one shot (a real large marketing site's sitemap-in-a-footer)
    # must still never push len(result.pages) past max_pages. This exercises the actual
    # priority-heap queue at the scale the behaviour names, not just the cap variable itself.
    n_pages = 10_000
    homepage_links = "".join(f'<a href="/page-{i}">Page {i}</a>' for i in range(n_pages))
    homepage_html = f"<html><body>{homepage_links}</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://example.com/":
            return httpx.Response(200, text=homepage_html)
        if url.startswith("https://example.com/page-"):
            return httpx.Response(200, text=f"<html><body>{url}</body></html>")
        return httpx.Response(404, text="not found")

    config = {
        "crawl": {
            "max_depth": 2,
            "max_pages": 25,          # PRD Section 13's real proposed default
            "request_timeout_s": 10,
            "total_budget_s": 120,
            "rate_limit_rps": 1000,   # fast for tests -- real-run rate limiting is covered
                                      # separately, this test is about the page cap only
            "max_raw_bytes": 2_000_000,
            "max_clean_chars": 12000,
            "max_redirects": 5,
            "respect_robots": True,
        }
    }
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("https://example.com/", ["example.com"], config, client=client)
    client.close()

    assert len(result.pages) == config["crawl"]["max_pages"]
    assert not result.budget_exhausted  # the cap tripped first, not the time budget


def test_crawl_site_preserves_document_order_when_no_priority_keywords_configured():
    # BASE_CONFIG has no priority_url_keywords -- must behave exactly like the old plain
    # FIFO crawl: homepage, then /about (the first link in document order), in that order.
    config = {**BASE_CONFIG, "crawl": {**BASE_CONFIG["crawl"], "max_pages": 2}}
    client = make_client()
    result = crawl_site("https://example.com/", ["example.com"], config, client=client)
    client.close()

    assert [p.url for p in result.pages] == [
        "https://example.com/",
        "https://example.com/about",
    ]


# --- Priority-ordered crawl (decided 2026-09-25, see wi/crawl/fetch.py's module docstring) --
# Closes the CRL-01 gap: without this, a page matching crawl.priority_url_keywords that's
# discovered later in the HTML (or one level deeper) than several low-value pages could be
# starved out of the max_pages budget entirely, even though the homepage links to it.

PRIORITY_CONFIG = {
    "crawl": {
        "max_depth": 1,
        "max_pages": 2,
        "request_timeout_s": 10,
        "total_budget_s": 120,
        "rate_limit_rps": 1000,
        "max_raw_bytes": 2_000_000,
        "max_clean_chars": 12000,
        "max_redirects": 5,
        "respect_robots": True,
        "priority_url_keywords": ["pricing"],
    }
}

PRIORITY_PAGES = {
    "https://example.com/": (
        200,
        '<html><body>'
        '<a href="/blog/post-1">Post 1</a> '
        '<a href="/blog/post-2">Post 2</a> '
        '<a href="/pricing">Pricing</a>'
        '</body></html>',
    ),
    "https://example.com/blog/post-1": (200, "<html><body>Post 1</body></html>"),
    "https://example.com/blog/post-2": (200, "<html><body>Post 2</body></html>"),
    "https://example.com/pricing": (200, "<html><body>Pricing</body></html>"),
}


def _priority_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in PRIORITY_PAGES:
            status, body = PRIORITY_PAGES[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_crawl_site_prioritises_pages_matching_priority_url_keywords():
    # Document order on the homepage lists both blog posts before /pricing, and max_pages
    # only leaves room for ONE of the three discovered links -- plain breadth-first order
    # would fetch /blog/post-1 next. It must fetch /pricing instead, since it matches
    # crawl.priority_url_keywords.
    client = _priority_client()
    result = crawl_site("https://example.com/", ["example.com"], PRIORITY_CONFIG, client=client)
    client.close()

    fetched_urls = {p.url for p in result.pages}
    assert fetched_urls == {"https://example.com/", "https://example.com/pricing"}


def test_crawl_site_priority_does_not_override_depth_ordering():
    # A priority page discovered ONE LEVEL DEEPER must still lose to a non-priority page at
    # a shallower depth -- priority only breaks ties within the same depth, it doesn't let a
    # deep page jump the whole queue and turn this into an uncontrolled crawl.
    config = {
        **PRIORITY_CONFIG,
        "crawl": {**PRIORITY_CONFIG["crawl"], "max_depth": 2, "max_pages": 2},
    }
    pages = {
        **PRIORITY_PAGES,
        "https://example.com/blog/post-1": (
            200,
            '<html><body><a href="/blog/pricing-deep">Deep pricing</a></body></html>',
        ),
        "https://example.com/blog/pricing-deep": (200, "<html><body>Deep pricing</body></html>"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in pages:
            status, body = pages[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("https://example.com/", ["example.com"], config, client=client)
    client.close()

    fetched_urls = {p.url for p in result.pages}
    # /pricing (depth 1, priority) still wins over /blog/pricing-deep (depth 2, priority)
    # and over the depth-1 blog posts -- depth 1 + priority beats everything else here.
    assert fetched_urls == {"https://example.com/", "https://example.com/pricing"}


# --- Duplicate-page dedup (decided 2026-09-26, closes CLN-01 / B-15) --------------------

def test_normalize_url_collapses_trailing_slash():
    from wi.crawl.fetch import _normalize_url

    assert _normalize_url("https://example.com/products/") == "https://example.com/products"
    assert _normalize_url("https://example.com/products") == "https://example.com/products"
    # root path is left alone, never collapsed to an empty path
    assert _normalize_url("https://example.com/") == "https://example.com/"
    assert _normalize_url("https://example.com") == "https://example.com/"


def test_extract_links_collapses_trailing_slash_duplicates():
    html = (
        '<a href="/products">Products</a> '
        '<a href="/products/">Products (again)</a>'
    )
    links = extract_links(html, "https://example.com/", ["example.com"])
    assert links == ["https://example.com/products"]


def test_crawl_site_treats_trailing_slash_variant_as_the_same_page():
    # The homepage links to BOTH "/products" and "/products/" -- CLN-01's own example of a
    # duplicate. Only one fetch for it should ever happen.
    pages = {
        "https://example.com/": (
            200,
            '<html><body>'
            '<a href="/products">Products</a> '
            '<a href="/products/">Products slash</a>'
            '</body></html>',
        ),
        "https://example.com/products": (200, "<html><body>Products page</body></html>"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in pages:
            status, body = pages[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    config = {**BASE_CONFIG, "crawl": {**BASE_CONFIG["crawl"], "max_pages": 5}}
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("https://example.com/", ["example.com"], config, client=client)
    client.close()

    fetched_urls = [p.url for p in result.pages]
    assert fetched_urls.count("https://example.com/products") == 1
    assert len(result.pages) == 2  # homepage + one products page, never two


def test_crawl_site_drops_content_duplicate_at_a_different_url():
    # /pricing and /plans are DIFFERENT normalised URLs but serve byte-identical content (a
    # mirror page) -- the URL-level check can't catch this, only the content hash can.
    identical_html = "<html><body>Same content, different path.</body></html>"
    pages = {
        "https://example.com/": (
            200,
            '<html><body><a href="/pricing">Pricing</a> <a href="/plans">Plans</a></body></html>',
        ),
        "https://example.com/pricing": (200, identical_html),
        "https://example.com/plans": (200, identical_html),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in pages:
            status, body = pages[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")

    config = {**BASE_CONFIG, "crawl": {**BASE_CONFIG["crawl"], "max_pages": 5}}
    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("https://example.com/", ["example.com"], config, client=client)
    client.close()

    fetched_urls = {p.url for p in result.pages}
    assert fetched_urls == {"https://example.com/", "https://example.com/pricing"}
    assert result.skipped_as_duplicate == ["https://example.com/plans"]


def test_is_crawlable_content_type_allows_html_and_plain_text():
    assert _is_crawlable_content_type("text/html; charset=utf-8")
    assert _is_crawlable_content_type("text/plain")
    assert _is_crawlable_content_type("application/xhtml+xml")


def test_is_crawlable_content_type_allows_missing_header():
    # Lenient default: an absent header is treated as crawlable, matching the crawler's old
    # behaviour and every existing test fixture (httpx.Response(text=...) always sets some
    # content-type, but a real misconfigured server might send none at all).
    assert _is_crawlable_content_type("")


def test_is_crawlable_content_type_blocks_binary_formats():
    # The bajajauto.com bug this fixes (decided 2026-09-26): a linked PDF was being decoded
    # as text and run through the HTML cleaner as if it were a real page.
    assert not _is_crawlable_content_type("application/pdf")
    assert not _is_crawlable_content_type("application/pdf; charset=binary")
    assert not _is_crawlable_content_type("image/png")
    assert not _is_crawlable_content_type("application/octet-stream")
    assert not _is_crawlable_content_type("application/zip")


def test_fetch_page_reports_unsupported_content_type_without_reading_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4 binary garbage", headers={"content-type": "application/pdf"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_page(client, "https://example.com/manual.pdf", max_raw_bytes=1000, timeout_s=5)
        assert result.status == "error"
        assert result.error_code == "UNSUPPORTED_CONTENT_TYPE"
        assert result.html is None


def test_crawl_site_skips_linked_pdfs_instead_of_crawling_them_as_pages():
    # Reproduces the real bajajauto.com run: a page links to a PDF; the crawler must not
    # treat it as a same-domain HTML page to fetch content from or extract further links out
    # of, and it must not count toward ok/extracted pages.
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://example.com/":
            return httpx.Response(
                200,
                text='<html><body><a href="/manual.pdf">Manual</a> <a href="/about">About</a></body></html>',
            )
        if url == "https://example.com/manual.pdf":
            return httpx.Response(200, content=b"%PDF-1.4 binary garbage",
                                   headers={"content-type": "application/pdf"})
        if url == "https://example.com/about":
            return httpx.Response(200, text="<html><body>About us.</body></html>")
        return httpx.Response(404, text="not found")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)
    client.close()

    by_url = {p.url: p for p in result.pages}
    assert by_url["https://example.com/manual.pdf"].status == "error"
    assert by_url["https://example.com/manual.pdf"].error_code == "UNSUPPORTED_CONTENT_TYPE"
    assert by_url["https://example.com/about"].status == "ok"
    ok_pages = [p for p in result.pages if p.status == "ok" and p.html]
    assert all("PDF" not in (p.html or "") for p in ok_pages)


# B-crawl-diagnostics (2026-09-27, crawl-coverage-misses investigation, see PROGRESS.md):
# run_site.py used to print exactly this information once and then discard it -- a fresh run
# was the only way to learn why a field went missing. These tests cover crawl_diagnostics()
# reshaping a CrawlResult into something that can be persisted into the run's output JSON.

def test_crawl_diagnostics_reports_ok_and_error_pages_with_full_fetch_result_detail():
    result = CrawlResult(
        start_url="https://example.com/",
        pages=[
            FetchResult(url="https://example.com/", status="ok", status_code=200,
                        html="<html>hi</html>", truncated=False, js_rendered=False),
            FetchResult(url="https://example.com/blocked", status="error", status_code=403,
                        error="Forbidden", error_code=None),
            FetchResult(url="https://example.com/rendered", status="ok", status_code=200,
                        html="<html>rendered</html>", js_rendered=True),
        ],
        skipped_by_robots=["https://example.com/admin"],
        skipped_as_duplicate=["https://example.com/mirror"],
        budget_exhausted=True,
    )

    diag = crawl_diagnostics(result)

    assert len(diag["pages"]) == 3
    ok_page = diag["pages"][0]
    assert ok_page == {
        "url": "https://example.com/",
        "status": "ok",
        "status_code": 200,
        "error": None,
        "error_code": None,
        "truncated": False,
        "js_rendered": False,
        "requested_url": None,  # B-76: only set when a redirect ended somewhere else
    }
    error_page = diag["pages"][1]
    assert error_page["status"] == "error"
    assert error_page["status_code"] == 403
    assert error_page["error"] == "Forbidden"
    assert diag["pages"][2]["js_rendered"] is True
    assert diag["skipped_by_robots"] == ["https://example.com/admin"]
    assert diag["skipped_as_duplicate"] == ["https://example.com/mirror"]
    assert diag["budget_exhausted"] is True


def test_crawl_diagnostics_on_a_real_crawl_result_is_json_serialisable_and_matches_page_count():
    # Not just a hand-built CrawlResult -- run an actual crawl_site() (offline, mocked
    # transport) so this also catches a future field added to FetchResult that crawl_diagnostics
    # forgets to carry through.
    import json

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://example.com/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")
        if url == "https://example.com/":
            return httpx.Response(200, text='<html><body><a href="/private/x">x</a></body></html>')
        return httpx.Response(404, text="not found")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)
    client.close()

    diag = crawl_diagnostics(result)
    json.dumps(diag)  # must not raise -- this is going straight into a run's output JSON
    assert len(diag["pages"]) == len(result.pages)
    assert diag["skipped_by_robots"] == result.skipped_by_robots


# --- B-60: skip other-language copies when the start URL is under an English locale prefix ---

def test_b60_locale_language_recognises_locale_segments_only():
    assert locale_language("https://s.example/en/pricing") == "en"
    assert locale_language("https://s.example/pt_br/pricing") == "pt"
    assert locale_language("https://s.example/zh-CN/x") == "zh"
    assert locale_language("https://s.example/pricing") is None
    assert locale_language("https://s.example/us/pricing") == "en"   # B-90: a country, read as English
    assert locale_language("https://s.example/") is None


def test_b60_other_locale_only_when_start_url_is_english_prefixed():
    start = "https://s.example/en"
    assert is_other_locale_url("https://s.example/ja/pricing-options", start)
    assert is_other_locale_url("https://s.example/pt_br/pricing-options", start)
    assert not is_other_locale_url("https://s.example/en/pricing-options", start)
    assert not is_other_locale_url("https://s.example/en-gb/pricing-options", start)   # English kept
    assert not is_other_locale_url("https://s.example/resource/guide", start)
    # no locale on the start URL -> never skip anything (a top-level /it/ may be IT content)
    assert not is_other_locale_url("https://s.example/it/solutions", "https://s.example/")


def _locale_site_client(pages):
    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        for cand in (key, key.rstrip("/"), key.rstrip("/") + "/"):   # bare domain: with or without "/"
            if cand in pages:
                return httpx.Response(200, text=pages[cand])
        return httpx.Response(404, text="not found")
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True, max_redirects=5)


LOCALE_PAGES = {
    "https://s.example/en": (
        '<html><body><a href="/en/pricing">P</a> <a href="/ja/pricing">JA</a> '
        '<a href="/de/pricing">DE</a> <a href="/resource/guide">G</a></body></html>'
    ),
    "https://s.example/en/pricing": "<html><body>English pricing</body></html>",
    "https://s.example/ja/pricing": "<html><body>Japanese pricing</body></html>",
    "https://s.example/de/pricing": "<html><body>German pricing</body></html>",
    "https://s.example/resource/guide": "<html><body>A guide</body></html>",
}


def test_b60_crawl_skips_other_language_pages_and_records_them():
    config = {"crawl": dict(BASE_CONFIG["crawl"], respect_robots=False)}
    with _locale_site_client(LOCALE_PAGES) as client:
        result = crawl_site("https://s.example/en/", ["s.example"], config, client=client)
    fetched = {p.url for p in result.pages}
    assert "https://s.example/en/pricing" in fetched
    assert "https://s.example/resource/guide" in fetched
    assert "https://s.example/ja/pricing" not in fetched and "https://s.example/de/pricing" not in fetched
    assert set(result.skipped_as_other_locale) == {"https://s.example/ja/pricing", "https://s.example/de/pricing"}
    assert crawl_diagnostics(result)["skipped_as_other_locale"] == result.skipped_as_other_locale


def test_b60_skip_can_be_switched_off_in_config():
    config = {"crawl": dict(BASE_CONFIG["crawl"], respect_robots=False, skip_other_locales=False)}
    with _locale_site_client(LOCALE_PAGES) as client:
        result = crawl_site("https://s.example/en/", ["s.example"], config, client=client)
    fetched = {p.url for p in result.pages}
    assert "https://s.example/ja/pricing" in fetched
    assert result.skipped_as_other_locale == []


def test_b60_start_url_without_locale_skips_nothing():
    # a bare-domain start page that never links to an /en... URL: a top-level /ja/ or /de/ here is
    # not evidence of a locale-organised site (B-69 only reacts to /en links on the start page)
    pages = dict(LOCALE_PAGES)
    pages["https://s.example"] = (
        '<html><body><a href="/pricing">P</a> <a href="/ja/pricing">JA</a> '
        '<a href="/de/pricing">DE</a> <a href="/resource/guide">G</a></body></html>'
    )
    pages.pop("https://s.example/en")
    config = {"crawl": dict(BASE_CONFIG["crawl"], respect_robots=False)}
    with _locale_site_client(pages) as client:
        result = crawl_site("https://s.example/", ["s.example"], config, client=client)
    assert result.skipped_as_other_locale == []


# ---- B-65: failed fetches (404/403) do not use up the page budget ------------------------------
def _site_with_dead_links(n_dead, n_live):
    links = "".join(f'<a href="/dead-{i}">d{i}</a>' for i in range(n_dead))
    links += "".join(f'<a href="/live-{i}">l{i}</a>' for i in range(n_live))
    home = f"<html><body>{links}</body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == "https://example.com/":
            return httpx.Response(200, text=home)
        if "/live-" in url:
            return httpx.Response(200, text=f"<html><body>{url}</body></html>")
        return httpx.Response(404, text="nope")

    return httpx.Client(transport=httpx.MockTransport(handler))


def _cfg(**over):
    crawl = {**BASE_CONFIG["crawl"], "max_pages": 5, "respect_robots": False,
             "priority_url_keywords": ["dead"]}   # dead links are dequeued first, as on loom.com
    crawl.update(over)
    return {"crawl": crawl}


def test_b65_dead_links_do_not_use_up_the_page_budget():
    client = _site_with_dead_links(n_dead=4, n_live=10)
    result = crawl_site("https://example.com/", ["example.com"], _cfg(), client=client)
    ok = [p for p in result.pages if p.status == "ok"]
    assert len(ok) == 5                      # the budget buys 5 real pages
    assert len(result.pages) == 5 + 4        # and the 4 failures are still recorded


def test_b65_failures_beyond_the_cap_count_as_attempts():
    client = _site_with_dead_links(n_dead=30, n_live=10)
    result = crawl_site("https://example.com/", ["example.com"], _cfg(max_failed_pages=3), client=client)
    failed = [p for p in result.pages if p.status != "ok"]
    # 3 free failures, then each further failure uses a slot, so the crawl stops after
    # 5 (budget) + 3 (free) = 8 pages -- the homepage plus 7 failures -- and never reaches the
    # live pages ranked behind 30 dead ones
    assert len(result.pages) == 8
    assert len(failed) == 7


def test_b65_a_site_with_no_failures_behaves_exactly_as_before():
    client = _site_with_dead_links(n_dead=0, n_live=10)
    result = crawl_site("https://example.com/", ["example.com"], _cfg(), client=client)
    assert len(result.pages) == 5


# ---- B-69: bare-domain start URL whose start page links to /en... pages -------------------------
def test_b69_bare_domain_start_page_linking_to_en_skips_other_languages():
    # live snowflake.com: https://www.snowflake.com/ links to /en/pricing-options and to /ja/, /ko/,
    # /pt_br/ ... copies of it; 10 of 40 fetched pages were such copies before this fix
    pages = dict(LOCALE_PAGES)
    pages["https://s.example"] = pages.pop("https://s.example/en")
    config = {"crawl": dict(BASE_CONFIG["crawl"], respect_robots=False)}
    with _locale_site_client(pages) as client:
        result = crawl_site("https://s.example/", ["s.example"], config, client=client)
    fetched = {p.url for p in result.pages}
    assert "https://s.example/en/pricing" in fetched and "https://s.example/resource/guide" in fetched
    assert "https://s.example/ja/pricing" not in fetched and "https://s.example/de/pricing" not in fetched
    assert set(result.skipped_as_other_locale) == {"https://s.example/ja/pricing", "https://s.example/de/pricing"}


def test_b69_switch_off_keeps_every_language():
    pages = dict(LOCALE_PAGES)
    pages["https://s.example"] = pages.pop("https://s.example/en")
    config = {"crawl": dict(BASE_CONFIG["crawl"], respect_robots=False, skip_other_locales=False)}
    with _locale_site_client(pages) as client:
        result = crawl_site("https://s.example/", ["s.example"], config, client=client)
    assert "https://s.example/ja/pricing" in {p.url for p in result.pages}


def test_b69_english_variants_and_non_language_segments_are_kept():
    pages = {
        "https://s.example": ('<html><body><a href="/en-gb/pricing">GB</a> <a href="/us/plans">US</a> '
                              '<a href="/en/about">A</a></body></html>'),
        "https://s.example/en-gb/pricing": "<html><body>gb</body></html>",
        "https://s.example/us/plans": "<html><body>us</body></html>",
        "https://s.example/en/about": "<html><body>about</body></html>",
    }
    config = {"crawl": dict(BASE_CONFIG["crawl"], respect_robots=False)}
    with _locale_site_client(pages) as client:
        result = crawl_site("https://s.example/", ["s.example"], config, client=client)
    assert result.skipped_as_other_locale == []
    assert {"https://s.example/en-gb/pricing", "https://s.example/us/plans"} <= {p.url for p in result.pages}


def test_crawl_site_flags_page_cap_reached_when_links_are_left_unfetched():
    # B-73: found on razorpay.com, which stopped at exactly max_pages (40) with links still
    # queued, yet limit_reached came out false because budget_exhausted only covers the time
    # budget. Here the homepage links to /about, which max_pages=1 leaves unfetched.
    config = {**BASE_CONFIG, "crawl": {**BASE_CONFIG["crawl"], "max_pages": 1}}
    with make_client() as client:
        result = crawl_site("https://example.com/", ["example.com"], config, client=client)

    assert len(result.pages) == 1
    assert result.page_cap_reached is True
    assert result.budget_exhausted is False  # the time budget is a separate limit
    assert crawl_diagnostics(result)["page_cap_reached"] is True


def test_crawl_site_does_not_flag_page_cap_when_the_site_runs_out_of_pages_first():
    # B-73: a site smaller than max_pages (25 here) fetches everything it discovers; nothing was
    # cut off, so the flag stays false.
    with make_client() as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)

    assert len(result.pages) < BASE_CONFIG["crawl"]["max_pages"]
    assert result.page_cap_reached is False
    assert crawl_diagnostics(result)["page_cap_reached"] is False


def _dup_client(pages):
    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in pages:
            status, body = pages[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_b75_same_page_with_different_raw_html_is_a_duplicate():
    # B-75: found on freshworks.com, where /customers, http://.../customers and
    # /360-customer-engagement all serve the same page but each response carries its own nonce,
    # so the raw-HTML hash never matched and all three used a page slot.
    def page(nonce):
        return (f'<html><head><title>Customers</title><script nonce="{nonce}">x()</script></head>'
                f'<body><p>Thousands of teams run their support on our platform every day.</p></body></html>')
    pages = {
        "https://example.com/": (200, '<html><body><a href="/customers">C</a> <a href="/stories">S</a></body></html>'),
        "https://example.com/customers": (200, page("a1b2")),
        "https://example.com/stories": (200, page("c3d4")),
    }
    with _dup_client(pages) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)

    assert {p.url for p in result.pages} == {"https://example.com/", "https://example.com/customers"}
    assert result.skipped_as_duplicate == ["https://example.com/stories"]


def test_b75_same_body_under_a_different_title_is_kept():
    # The title is page text the evidence check searches, so pages that differ only there are
    # not merged.
    body = "<body><p>Thousands of teams run their support on our platform every day.</p></body>"
    pages = {
        "https://example.com/": (200, '<html><body><a href="/a">A</a> <a href="/b">B</a></body></html>'),
        "https://example.com/a": (200, f"<html><head><title>Plan A</title></head>{body}</html>"),
        "https://example.com/b": (200, f"<html><head><title>Plan B</title></head>{body}</html>"),
    }
    with _dup_client(pages) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)

    assert len(result.pages) == 3
    assert result.skipped_as_duplicate == []


def test_b75_two_different_empty_shells_are_not_merged():
    # No text at all to compare: fall back to the raw-HTML hash, so two different JS shells stay.
    pages = {
        "https://example.com/": (200, '<html><body><a href="/a">A</a> <a href="/b">B</a></body></html>'),
        "https://example.com/a": (200, '<html><body><div id="app-a"></div></body></html>'),
        "https://example.com/b": (200, '<html><body><div id="app-b"></div></body></html>'),
    }
    with _dup_client(pages) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)

    assert len(result.pages) == 3


def _redirect_client(pages, redirects):
    def handler(request: httpx.Request) -> httpx.Response:
        key = str(request.url)
        if key in redirects:
            return httpx.Response(301, headers={"Location": redirects[key]})
        if key in pages:
            status, body = pages[key]
            return httpx.Response(status, text=body)
        return httpx.Response(404, text="not found")
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True, max_redirects=5)


def test_b76_fetch_page_records_the_final_resolved_url():
    # B-76 (PRD Section 9: "Record the final resolved URL as the source").
    pages = {"https://example.com/customers/": (200, "<html><body>Customers</body></html>")}
    redirects = {"https://example.com/360-customer-engagement": "https://example.com/customers/"}
    with _redirect_client(pages, redirects) as client:
        page = fetch_page(client, "https://example.com/360-customer-engagement", 100_000, 5)

    assert page.url == "https://example.com/customers"          # normalised final URL
    assert page.requested_url == "https://example.com/360-customer-engagement"


def test_b76_fetch_page_without_a_redirect_leaves_requested_url_empty():
    with make_client() as client:
        page = fetch_page(client, "https://example.com/about", 100_000, 5)
    assert page.url == "https://example.com/about"
    assert page.requested_url is None


def test_b76_redirect_to_a_page_already_kept_is_a_duplicate_and_links_resolve_from_the_final_url():
    # Found on freshworks.com: /company/partners redirects to /partners/, which was also crawled.
    pages = {
        "https://example.com/": (200, '<html><body><a href="/partners">P</a> <a href="/company/partners">CP</a> '
                                      '<a href="/old-team">T</a></body></html>'),
        "https://example.com/partners": (200, "<html><head><title>Partners</title></head><body>Partner list</body></html>"),
        "https://example.com/company/team/": (200, '<html><body>Team <a href="board">Board</a></body></html>'),
        "https://example.com/company/team/board": (200, "<html><body>Board members</body></html>"),
    }
    redirects = {
        "https://example.com/company/partners": "https://example.com/partners",
        "https://example.com/old-team": "https://example.com/company/team/",
    }
    with _redirect_client(pages, redirects) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)

    urls = [p.url for p in result.pages if p.status == "ok"]
    assert urls.count("https://example.com/partners") == 1
    assert "https://example.com/company/partners" in result.skipped_as_duplicate
    team = next(p for p in result.pages if p.url == "https://example.com/company/team")
    assert team.requested_url == "https://example.com/old-team"
    # "board" is relative to /company/team/, not to the /old-team address that was requested.
    assert "https://example.com/company/team/board" in urls
    assert crawl_diagnostics(result)["pages"][urls.index("https://example.com/company/team")]["requested_url"] \
        == "https://example.com/old-team"


def test_b78_is_auth_url_matches_login_hosts_and_whole_path_segments_only():
    from wi.crawl.fetch import is_auth_url
    for url in ["https://login.example.com/email-login", "https://sso.example.com/",
                "https://example.com/signin", "https://example.com/sign-in?next=/",
                "https://example.com/sso/start", "https://example.com/app/login",
                "https://example.com/LOGIN"]:
        assert is_auth_url(url), url
    for url in ["https://example.com/authors", "https://example.com/blog/logins-guide",
                "https://example.com/signup", "https://example.com/pricing",
                "https://www.example.com/customers"]:
        assert not is_auth_url(url), url


def test_b78_crawl_skips_login_links_before_fetching_them():
    # Found on freshworks.com: login.freshworks.com/email-login took a page slot and a Playwright
    # render. Signup links are kept: they are a sales cue, not an account screen.
    fetched = []
    pages = {
        "https://example.com/": (200, '<html><body><a href="https://login.example.com/email-login">Log in</a> '
                                      '<a href="/signin">Sign in</a> <a href="/signup">Sign up</a></body></html>'),
        "https://example.com/signup": (200, "<html><body>Start for free</body></html>"),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(str(request.url))
        if str(request.url) in pages:
            status, body = pages[str(request.url)]
            return httpx.Response(status, text=body)
        return httpx.Response(200, text="<html><body>Sign in to your account</body></html>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)

    assert result.skipped_as_auth == ["https://login.example.com/email-login", "https://example.com/signin"]
    assert not any("signin" in u or "login." in u for u in fetched)
    assert "https://example.com/signup" in [p.url for p in result.pages]
    assert crawl_diagnostics(result)["skipped_as_auth"] == result.skipped_as_auth


def test_b80_redirect_ending_off_domain_or_on_a_disallowed_path_is_dropped_with_a_reason():
    # B-80: robots.txt and the domain scope were only checked on the address asked for; a
    # redirect could still land outside them.
    pages = {
        "https://example.com/robots.txt": (200, "User-agent: *\nDisallow: /private/\n"),
        "https://example.com/": (200, '<html><body><a href="/go-out">Out</a> <a href="/go-private">Priv</a> '
                                      '<a href="/go-about">About</a></body></html>'),
        "https://elsewhere.org/landing": (200, '<html><body>Other company <a href="/more">More</a></body></html>'),
        "https://example.com/private/area": (200, "<html><body>Private</body></html>"),
        "https://example.com/about": (200, "<html><head><title>About</title></head><body>About us</body></html>"),
    }
    redirects = {
        "https://example.com/go-out": "https://elsewhere.org/landing",
        "https://example.com/go-private": "https://example.com/private/area",
        "https://example.com/go-about": "https://example.com/about",
    }
    with _redirect_client(pages, redirects) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)

    kept = [p.url for p in result.pages]
    assert kept == ["https://example.com/", "https://example.com/about"]   # in-scope redirect kept
    assert result.dropped_after_redirect == [
        {"requested_url": "https://example.com/go-out", "final_url": "https://elsewhere.org/landing",
         "reason": "final URL outside the approved domains"},
        {"requested_url": "https://example.com/go-private", "final_url": "https://example.com/private/area",
         "reason": "final URL disallowed by robots.txt"},
    ]
    assert crawl_diagnostics(result)["dropped_after_redirect"] == result.dropped_after_redirect


# --- B-83: unreachable site (PRD Section 9 / INP-03) -------------------------------------------

def _flaky_client(responses, calls):
    """`responses` maps a URL to a list of outcomes served in order (the last one repeats): an int
    is an HTTP status, an exception class is raised as a network failure."""
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if url.endswith("/robots.txt"):
            return httpx.Response(404)
        seq = responses.get(url, [404])
        outcome = seq.pop(0) if len(seq) > 1 else seq[0]
        if isinstance(outcome, type) and issubclass(outcome, Exception):
            raise outcome("simulated", request=request)
        return httpx.Response(outcome, text="<html><body>Hello there, a real page.</body></html>")
    return httpx.Client(transport=httpx.MockTransport(handler))


def _record_sleeps(monkeypatch):
    slept = []
    monkeypatch.setattr("wi.crawl.fetch.time.sleep", lambda s: slept.append(s))
    return slept


def test_b83_start_url_recovers_after_retries(monkeypatch):
    slept, calls = _record_sleeps(monkeypatch), []
    responses = {"https://example.com/": [httpx.ConnectError, 503, 200]}
    with _flaky_client(responses, calls) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)

    assert result.crawl_status == "ok"
    assert result.start_attempts == 3
    assert slept == [1.0, 2.0]
    assert [p.url for p in result.pages] == ["https://example.com/"]


def test_b83_start_url_that_never_answers_is_site_unreachable(monkeypatch):
    slept, calls = _record_sleeps(monkeypatch), []
    responses = {"https://example.com/": [httpx.ConnectTimeout]}
    with _flaky_client(responses, calls) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)

    assert result.crawl_status == "unreachable"
    assert result.crawl_error_code == "SITE_UNREACHABLE"
    assert result.start_attempts == 3                     # 1 try + 2 bounded retries
    assert slept == [1.0, 2.0]
    assert "after 3 attempt(s)" in result.crawl_status_reason
    diag = crawl_diagnostics(result)
    assert (diag["crawl_status"], diag["crawl_error_code"]) == ("unreachable", "SITE_UNREACHABLE")


def test_b83_5xx_start_url_is_retried_then_unreachable(monkeypatch):
    slept, calls = _record_sleeps(monkeypatch), []
    with _flaky_client({"https://example.com/": [503]}, calls) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)
    assert result.crawl_status == "unreachable" and result.start_attempts == 3
    assert "HTTP 503" in result.crawl_status_reason


def test_b83_4xx_start_url_is_never_retried(monkeypatch):
    slept, calls = _record_sleeps(monkeypatch), []
    with _flaky_client({"https://example.com/": [404]}, calls) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)
    assert result.start_attempts == 1 and slept == []
    assert result.crawl_status == "unreachable"
    assert calls.count("https://example.com/") == 1


def test_b83_retries_stop_at_the_total_time_budget(monkeypatch):
    slept, calls = _record_sleeps(monkeypatch), []
    config = {**BASE_CONFIG, "crawl": {**BASE_CONFIG["crawl"], "total_budget_s": 0.5}}
    with _flaky_client({"https://example.com/": [httpx.ConnectError]}, calls) as client:
        result = crawl_site("https://example.com/", ["example.com"], config, client=client)
    assert result.start_attempts == 1 and slept == []     # a 1 s wait would pass the 0.5 s budget
    assert result.crawl_status == "unreachable"


def test_b83_pages_after_the_start_page_are_never_retried(monkeypatch):
    slept, calls = _record_sleeps(monkeypatch), []
    responses = {
        "https://example.com/": [200],
        "https://example.com/about": [503],
    }

    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url.endswith("/robots.txt"):
            return httpx.Response(404)
        if url == "https://example.com/":
            return httpx.Response(200, text='<html><body><a href="/about">About</a> text</body></html>')
        return httpx.Response(503)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = crawl_site("https://example.com/", ["example.com"], BASE_CONFIG, client=client)
    assert calls.count("https://example.com/about") == 1
    assert result.crawl_status == "ok" and slept == []


# --- B-84: blocked sites (PRD Section 9 / INP-03, CRL-03) ----------------------------------------

CF_CHALLENGE = ('<html><head><title>Just a moment...</title></head><body>'
                '<script>window._cf_chl_opt={cvId:"3"};</script>'
                '<noscript>Enable JavaScript and cookies to continue</noscript></body></html>')
REAL_PAGE = ('<html><head><title>Example Co</title></head><body><h1>Example Co</h1><p>'
             + "We build scheduling software for teams of every size. " * 20 + '</p></body></html>')


def _scripted_client(script, calls, robots="User-agent: *\nAllow: /\n"):
    """`script` maps a URL to a list of (status, headers, body) served in order; the last repeats."""
    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url.endswith("/robots.txt"):
            return httpx.Response(200, text=robots)
        seq = script.get(url, [(404, {}, "not found")])
        status, headers, body = seq.pop(0) if len(seq) > 1 else seq[0]
        return httpx.Response(status, headers=headers, text=body)
    return httpx.Client(transport=httpx.MockTransport(handler))


def _crawl(script, monkeypatch, robots="User-agent: *\nAllow: /\n", js_renderer=None, config=BASE_CONFIG):
    slept, calls = _record_sleeps(monkeypatch), []
    with _scripted_client(script, calls, robots) as client:
        result = crawl_site("https://example.com/", ["example.com"], config, client=client,
                            js_renderer=js_renderer)
    return result, slept, calls


def test_b84_start_page_403_or_401_is_blocked_and_never_retried(monkeypatch):
    for status in (403, 401):
        result, slept, calls = _crawl({"https://example.com/": [(status, {}, "Forbidden")]}, monkeypatch)
        assert (result.crawl_status, result.crawl_error_code) == ("blocked", "SITE_BLOCKED")
        assert result.start_attempts == 1 and slept == []
        assert f"HTTP {status}" in result.crawl_status_reason
        assert result.pages[0].error_code == "BLOCKED"


def test_b84_start_page_429_honours_retry_after_then_recovers(monkeypatch):
    script = {"https://example.com/": [(429, {"Retry-After": "3"}, ""), (200, {}, REAL_PAGE)]}
    result, slept, _ = _crawl(script, monkeypatch)
    assert result.crawl_status == "ok" and slept == [3.0] and result.start_attempts == 2


def test_b84_start_page_429_that_persists_is_blocked_after_bounded_backoff(monkeypatch):
    result, slept, _ = _crawl({"https://example.com/": [(429, {"Retry-After": "1"}, "")]}, monkeypatch)
    assert slept == [1.0, 1.0] and result.start_attempts == 3
    assert (result.crawl_status, result.crawl_error_code) == ("blocked", "SITE_BLOCKED")
    assert "HTTP 429" in result.crawl_status_reason


def test_b84_start_page_429_without_retry_after_uses_the_1s_2s_backoff(monkeypatch):
    result, slept, _ = _crawl({"https://example.com/": [(429, {}, "")]}, monkeypatch)
    assert slept == [1.0, 2.0] and result.crawl_status == "blocked"


def test_b84_a_retry_after_longer_than_the_cap_is_not_retried_early(monkeypatch):
    result, slept, _ = _crawl({"https://example.com/": [(429, {"Retry-After": "120"}, "")]}, monkeypatch)
    assert slept == [] and result.start_attempts == 1 and result.crawl_status == "blocked"


def test_b84_cloudflare_challenge_header_on_a_503_is_blocked_not_retried(monkeypatch):
    script = {"https://example.com/": [(503, {"cf-mitigated": "challenge"}, CF_CHALLENGE)]}
    result, slept, _ = _crawl(script, monkeypatch)
    assert result.crawl_status == "blocked" and slept == [] and result.start_attempts == 1
    assert "cf-mitigated" in result.crawl_status_reason


def test_b84_challenge_page_served_with_200_is_blocked_and_never_rendered(monkeypatch):
    rendered = []
    result, _, _ = _crawl({"https://example.com/": [(200, {}, CF_CHALLENGE)]}, monkeypatch,
                          js_renderer=lambda url, t: rendered.append(url) or REAL_PAGE)
    assert (result.crawl_status, result.crawl_error_code) == ("blocked", "SITE_BLOCKED")
    assert "bot-protection page" in result.crawl_status_reason
    assert rendered == []                                # the JS fallback never touches it
    assert all(p.status == "error" for p in result.pages)


def test_b84_robots_disallowing_the_start_url_is_blocked_and_it_is_not_fetched(monkeypatch):
    result, _, calls = _crawl({"https://example.com/": [(200, {}, REAL_PAGE)]}, monkeypatch,
                              robots="User-agent: *\nDisallow: /\n")
    assert (result.crawl_status, result.crawl_error_code) == ("blocked", "ROBOTS_DISALLOWED")
    assert "https://example.com/" not in calls           # fetch behaviour unchanged: never fetched
    assert result.skipped_by_robots == ["https://example.com/"]


def test_b84_ordinary_pages_are_not_mistaken_for_challenges():
    from wi.crawl.fetch import detect_challenge
    contact = REAL_PAGE.replace("</body>", '<div class="g-recaptcha" data-sitekey="x"></div></body>')
    article = REAL_PAGE.replace("<title>Example Co", "<title>Access denied: how we handle data requests")
    assert detect_challenge(contact, start_page=True) is None
    assert detect_challenge(contact) is None             # long page: a widget alone is not a wall
    assert detect_challenge(article, start_page=True) is None
    assert detect_challenge('<html><body><div class="g-recaptcha"></div></body></html>',
                            start_page=True) is None     # start page needs a strong marker
    assert "CAPTCHA page" in detect_challenge('<html><body><div class="g-recaptcha"></div></body></html>')


def test_b84_later_refusals_are_listed_and_never_used_but_the_crawl_stays_ok(monkeypatch):
    home = ('<html><head><title>Home</title></head><body>' + "Real home text. " * 30 +
            '<a href="/pricing">P</a> <a href="/contact">C</a> <a href="/about">A</a></body></html>')
    captcha = ('<html><head><title>Contact</title></head><body><div class="g-recaptcha"></div>'
               '<a href="/secret">S</a></body></html>')
    rendered = []
    script = {
        "https://example.com/": [(200, {}, home)],
        "https://example.com/pricing": [(403, {}, "Forbidden")],
        "https://example.com/contact": [(200, {}, captcha)],
        "https://example.com/about": [(200, {}, REAL_PAGE)],
    }
    result, slept, calls = _crawl(script, monkeypatch, js_renderer=lambda u, t: rendered.append(u))
    assert result.crawl_status == "ok"
    assert [w for w in slept if w >= 0.5] == []          # no retry waits (tiny politeness gaps only)
    assert [b["url"] for b in result.blocked_pages] == ["https://example.com/pricing",
                                                        "https://example.com/contact"]
    ok_urls = [p.url for p in result.pages if p.status == "ok"]
    assert ok_urls == ["https://example.com/", "https://example.com/about"]
    assert "https://example.com/secret" not in calls     # the CAPTCHA page's links are not followed
    assert "https://example.com/contact" not in rendered
    assert crawl_diagnostics(result)["blocked_pages"] == result.blocked_pages


def test_b84_a_render_that_turns_out_to_be_a_challenge_is_discarded(monkeypatch):
    thin = '<html><head><title>Home</title></head><body><div id="app"></div></body></html>'
    config = {**BASE_CONFIG, "crawl": {**BASE_CONFIG["crawl"], "js_fallback_min_text_chars": 200}}
    result, _, _ = _crawl({"https://example.com/": [(200, {}, thin)]}, monkeypatch,
                          js_renderer=lambda u, t: CF_CHALLENGE, config=config)
    assert result.pages[0].js_rendered is False and result.pages[0].html == thin


def test_b84_parse_retry_after_reads_seconds_and_http_dates():
    from wi.crawl.fetch import parse_retry_after
    assert parse_retry_after("5") == 5.0
    assert parse_retry_after(None) is None and parse_retry_after("soon") is None
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0   # in the past: no wait


# --- B-86: a start URL that redirects off the approved domains ------------------------------------

def _redirect_site(redirects, pages):
    calls = []

    def handler(request):
        url = str(request.url)
        calls.append(url)
        if url.endswith("/robots.txt"):
            return httpx.Response(404)
        if url in redirects:
            return httpx.Response(301, headers={"Location": redirects[url]})
        return httpx.Response(200, text=pages.get(url, REAL_PAGE))
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True, max_redirects=5), calls


def _crawl_from(start, redirects, pages=None, monkeypatch=None):
    from wi.crawl.url import validate_company_url
    if monkeypatch:
        _record_sleeps(monkeypatch)
    v = validate_company_url(start)
    client, calls = _redirect_site(redirects, pages or {})
    with client:
        return crawl_site(v.url, v.approved_domains, BASE_CONFIG, client=client), calls


def test_b86_start_url_redirecting_to_another_domain_is_reported_and_not_crawled(monkeypatch):
    home_elsewhere = '<html><body>' + "Atlassian text. " * 40 + '<a href="/jira">Jira</a></body></html>'
    result, calls = _crawl_from(
        "https://www.loom.com/", {"https://www.loom.com/": "https://www.atlassian.com/software/loom"},
        {"https://www.atlassian.com/software/loom": home_elsewhere}, monkeypatch)
    assert (result.crawl_status, result.crawl_error_code) == ("redirected", "REDIRECTED_OFF_DOMAIN")
    assert result.final_url == "https://www.atlassian.com/software/loom"
    assert "outside the approved domains" in result.crawl_status_reason
    assert [p for p in result.pages if p.status == "ok"] == []          # nothing to send to the model
    assert "https://www.atlassian.com/jira" not in calls                 # its links are not followed
    assert crawl_diagnostics(result)["final_url"] == result.final_url


def test_b86_redirects_that_stay_on_the_company_domain_are_ok(monkeypatch):
    cases = [
        ("https://example.co.in/", {"https://example.co.in/": "https://www.example.co.in/"}),   # apex -> www
        ("https://www.example.co.uk/", {"https://www.example.co.uk/": "https://example.co.uk/"}),  # www -> apex
        ("http://example.com/", {"http://example.com/": "https://example.com/"}),               # http -> https
        ("https://example.com/", {"https://example.com/": "https://example.com/en/home"}),      # path
    ]
    for start, redirects in cases:
        result, _ = _crawl_from(start, redirects, monkeypatch=monkeypatch)
        assert result.crawl_status == "ok", start
        assert result.final_url is None
        assert [p.status for p in result.pages][:1] == ["ok"], start


def test_b86_a_different_company_on_the_same_country_suffix_is_off_domain(monkeypatch):
    # The rule compares against the host as given, never a bare "co.uk" or "co.in".
    for start, target in [("https://example.co.uk/", "https://another-company.co.uk/"),
                          ("https://example.co.in/", "https://www.someone-else.co.in/")]:
        result, _ = _crawl_from(start, {start: target}, monkeypatch=monkeypatch)
        assert (result.crawl_status, result.crawl_error_code) == ("redirected", "REDIRECTED_OFF_DOMAIN"), start


def test_b86_redirect_to_a_restricted_platform_is_marked_restricted(monkeypatch):
    result, _ = _crawl_from("https://example.com/",
                            {"https://example.com/": "https://www.linkedin.com/company/example"},
                            monkeypatch=monkeypatch)
    assert (result.crawl_status, result.crawl_error_code) == ("redirected", "RESTRICTED_PLATFORM")


def test_b86_loom_start_page_behaves_exactly_as_before(monkeypatch):
    # Loom today: the start page is served directly; some of its links redirect to atlassian.com
    # and are dropped by B-80 as before. crawl_status stays "ok" and the start page is crawled.
    home = ('<html><head><title>Loom</title></head><body>' + "Record your screen with Loom. " * 30 +
            '<a href="/pricing">Pricing</a> <a href="/security">Security</a></body></html>')
    result, calls = _crawl_from(
        "https://www.loom.com/",
        {"https://www.loom.com/security": "https://www.atlassian.com/legal/security-measures"},
        {"https://www.loom.com/": home}, monkeypatch)
    assert result.crawl_status == "ok" and result.final_url is None
    assert [p.url for p in result.pages if p.status == "ok"] == ["https://www.loom.com/",
                                                                 "https://www.loom.com/pricing"]
    assert result.dropped_after_redirect == [{
        "requested_url": "https://www.loom.com/security",
        "final_url": "https://www.atlassian.com/legal/security-measures",
        "reason": "final URL outside the approved domains"}]


def test_b86_validation_still_rejects_restricted_platforms_through_the_shared_helper():
    from wi.crawl.url import is_restricted_host, validate_company_url
    assert validate_company_url("https://www.linkedin.com/company/acme").error_code == "RESTRICTED_PLATFORM"
    assert is_restricted_host("www.linkedin.com") and is_restricted_host("m.facebook.com")
    assert not is_restricted_host("example.co.uk")


# --- B-90: country-code path segments ------------------------------------------------------------

def test_b90_english_speaking_country_segments_are_english_and_never_skipped():
    from wi.crawl.fetch import is_non_english_locale_url
    for seg in ["us", "uk", "gb", "in", "au", "ca", "nz", "ie", "sg", "za", "UK", "Ca"]:
        url = f"https://s.example/{seg}/pricing"
        assert locale_language(url) == "en", seg
        assert not is_non_english_locale_url(url), seg
        assert not is_other_locale_url(url, "https://s.example/en"), seg


def test_b90_other_country_codes_map_to_their_language_and_are_skipped():
    from wi.crawl.fetch import is_non_english_locale_url
    expected = {"jp": "ja", "kr": "ko", "cn": "zh", "tw": "zh", "hk": "zh", "br": "pt", "mx": "es"}
    for seg, lang in expected.items():
        url = f"https://s.example/{seg}/security"
        assert locale_language(url) == lang, seg
        assert is_non_english_locale_url(url), seg


def test_b90_language_with_region_keeps_its_language_meaning():
    assert locale_language("https://s.example/ca-es/x") == "ca"       # Catalan (Spain), not Canada
    assert locale_language("https://s.example/en-in/x") == "en"
    assert locale_language("https://s.example/pt_br/x") == "pt"


def test_b90_crawl_keeps_english_country_pages_and_skips_other_countries():
    links = "".join(f'<a href="/{s}/page">{s}</a> ' for s in ["uk", "ca", "us", "in", "au", "jp", "kr", "cn", "de"])
    pages = {"https://s.example/en": f"<html><body>Home {links}</body></html>"}
    pages.update({f"https://s.example/{s}/page": f"<html><body>{s} page text</body></html>"
                  for s in ["uk", "ca", "us", "in", "au", "jp", "kr", "cn", "de"]})
    with _locale_site_client(pages) as client:
        result = crawl_site("https://s.example/en", ["s.example"], BASE_CONFIG, client=client)
    fetched = {p.url for p in result.pages}
    for s in ["uk", "ca", "us", "in", "au"]:
        assert f"https://s.example/{s}/page" in fetched, s
    assert sorted(result.skipped_as_other_locale) == sorted(
        f"https://s.example/{s}/page" for s in ["jp", "kr", "cn", "de"])
