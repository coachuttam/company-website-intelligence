"""Feed parsing with feedparser (B-104): entries with title, link, published date and summary text."""
from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timezone
from typing import List, NamedTuple, Optional

import feedparser
from bs4 import BeautifulSoup


class Entry(NamedTuple):
    title: str
    link: str
    published: Optional[date]
    summary: str
    feed_title: str


def _text(html: str) -> str:
    return " ".join(BeautifulSoup(html or "", "lxml").get_text(" ").split())


def parse_feed(body: bytes) -> List[Entry]:
    """Every entry of an RSS/Atom feed. A body that is not a feed gives []."""
    parsed = feedparser.parse(body)
    if not parsed.entries:
        return []
    feed_title = _text(parsed.feed.get("title", ""))
    out = []
    for e in parsed.entries:
        stamp = e.get("published_parsed") or e.get("updated_parsed")
        published = (datetime.fromtimestamp(calendar.timegm(stamp), tz=timezone.utc).date() if stamp else None)
        summary = _text(e.get("summary", "") or "")
        out.append(Entry(title=_text(e.get("title", "")), link=(e.get("link") or "").strip(), published=published,
                         summary=re.sub(r"\s+", " ", summary)[:400], feed_title=feed_title))
    return out


def looks_like_feed(content_type: str, body: bytes) -> bool:
    head = body[:500].lstrip().lower()
    return ("rss" in content_type or "atom" in content_type or "xml" in content_type
            or head.startswith(b"<?xml") or b"<rss" in head or b"<feed" in head)
