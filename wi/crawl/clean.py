"""Boilerplate removal (PRD Section 7): turns raw HTML into the clean text the
LLM actually reads. Trafilatura does the real work (nav, footer, cookie banners
stripped). BeautifulSoup is the fallback for pages trafilatura can't parse --
returning nothing would be worse than a rough fallback, since a page with zero
clean text can't produce any claims at all, extracted or not_found-with-coverage.
The raw HTML from fetch.py is kept separately as the ground truth for
wi/validate/evidence.py; this module only produces what the model reads.

Always keep the page's <h1> (decided 2026-09-24): real bug found live on basecamp.com --
its actual tagline, "Basecamp is project management without all the nonsense. Rock solid
and famously easy to use.", is a plain <h1>, genuinely on the page, yet trafilatura's
main-content heuristics dropped it from every cleaned run today (most likely because it
sits in a hero/<header>-style container that gets treated like navigation chrome). No
prompt wording can fix this -- the text never reached the model at all, so it could never
be quoted no matter how the extraction prompt was worded (see wi/extract/prompt.py rule 3:
evidence has to be real page text). An <h1> is headline content by definition, never
boilerplate, so it's always folded back in if trafilatura's own extraction dropped it.

resolve_char_cap() (decided 2026-09-22): a flat max_clean_chars for every page was costing us
real content. On the basecamp.com run, /customers and /support/testimonials both got truncated
at 12,000 chars before reaching the named-customer text further down the page, while pages far
less likely to hold schema-relevant facts (guides, blog-style posts) got the same allowance.
Rather than raise the cap for every page -- which would just burn more of the token budget
across the board (we were already at 78% of it on a single 25-page site) -- pages whose URL
looks like it holds named entities (customers, testimonials, pricing, partners,
certifications, about/team) get a higher cap; everything else keeps the default. This is a URL
heuristic, not a guarantee: config.yaml's crawl.priority_url_keywords is the tunable list.

Always keep a postal-address-shaped block (decided 2026-09-27, the held-out company_identity.
headquarters investigation): confirmed live on two real pages -- razorpay.com/about (the full
street address sits in an "Our Workspaces" section AND, more fully, in a "REGD. OFFICE ADDRESS"
footer box) and gong.io/about (a "Gongsters around the globe" card-style office-locations list,
positioned in the main body before the footer nav) -- that a company's own real, on-topic
mailing address regularly gets dropped by trafilatura's main-content heuristics, the exact same
failure class the <h1> fix above already exists for: real, non-boilerplate content that happens
to sit inside a <footer>, or a card/list layout trafilatura mistakes for chrome. No prompt
wording can fix this either -- the text never reaches the model, so it can never be quoted (rule
3 in wi/extract/prompt.py). Unlike the <h1> fix, this one deliberately does NOT restrict itself
to any single tag: a "Regd. Office" box is exactly the kind of content a <footer> legitimately
holds alongside real boilerplate, so the search below covers the whole document, footer
included. To stay conservative -- this must not start folding in unrelated numbers or street
names mentioned in passing -- a block only counts as address-shaped when it is short (see
_ADDRESS_MAX_BLOCK_CHARS) AND contains BOTH a common street-suffix word (Street, Road, Floor,
Suite, and similar) AND a postal/zip-code-shaped token (US ZIP, Indian PIN, or Canadian
postcode); an explicit <address> tag is trusted on its own, since using that tag is itself a
deliberate authoring signal. Among several matching blocks, the shortest one wins, on the
reasoning that the smallest enclosing element is the most likely to be the address itself
rather than a larger wrapper that merely contains one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urlsplit

import trafilatura
from bs4 import BeautifulSoup

from wi.crawl.sales_cues import cue_block_for_html, is_pricing_page_url

_ADDRESS_STREET_WORDS = re.compile(
    r"\b(street|st\.|road|rd\.|avenue|ave\.|boulevard|blvd\.|drive|dr\.|lane|floor|suite|"
    r"ste\.|building|tower|plaza|way|highway)\b", re.IGNORECASE,
)
_ADDRESS_POSTAL_CODE = re.compile(
    r"\b\d{5}(-\d{4})?\b"                      # US ZIP / ZIP+4
    r"|\b\d{6}\b"                                # Indian PIN code
    r"|\b[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d\b"    # Canadian postal code
)
_ADDRESS_MAX_BLOCK_CHARS = 300  # a real address is short; rules out a whole page matching


@dataclass
class CleanPage:
    url: str
    title: Optional[str]
    text: str
    truncated: bool = False


def extract_fallback_text(html: str) -> str:
    """Strips script/style/nav/header/footer/noscript and returns the remaining visible text,
    joined on single spaces. Promoted to a public name (2026-09-26, alongside fetch.py's
    normalize_url) so wi/crawl/js_fallback.py's needs_fallback() can reuse this exact
    definition instead of maintaining its own copy -- which had silently drifted (missing
    nav/header/footer) and was undercounting boilerplate-heavy SPA shells like darwinbox.com
    as if they had real content, so the JS fallback never triggered. `_fallback_text` is kept
    as an alias below for any existing internal callers/imports."""
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ").split())


_fallback_text = extract_fallback_text


def _title(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    return h1.get_text(strip=True) if h1 else None


def _h1_text(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "lxml")
    h1 = soup.find("h1")
    if not h1:
        return None
    text = " ".join(h1.get_text(separator=" ").split())
    return text or None


def _address_text(html: str) -> Optional[str]:
    """Finds the smallest element that looks like a postal address: either an explicit
    <address> tag, or a short block of text (see _ADDRESS_MAX_BLOCK_CHARS) containing both a
    common street-suffix word and a postal/zip-code-shaped token. Both signals are required and
    the block must be short, so this doesn't fire on an unrelated page that merely mentions a
    street name or a five-digit number in passing. Searches the WHOLE document, footer and
    header included -- see the module docstring for why. Returns the shortest match found among
    every element checked, or None if nothing matches."""
    soup = BeautifulSoup(html, "lxml")

    explicit = soup.find("address")
    if explicit:
        text = " ".join(explicit.get_text(separator=" ").split())
        if text:
            return text

    candidates = []
    for tag in soup.find_all(["p", "div", "li", "span"]):
        text = " ".join(tag.get_text(separator=" ").split())
        if not text or len(text) > _ADDRESS_MAX_BLOCK_CHARS:
            continue
        if _ADDRESS_STREET_WORDS.search(text) and _ADDRESS_POSTAL_CODE.search(text):
            candidates.append(text)
    if not candidates:
        return None
    return min(candidates, key=len)


def clean_page(url: str, html: str, max_clean_chars: int) -> CleanPage:
    text = trafilatura.extract(html, url=url, include_tables=True, include_links=False) or ""
    if not text.strip():
        text = _fallback_text(html)

    # See module docstring: trafilatura sometimes drops a real <h1> as if it were boilerplate
    # (e.g. a hero tagline inside a <header> container). Fold it back in at the front if so.
    h1 = _h1_text(html)
    if h1 and h1 not in text:
        text = h1 + "\n" + text

    # See module docstring: a real postal address regularly sits in a <footer> "Regd. Office"
    # box or a card-style locations list, and gets dropped the same way. Fold it back in too.
    address = _address_text(html)
    if address and address not in text:
        text = text + "\n" + address

    truncated = len(text) > max_clean_chars
    if truncated:
        text = text[:max_clean_chars]

    # See wi/crawl/sales_cues.py: trafilatura drops button/link labels, so a pricing page's
    # "Get started" / "Contact sales" call-to-actions never reach the model or the evidence gate.
    # Appended AFTER truncation (a few short lines) so a long page cannot cut them off.
    if is_pricing_page_url(url):
        cue_block = cue_block_for_html(html)
        if cue_block:
            text = text + "\n" + cue_block

    return CleanPage(url=url, title=_title(html), text=text, truncated=truncated)


def is_priority_url(url: str, keywords: List[str]) -> bool:
    """True if the URL's path looks like it holds named entities (customers, testimonials,
    pricing, etc.) worth a bigger character allowance. Checked on the URL path only -- the
    page's own title/text aren't known yet at this point in the pipeline."""
    path = urlsplit(url).path.lower()
    return any(kw.lower() in path for kw in keywords)


def resolve_char_cap(url: str, config: dict) -> int:
    """The character cap to hand clean_page() for this particular URL: config.yaml's
    crawl.priority_max_clean_chars for a page matching crawl.priority_url_keywords, otherwise
    the default crawl.max_clean_chars. Falls back to the default cap if either priority setting
    is missing from config, so older configs without them still work."""
    crawl_cfg = config.get("crawl", {})
    default_cap = crawl_cfg["max_clean_chars"]
    priority_cap = crawl_cfg.get("priority_max_clean_chars", default_cap)
    keywords = crawl_cfg.get("priority_url_keywords", [])
    if keywords and is_priority_url(url, keywords):
        return priority_cap
    return default_cap
