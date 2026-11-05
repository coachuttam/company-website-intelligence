#!/usr/bin/env python3
"""Diagnostic only (no LLM call, no scoring, nothing written): crawl each site exactly as
run_site.py does, then show which self-serve and contact-sales cue lines the rule-based detector
(wi.crawl.sales_cues.py, B-61) finds on its pricing pages. Used to judge, before wiring it into
the pipeline, whether the cues are present in the cleaned text and how noisy the lexicons are.

Usage:
    python tools/diagnostics/_diagnostic_sales_cues.py URL [URL ...]
Example:
    python tools/diagnostics/_diagnostic_sales_cues.py https://www.notion.com/ https://www.loom.com/
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from wi.config import load_config
from wi.crawl.clean import clean_page, resolve_char_cap
from wi.crawl.fetch import crawl_site
from wi.crawl.js_fallback import render_with_playwright
from wi.crawl.url import validate_company_url
from wi.crawl.sales_cues import extract_cta_lines, find_sales_cues, is_pricing_page_url


def run_one(url, config):
    validated = validate_company_url(url)
    if validated.status != "ok":
        print("REJECTED:", validated.message)
        return
    renderer = render_with_playwright if config["crawl"].get("js_fallback_enabled", False) else None
    crawl = crawl_site(validated.url, validated.approved_domains, config, js_renderer=renderer)
    print(f"=== {url}  ({len(crawl.pages)} pages crawled)")
    found_pricing_page = False
    site_self, site_contact = [], []
    raw_self, raw_contact = [], []
    for page in crawl.pages:
        if page.status != "ok" or not page.html or not is_pricing_page_url(page.url):
            continue
        found_pricing_page = True
        text = clean_page(page.url, page.html, resolve_char_cap(page.url, config)).text
        cues = find_sales_cues(text)
        print(f"-- {page.url}  ({len(text)} chars)  self-serve={len(cues.self_serve)} contact-sales={len(cues.contact_sales)}")
        for line in cues.self_serve:
            print("     self-serve  :", repr(line))
        for line in cues.contact_sales:
            print("     contact-sales:", repr(line))
        # Same detector, run on the RAW page's button/link labels instead of the cleaned text.
        raw_cues = find_sales_cues("\n".join(extract_cta_lines(page.html)))
        print(f"     raw HTML buttons/links: self-serve={len(raw_cues.self_serve)} contact-sales={len(raw_cues.contact_sales)}")
        for line in raw_cues.self_serve:
            print("     RAW self-serve   :", repr(line))
        for line in raw_cues.contact_sales:
            print("     RAW contact-sales:", repr(line))
        site_self += cues.self_serve
        site_contact += cues.contact_sales
        raw_self += raw_cues.self_serve
        raw_contact += raw_cues.contact_sales
    if not found_pricing_page:
        print("   (no pricing-style page was crawled)")
    verdict = "HYBRID" if site_self and site_contact else ("self-serve only" if site_self else
                                                            ("contact-sales only" if site_contact else "no cues"))
    raw_verdict = "HYBRID" if raw_self and raw_contact else ("self-serve only" if raw_self else
                                                              ("contact-sales only" if raw_contact else "no cues"))
    print(f"   RESULT for {url}: cleaned text -> {verdict}; raw buttons/links -> {raw_verdict}\n")


def main(urls):
    config = load_config()
    for u in urls:
        run_one(u, config)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    sys.exit(main(sys.argv[1:]))
