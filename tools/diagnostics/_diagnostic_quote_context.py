#!/usr/bin/env python3
"""Diagnostic only (no LLM call, no scoring): crawl one site exactly as run_site.py does, then
print the CLEANED text around each search term, with repr() so newlines and odd spacing are
visible. Used to see why a model quote such as 'Business, 1,499/month' was 'not found in page
text' -- i.e. how the real page text lays that content out.

Usage:
    python tools/diagnostics/_diagnostic_quote_context.py URL TERM [TERM ...] [options]

Options:
    --home         only look at the site's home page (the page whose path is "/")
    --page TEXT    only look at pages whose URL contains TEXT (repeatable)
    --full         also print each selected page's whole cleaned text (use with --home/--page)
    --max-hits N   hits shown per term per page (default 2)

Examples:
    python tools/diagnostics/_diagnostic_quote_context.py https://simplestores.in/ "1,499" "Enterprise"
    python tools/diagnostics/_diagnostic_quote_context.py https://www.notion.com/ "capture context" --home
    python tools/diagnostics/_diagnostic_quote_context.py https://www.notion.com/ --home --full

A summary at the end lists, for every term, how many pages it was found on, so a term that
printed nothing is reported as "NOT FOUND" rather than silently omitted. TERM is optional
when --full is used.
"""
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wi.config import load_config
from wi.crawl.clean import clean_page, resolve_char_cap
from wi.crawl.fetch import crawl_site
from wi.crawl.js_fallback import render_with_playwright
from wi.crawl.url import validate_company_url
from wi.validate.evidence import normalise

WINDOW = 90
DEFAULT_MAX_HITS = 2


def parse_args(argv):
    """Split argv into (url, terms, options). Pure function so it can be tested."""
    opts = {"home": False, "pages": [], "full": False, "max_hits": DEFAULT_MAX_HITS}
    rest = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--home":
            opts["home"] = True
        elif a == "--full":
            opts["full"] = True
        elif a == "--page" and i + 1 < len(argv):
            opts["pages"].append(argv[i + 1])
            i += 1
        elif a == "--max-hits" and i + 1 < len(argv):
            opts["max_hits"] = int(argv[i + 1])
            i += 1
        else:
            rest.append(a)
        i += 1
    if not rest:
        return None, [], opts
    return rest[0], rest[1:], opts


def is_selected(page_url, opts):
    """Whether a crawled page passes the --home / --page filters (no filters: all pages)."""
    if not opts["home"] and not opts["pages"]:
        return True
    if opts["home"] and urlparse(page_url).path in ("", "/"):
        return True
    return any(p in page_url for p in opts["pages"])


def main(url, terms, opts):
    config = load_config()
    validated = validate_company_url(url)
    if validated.status != "ok":
        print("REJECTED:", validated.message)
        return 1
    renderer = render_with_playwright if config["crawl"].get("js_fallback_enabled", False) else None
    crawl = crawl_site(validated.url, validated.approved_domains, config, js_renderer=renderer)
    pages_in_scope = 0
    pages_with_hits = {t: 0 for t in terms}
    for page in crawl.pages:
        if page.status != "ok" or not page.html:
            continue
        if not is_selected(page.url, opts):
            continue
        pages_in_scope += 1
        text = clean_page(page.url, page.html, resolve_char_cap(page.url, config)).text
        norm = normalise(text)
        if opts["full"]:
            print("== FULL CLEANED TEXT:", page.url, "|", len(text), "chars,",
                  "js_rendered" if getattr(page, "js_rendered", False) else "static html")
            print(text)
            print("== END", page.url)
        for term in terms:
            low = term.lower()
            shown = 0
            start = 0
            found_here = False
            while True:
                i = text.lower().find(low, start)
                if i < 0:
                    break
                found_here = True
                if shown < opts["max_hits"]:
                    lo, hi = max(0, i - WINDOW), min(len(text), i + len(term) + WINDOW)
                    print("--", page.url, "| term:", term)
                    print("   raw :", repr(text[lo:hi]))
                    j = norm.find(normalise(term))
                    if j >= 0 and shown == 0:
                        print("   norm:", repr(norm[max(0, j - WINDOW):j + len(term) + WINDOW]))
                    shown += 1
                start = i + len(term)
            if found_here:
                pages_with_hits[term] += 1
    print()
    print(f"SUMMARY: {pages_in_scope} page(s) searched.")
    if pages_in_scope == 0:
        print("  No page matched the --home/--page filter (or none fetched OK).")
    for term in terms:
        n = pages_with_hits[term]
        print(f"  {term!r}: " + (f"found on {n} page(s)" if n else "NOT FOUND on any searched page"))
    return 0


if __name__ == "__main__":
    url, terms, opts = parse_args(sys.argv[1:])
    if url is None or (not terms and not opts["full"]):
        print(__doc__)
        sys.exit(1)
    sys.exit(main(url, terms, opts))
