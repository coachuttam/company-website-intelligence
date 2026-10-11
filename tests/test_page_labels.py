"""B-100: logo/image labels on every page and navigation text on the homepage (wi/crawl/page_labels.py).
HTML fixtures only: no network, no model call."""
from __future__ import annotations

import json

from wi.crawl import cache as cache_module
from wi.crawl.clean import CleanPage, clean_page, main_text
from wi.crawl.fetch import FetchResult
from wi.crawl.page_labels import (
    LABELS_BUDGET, LABELS_HEADER, MAX_LABELS, MAX_NAV_ITEMS, NAV_BUDGET, NAV_HEADER, filter_label,
    homepage_url, image_labels, nav_items,
)
from wi.crawl.snapshot import build_snapshot

PROSE = "<p>" + "Acme builds rockets for teams that need to reach orbit on a budget. " * 8 + "</p>"


def _page(body: str, head: str = "<title>Acme</title>") -> str:
    return f"<html><head>{head}</head><body><main><h1>Acme</h1>{PROSE}{body}</main></body></html>"


# 1. each filter rule
def test_filter_rules():
    assert filter_label("Publix Logo") == ("Publix", None)          # trailing generic word stripped
    assert filter_label("Cal.com") == ("Cal.com", None)             # a domain is not a file name
    assert filter_label("CVS Health") == ("CVS Health", None)
    assert filter_label("A") == (None, "length")
    assert filter_label("x" * 61) == (None, "length")
    assert filter_label("2024") == (None, "no_letter")
    assert filter_label("hero-banner.png") == (None, "file_name")
    assert filter_label("image_28") == (None, "slug")
    assert filter_label("unext_logo") == (None, "slug")
    assert filter_label("ozonetel-1") == (None, "slug")
    assert filter_label("X logo") == (None, "empty_after_strip")
    assert filter_label("Testimonial media") == (None, "generic")
    assert filter_label("arrow") == (None, "generic")


def test_sources_order_duplicates_and_skips():
    html = _page(
        '<img alt="Globex"><svg aria-label="Initech"></svg><a aria-label="Hooli" href="/h">x</a>'
        '<div title="Umbrella"><svg></svg></div>'          # title on a logo wrapper
        '<div title="Just a tooltip">text</div>'           # not logo-like: ignored
        '<img alt="globex">'                                # duplicate after casefolding
        '<img alt="Pixel" width="1" height="1">'           # tracking pixel
        '<div class="cookie-consent"><img alt="Consent Co"></div>'
        '<noscript><img alt="Noscript Co"></noscript>')
    stats = {}
    assert image_labels(html, stats) == ["Globex", "Initech", "Hooli", "Umbrella"]
    assert stats.get("duplicate") == 1


def test_label_cap_and_budget():
    html = _page("".join(f'<img alt="Company Number {chr(65 + i // 26)}{chr(65 + i % 26)}">' for i in range(100)))
    labels = image_labels(html)
    assert len(labels) == MAX_LABELS
    page = clean_page("https://acme.example/customers", html, 12000)
    block = page.text.split("\n" + LABELS_HEADER, 1)[1]
    assert len(LABELS_HEADER + block) <= LABELS_BUDGET


# 2. navigation: homepage only
NAV = ('<header><nav><a href="/">Home</a><a href="/i">Industries</a><a href="/r">Retail</a>'
       '<a href="/l">Log in</a><a href="/x">›</a></nav></header>'
       '<footer><a href="/i">industries</a><a href="/c">Compare vs Rivalco</a></footer>')


def test_nav_block_only_on_the_homepage():
    html = f"<html><head><title>Acme</title></head><body>{NAV}<main><h1>Acme</h1>{PROSE}</main></body></html>"
    home = clean_page("https://acme.example/", html, 12000, homepage=True).text
    other = clean_page("https://acme.example/about", html, 12000).text
    assert f"\n{NAV_HEADER} Industries | Retail | Compare vs Rivalco" in home   # order, dups, generic, punctuation
    assert NAV_HEADER not in other
    assert nav_items(html) == ["Industries", "Retail", "Compare vs Rivalco"]


def test_nav_cap_and_budget():
    links = "".join(f'<a href="/p{i}">Product line {i:03d} with a long name</a>' for i in range(300))
    html = f"<html><body><nav>{links}</nav><main>{PROSE}</main></body></html>"
    assert len(nav_items(html)) == MAX_NAV_ITEMS
    text = clean_page("https://acme.example/", html, 12000, homepage=True).text
    block = text.split("\n" + NAV_HEADER, 1)[1]
    assert len(NAV_HEADER + block) <= NAV_BUDGET


def test_homepage_is_the_shortest_path():
    assert homepage_url(["https://a.example/about", "https://a.example/", "https://a.example/x"]) == "https://a.example/"
    assert homepage_url([]) is None


# 3. budgets never truncate main content
def test_blocks_never_push_main_content_out():
    html = _page('<img alt="Globex">')
    capped = clean_page("https://acme.example/about", html, 200)
    assert capped.text.startswith(main_text("https://acme.example/about", html)[:200])
    assert capped.text.endswith(f"\n{LABELS_HEADER} Globex") and capped.truncated


# 4. no alts and no nav: byte-identical to the old cleaned text
def test_page_without_labels_or_nav_is_unchanged():
    html = _page("")
    url = "https://acme.example/about"
    old = main_text(url, html)[:12000]
    assert clean_page(url, html, 12000).text == old
    assert clean_page(url, html, 12000, homepage=True).text == old   # homepage without nav elements


# 5. the evidence gate sees the blocks as page text
def test_a_quote_from_a_block_is_found_by_the_gate():
    from wi.validate.evidence import quote_in_page
    page = clean_page("https://acme.example/", _page('<img alt="Globex">'), 12000)
    assert quote_in_page("Globex", page.text)


# 6. versions and snapshot
def test_version_bump_changes_the_cache_key(monkeypatch):
    assert cache_module.EXTRACTION_LOGIC_VERSION == 27
    pages = [CleanPage(url="https://acme.example/", title="Acme", text="x")]
    k27 = cache_module.run_fingerprint("https://acme.example/", pages, {})
    monkeypatch.setattr(cache_module, "EXTRACTION_LOGIC_VERSION", 26)
    assert cache_module.run_fingerprint("https://acme.example/", pages, {}) != k27


def test_snapshot_format_still_loads():
    html = _page('<img alt="Globex">')
    cp = clean_page("https://acme.example/", html, 12000, homepage=True)
    fetched = [FetchResult(url=cp.url, status="ok", status_code=200, html=html)]
    snap = json.loads(json.dumps(build_snapshot("https://acme.example/", "2026-10-11", fetched, [cp], [cp.url])))
    page = snap["pages"][0]
    assert {"clean_text", "clean_chars", "clean_truncated", "clean_sha256", "sent_to_model"} <= set(page)
    assert page["clean_text"] == cp.text and LABELS_HEADER in page["clean_text"]
