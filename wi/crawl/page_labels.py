"""Logo/image labels and homepage navigation text for the cleaned page (B-100, 2026-10-11).

WHY. The held-out v2 diagnosis (eval/HELDOUT_V2_REPORT.md, section 4) found that in 8 of the 25 fields
the model returned as not_found, the label's text was on a crawled page but the cleaner (trafilatura)
had removed it: industry and solution menus, footer "Compare" columns, and partner or customer names
that exist only as image alt text. Homepages kept 1.5k to 5k characters out of 0.3 to 1.9 MB of HTML.

DESIGN.
1. Image labels, from the main content only. Collected from <img alt>, aria-label on
   <svg>/<img>/<a>, and the title attribute of a logo-like element (an <img>/<svg>, or an element
   whose direct child is one: the "title on the logo's wrapper" pattern). Skipped: anything inside
   <nav>, <header>, <footer> or an element with role navigation, banner or contentinfo (site chrome
   that repeats on every page: app-store and browser icons, social links, menu controls); anything
   inside <script>, <style>, <noscript>, <template> or a cookie/consent container; 1x1 tracking
   images.
   A label is kept only if it:
     - is 2 to 60 characters and has a letter;
     - is not a file name (image or document extension) or a slug (lowercase tokens joined by "_"
       or "-", e.g. "image_28", "unext_logo", "ozonetel-1");
     - still has 2+ characters after a trailing generic word (logo, icon, image, badge) is stripped
       ("Publix Logo" -> "Publix");
     - is not a generic word (logo, image, icon, arrow, ...);
     - does not start with an interface prefix ("open ", "close ", "link to ", "back to ", "go to ",
       "skip to ", "download on", "get it on", "available on");
     - does not contain a store, cookie or consent phrase ("app store", "google play", "cookie",
       "consent", "privacy settings", "manage preferences");
     - is not a browser or platform name standing alone (chrome, firefox, safari, edge, outlook,
       android, ios).
   Duplicates are dropped after casefolding, at most 60 labels per page.
   Block: one line, "[logo and image labels] name1 | name2 | ...".
2. Site-wide first occurrence. A label is kept only on the first page where it appears; later pages
   drop it. "First" means the pipeline's page order: the order of the crawl result's pages, which is
   the crawler's dequeue order (fetching is sequential, so it does not depend on fetch timing).
   run_site.py cleans the pages in that order and passes one per-run set (`seen_labels`) to every
   clean_page() call. A caller that cleans a single page on its own passes no set, and the page keeps
   its own labels (no cross-page step). The result is part of each page's clean text, so the run
   fingerprint (cache key) and the B-88 snapshot simply see that text; their formats are unchanged.
3. Navigation, homepage only (the shortest-path page of the site, chosen by the caller). The visible
   text of links inside <nav>, <header> and <footer>, in document order, de-duplicated after
   casefolding, 2 to 60 characters, at most 150 items. Dropped:
     - punctuation-only texts;
     - a single generic word (login, sign in, sign up, menu, close, contact, home);
     - items containing a cookie or consent phrase;
     - items starting with "open " or "link to ".
   Other pages get no navigation block: it repeats on every page and would only add noise.
   Block: one line, "[site navigation] item1 | item2 | ...".
4. Budgets. Both blocks are appended after the main content, AFTER clean_page() has applied
   max_clean_chars to it, each with its own fixed budget (6,000 characters), so they never push
   main content out. A block that would exceed its budget stops at the last whole item that fits.
   A page with no qualifying label (and, for the homepage, no navigation) is unchanged.
5. Evidence gate, unchanged. wi/extract/pipeline.py builds the text the gate searches from
   CleanPage.text (plus the title), and the blocks are part of CleanPage.text, so a quote taken from
   a block ("Publix", or "Industries | Retail") is found as page text exactly like body text.
6. Interactions. main_text(), which the crawl hashes to spot duplicate pages (B-75), is unchanged.
   EXTRACTION_LOGIC_VERSION is bumped (27 on this branch) so cached results from the old cleaner are
   not reused. The prompt is unchanged: each block is a plainly labelled line, and the existing
   rules apply to it as to any page text. Whether the model needs a sentence about the blocks cannot
   be checked without model calls; adding one would also change prompt_version for every site.
7. Risks. More candidate names can lead the model to list decorative logos, investor or press logos
   as customers, or nav items as products. The gate only checks that the quote exists, so it does
   not stop this (see docs/KNOWN_LIMITATIONS.md); the prompt's field rules and the labelling guide's
   Decisions (a) to (d) are the limits. To measure: unsupported and incorrect counts on
   named_customers, partnerships, products.names and certifications against a back-to-back control.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Optional, Set, Tuple
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag

LABELS_HEADER = "[logo and image labels]"
NAV_HEADER = "[site navigation]"
LABELS_BUDGET = 6000
NAV_BUDGET = 6000
MAX_LABELS = 60
MAX_NAV_ITEMS = 150
MIN_CHARS, MAX_CHARS = 2, 60

GENERIC_LABELS = frozenset({
    "logo", "image", "icon", "arrow", "avatar", "photo", "picture", "banner", "background",
    "placeholder", "testimonial media", "close", "menu", "search", "globe", "flag", "tick", "prev",
    "next",
})
UI_PREFIXES = ("open ", "close ", "link to ", "back to ", "go to ", "skip to ", "download on",
               "get it on", "available on")
STORE_CONSENT_PHRASES = ("app store", "google play", "cookie", "cookies", "consent", "privacy settings",
                         "manage preferences")
COOKIE_CONSENT_PHRASES = ("cookie", "cookies", "consent", "privacy settings", "manage preferences")
STANDALONE_PLATFORMS = frozenset({"chrome", "firefox", "safari", "edge", "outlook", "android", "ios"})
TRAILING_GENERIC = re.compile(r"[\s_-]+(logo|icon|image|badge)s?$", re.IGNORECASE)
FILE_EXTENSION = re.compile(r"\.(png|jpe?g|gif|svg|webp|avif|bmp|ico|tiff?|pdf)$", re.IGNORECASE)
SLUG = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)+$")
GENERIC_NAV = frozenset({"login", "log in", "sign in", "sign up", "menu", "close", "contact", "home"})
NAV_DROP_PREFIXES = ("open ", "link to ")
_SKIP_TAGS = ("script", "style", "noscript", "template")
_CHROME_TAGS = ("nav", "header", "footer")
_CHROME_ROLES = ("navigation", "banner", "contentinfo")
_CONSENT = re.compile(r"cookie|consent|onetrust|cookiebot|cc-window|cc-banner", re.IGNORECASE)
_IMAGE_TAGS = ("img", "svg")

# reasons a candidate label was dropped, for the before/after report
REASONS = ("site_chrome", "length", "no_letter", "file_name", "slug", "empty_after_strip", "generic",
           "ui_prefix", "store_or_consent", "platform_word", "duplicate", "seen_on_earlier_page", "cap")


def _norm(text: str) -> str:
    return " ".join((text or "").split())


def filter_label(raw: str) -> Tuple[Optional[str], Optional[str]]:
    """(kept label, None) or (None, reason) for one candidate label."""
    text = _norm(raw)
    if not MIN_CHARS <= len(text) <= MAX_CHARS:
        return None, "length"
    if not re.search(r"[^\W\d_]", text):
        return None, "no_letter"
    if FILE_EXTENSION.search(text):
        return None, "file_name"
    if SLUG.match(text):
        return None, "slug"
    stripped = TRAILING_GENERIC.sub("", text).strip()
    if len(stripped) < MIN_CHARS:
        return None, "empty_after_strip"
    low = stripped.casefold()
    if low in GENERIC_LABELS:
        return None, "generic"
    if low.startswith(UI_PREFIXES):
        return None, "ui_prefix"
    if any(p in low for p in STORE_CONSENT_PHRASES):
        return None, "store_or_consent"
    if low in STANDALONE_PLATFORMS:
        return None, "platform_word"
    return stripped, None


def _ancestors(el: Tag) -> Iterable[Tag]:
    for anc in [el, *el.parents]:
        if isinstance(anc, Tag):
            yield anc


def _skipped(el: Tag) -> bool:
    for anc in _ancestors(el):
        if anc.name in _SKIP_TAGS:
            return True
        marker = " ".join([anc.get("id") or "", *(anc.get("class") or [])])
        if marker and _CONSENT.search(marker):
            return True
    return False


def _in_site_chrome(el: Tag) -> bool:
    return any(anc.name in _CHROME_TAGS or (anc.get("role") or "").lower() in _CHROME_ROLES
               for anc in _ancestors(el))


def _tracking_pixel(el: Tag) -> bool:
    return el.name == "img" and str(el.get("width", "")).strip() in ("0", "1") \
        and str(el.get("height", "")).strip() in ("0", "1")


def _candidates(soup: BeautifulSoup, stats: Optional[dict]) -> Iterable[str]:
    for el in soup.find_all(True):
        found = []
        if el.name == "img" and el.get("alt"):
            found.append(el["alt"])
        if el.name in ("svg", "img", "a") and el.get("aria-label"):
            found.append(el["aria-label"])
        if el.get("title") and (el.name in _IMAGE_TAGS or
                                any(isinstance(c, Tag) and c.name in _IMAGE_TAGS for c in el.children)):
            found.append(el["title"])
        if not found or _tracking_pixel(el) or _skipped(el):
            continue
        if _in_site_chrome(el):
            if stats is not None:
                stats["site_chrome"] = stats.get("site_chrome", 0) + len(found)
            continue
        yield from found


def _join(header: str, items: List[str], budget: int) -> str:
    line = header
    for item in items:
        nxt = f"{line} {item}" if line == header else f"{line} | {item}"
        if len(nxt) > budget:
            break
        line = nxt
    return line if line != header else ""


def image_labels(html: str, stats: Optional[dict] = None, seen: Optional[Set[str]] = None) -> List[str]:
    """Kept labels for one page, in document order. `seen` is the per-run set of labels already kept
    on earlier pages (site-wide first occurrence); kept labels are added to it."""
    soup = BeautifulSoup(html, "lxml")
    kept, here = [], set()
    for raw in _candidates(soup, stats):
        label, reason = filter_label(raw)
        if label is not None and label.casefold() in here:
            label, reason = None, "duplicate"
        if label is not None and seen is not None and label.casefold() in seen:
            label, reason = None, "seen_on_earlier_page"
        if label is not None and len(kept) >= MAX_LABELS:
            label, reason = None, "cap"
        if label is None:
            if stats is not None:
                stats[reason] = stats.get(reason, 0) + 1
            continue
        here.add(label.casefold())
        kept.append(label)
    if seen is not None:
        seen.update(here)
    return kept


def labels_block(html: str, stats: Optional[dict] = None, seen: Optional[Set[str]] = None) -> str:
    return _join(LABELS_HEADER, image_labels(html, stats, seen), LABELS_BUDGET)


def nav_items(html: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    items, seen = [], set()
    for region in soup.find_all(["nav", "header", "footer"]):
        if _skipped(region):
            continue
        for a in region.find_all("a"):
            text = _norm(a.get_text(" "))
            key = text.casefold()
            if not MIN_CHARS <= len(text) <= MAX_CHARS or not re.search(r"[^\W_]", text):
                continue
            if key in GENERIC_NAV or key in seen or key.startswith(NAV_DROP_PREFIXES):
                continue
            if any(p in key for p in COOKIE_CONSENT_PHRASES):
                continue
            seen.add(key)
            items.append(text)
            if len(items) >= MAX_NAV_ITEMS:
                return items
    return items


def nav_block(html: str) -> str:
    return _join(NAV_HEADER, nav_items(html), NAV_BUDGET)


def homepage_url(urls: Iterable[str]) -> Optional[str]:
    """The site's homepage for the navigation block: the URL with the shortest path, then the
    alphabetically first URL."""
    urls = list(urls)
    return min(urls, key=lambda u: (len(urlsplit(u).path or "/"), u)) if urls else None
