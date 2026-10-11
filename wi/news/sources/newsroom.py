"""The company's own newsroom feeds (B-104): feed links advertised on the homepage and on common
newsroom pages, plus common feed paths, all on the company's own domain. At most MAX_PAGES discovery
pages and MAX_FEEDS feed fetches per company; robots.txt and per-host rate limits via news.http."""
from __future__ import annotations

from typing import List, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from wi.news.entity import Company, belongs_to
from wi.news.http import Fetcher
from wi.news.sources.rss import Entry, looks_like_feed, parse_feed

NEWSROOM_PATHS = ("/news", "/newsroom", "/press", "/blog")
FEED_PATHS = ("/feed", "/rss.xml", "/feed.xml", "/blog/rss.xml", "/news/rss.xml", "/blog/feed")
FEED_TYPES = ("application/rss+xml", "application/atom+xml")
MAX_PAGES = 5
MAX_FEEDS = 6


def feed_links(html: str, base: str) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    out = []
    for link in soup.find_all("link"):
        rel = [r.lower() for r in (link.get("rel") or [])]
        if "alternate" in rel and (link.get("type") or "").lower() in FEED_TYPES and link.get("href"):
            out.append(urljoin(base, link["href"]))
    return out


def discover_and_read(company: Company, fetcher: Fetcher, deadline_ok) -> Tuple[List[Entry], List[dict]]:
    """(entries from every feed found on the company's domain, a log of every URL tried)."""
    log, candidates = [], []
    for path in ("/",) + NEWSROOM_PATHS:
        if len([x for x in log if x["kind"] == "page"]) >= MAX_PAGES or not deadline_ok():
            break
        url = urljoin(company.home_url, path)
        r, reason = fetcher.fetch(url)
        log.append({"url": url, "kind": "page", "status": "ok" if r else "skipped", "reason": reason})
        if r is not None and "html" in r.content_type:
            for f in feed_links(r.body.decode("utf-8", "replace"), url):
                if not belongs_to(f, company.domain):
                    log.append({"url": f, "kind": "feed", "status": "skipped",
                                "reason": "feed not on the company's domain (third-party sources out of scope)"})
                elif f not in candidates:
                    candidates.append(f)
    for path in FEED_PATHS:
        url = urljoin(company.home_url, path)
        if url not in candidates:
            candidates.append(url)
    entries = []
    for url in candidates[:MAX_FEEDS]:
        if not deadline_ok():
            log.append({"url": url, "kind": "feed", "status": "skipped", "reason": "news time budget used up"})
            continue
        r, reason = fetcher.fetch(url)
        if r is None or not looks_like_feed(r.content_type, r.body):
            log.append({"url": url, "kind": "feed", "status": "skipped", "reason": reason if r is None else "not a feed"})
            continue
        found = parse_feed(r.body, url)
        log.append({"url": url, "kind": "feed", "status": "ok", "reason": f"{len(found)} entries"})
        entries.extend(found)
    return entries, log
