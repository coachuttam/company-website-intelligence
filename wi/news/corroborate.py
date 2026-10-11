"""Corroboration, cut line 1 (B-106; PRD Section 8): for each qualifying company announcement, search
GDELT for independent coverage and match on titles by rules only. No article is fetched and no model is
called, so the strongest status is "possible_coverage"; nothing is ever "corroborated" or "verified".

Rules, fixed before any result was seen:
  Step 0, which items qualify: the item's feed URL path contains news, newsroom, press,
    press-releases or media, OR its rule-based event type is not "other". Others are not_checked.
  A GDELT headline is a candidate only if ALL hold:
    - entity: the company name appears as a whole phrase in the headline, AND the headline also has
      the company's domain or one of its product names (from the profile; a product name may also
      match without the company-name prefix when the remainder is at least 4 characters);
    - independence: the article is not on the company's domain or a subdomain, and not on a
      press-release wire (company-distributed text, not independent coverage);
    - event: the article is dated within +/-7 days of the announcement.
  Statuses: possible_coverage (at least one candidate), not_corroborated (GDELT answered, no
  candidate), not_checked (not qualifying, GDELT failed, or the budget ran out).
Budgets: at most MAX_QUERIES GDELT queries and TIME_BUDGET_S seconds per company. Never raises.
"""
from __future__ import annotations

import re
import time
from datetime import date
from typing import Callable, List, Optional, Tuple
from urllib.parse import urlsplit

from wi.news.entity import Company, belongs_to
from wi.news.http import Fetcher
from wi.news.schema import Corroboration, CoverageSource, NewsItem
from wi.news.sources import gdelt

QUALIFYING_FEED_WORDS = ("news", "newsroom", "press", "press-releases", "media")
PRESS_WIRES = ("prnewswire.com", "businesswire.com", "globenewswire.com", "accesswire.com", "einpresswire.com",
               "newswire.com", "prweb.com", "openpr.com", "issuewire.com", "einnews.com")
EVENT_WINDOW_DAYS = 7
MAX_QUERIES = 5
TIME_BUDGET_S = 120.0
MIN_PRODUCT_REMAINDER = 4


def qualifies(item: NewsItem) -> Tuple[bool, str]:
    path = urlsplit(item.feed_url or "").path.lower()
    words = set(re.split(r"[/_.-]+", path))
    if words & set(QUALIFYING_FEED_WORDS) or "press-releases" in path:
        return True, "newsroom/press feed"
    if item.event_type != "other":
        return True, f"event type {item.event_type}"
    return False, "blog/article item (feed is not a newsroom feed and event type is other)"


def _phrase(text: str, phrase: str) -> bool:
    return bool(phrase) and re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, re.IGNORECASE) is not None


def product_terms(company: Company, products: List[str]) -> List[str]:
    terms = []
    for p in products:
        p = " ".join(str(p).split())
        if p:
            terms.append(p)
            rest = re.sub(r"^" + re.escape(company.name) + r"\s+", "", p, flags=re.IGNORECASE)
            if rest != p and len(rest) >= MIN_PRODUCT_REMAINDER:
                terms.append(rest)
    return terms


def entity_match(title: str, company: Company, products: List[str]) -> bool:
    # the name must appear on its own, not only inside the domain ("acme.com" is not the name "Acme")
    without_domain = re.sub(r"(?<![\w.])(?:www\.)?" + re.escape(company.domain) + r"(?![\w])", " ", title,
                            flags=re.IGNORECASE)
    if not _phrase(without_domain, company.name):
        return False
    return _phrase(title, company.domain) or any(_phrase(title, t) for t in product_terms(company, products))


def independent(article_url: str, domain: str, company: Company) -> bool:
    if belongs_to(article_url, company.domain):
        return False
    d = (domain or urlsplit(article_url).hostname or "").lower()
    return not any(d == w or d.endswith("." + w) for w in PRESS_WIRES)


def corroborate(items: List[NewsItem], company: Company, products: List[str], fetcher: Fetcher,
                clock: Callable[[], float] = time.monotonic) -> dict:
    """Sets item.corroboration on every item; returns counts for the report's record."""
    started = clock()
    counts = {"items_qualified": 0, "gdelt_queries": 0, "gdelt_failures": 0, "candidates_seen": 0,
              "candidates_matched": 0}
    for item in items:
        ok, why = qualifies(item)
        if not ok:
            item.corroboration = Corroboration(status="not_checked", reason=why)
            continue
        counts["items_qualified"] += 1
        if counts["gdelt_queries"] >= MAX_QUERIES or clock() - started >= TIME_BUDGET_S:
            item.corroboration = Corroboration(status="not_checked", reason="corroboration budget used up")
            continue
        try:
            around = date.fromisoformat(item.published_at)
            counts["gdelt_queries"] += 1
            articles, reason = gdelt.search(fetcher, company.name, around)
        except Exception as e:   # never breaks the snapshot
            articles, reason = None, f"{type(e).__name__}"
        if articles is None:
            counts["gdelt_failures"] += 1
            item.corroboration = Corroboration(status="not_checked", reason=reason)
            continue
        counts["candidates_seen"] += len(articles)
        sources = []
        for a in articles:
            if not (a.published and abs((a.published - around).days) <= EVENT_WINDOW_DAYS):
                continue
            if not independent(a.url, a.domain, company) or not entity_match(a.title, company, products):
                continue
            sources.append(CoverageSource(publisher=a.domain or (urlsplit(a.url).hostname or ""), url=a.url,
                                          published_at=a.published.isoformat(), headline=a.title))
        counts["candidates_matched"] += len(sources)
        item.corroboration = (
            Corroboration(status="possible_coverage", sources=sources[:5],
                          reason="independent headline(s) name the company and its domain or a product; "
                                 "article text not checked (cut line 1)")
            if sources else
            Corroboration(status="not_corroborated", reason=f"GDELT gave {len(articles)} article(s); none matched the rules"))
    return counts
