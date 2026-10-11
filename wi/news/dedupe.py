"""De-duplication (B-104, R-NEWS-004): one item per canonical URL and per normalised headline, so a
post republished under several feed URLs collapses to one event; the earliest dated copy is kept."""
from __future__ import annotations

import re
from datetime import date
from typing import List, Tuple
from urllib.parse import urlsplit

from wi.news.sources.rss import Entry


def canonical_url(url: str) -> str:
    p = urlsplit(url)
    return f"{(p.hostname or '').lower().removeprefix('www.')}{p.path.rstrip('/')}"


def headline_key(title: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", title.casefold()).split())


def dedupe(entries: List[Entry]) -> Tuple[List[Entry], int]:
    """(unique entries, number collapsed). Within a duplicate group the earliest dated copy is kept;
    on a tie, the one without a query string, then the shorter URL."""
    # earliest first; on a tie, the URL without a query string, then the shorter URL
    ordered = sorted(entries, key=lambda e: (e.published or date.max, "?" in e.link, len(e.link), e.link))
    seen_url, seen_head, kept = set(), set(), []
    for e in ordered:
        u, h = canonical_url(e.link), headline_key(e.title)
        if u in seen_url or (h and h in seen_head):
            continue
        seen_url.add(u)
        if h:
            seen_head.add(h)
        kept.append(e)
    return kept, len(entries) - len(kept)
