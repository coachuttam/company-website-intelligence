"""GDELT DOC 2.0 article search (B-106, cut line 1): headlines only, no article fetching.
https://api.gdeltproject.org/api/v2/doc/doc?query=...&mode=ArtList&format=json. One query per qualifying
announcement, at most one request every 5 seconds (news.http host interval), robots.txt respected."""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import List, NamedTuple, Optional, Tuple
from urllib.parse import urlencode

from wi.news.http import Fetcher

API = "https://api.gdeltproject.org/api/v2/doc/doc"
MAX_RECORDS = 75


class Article(NamedTuple):
    url: str
    title: str
    domain: str
    published: Optional[date]


def query_url(company_name: str, around: date, days: int = 7) -> str:
    start = datetime.combine(around - timedelta(days=days), datetime.min.time())
    end = datetime.combine(around + timedelta(days=days), datetime.max.time())
    params = {"query": f'"{company_name}" sourcelang:english', "mode": "ArtList", "format": "json",
              "maxrecords": MAX_RECORDS, "sort": "DateDesc",
              "startdatetime": start.strftime("%Y%m%d%H%M%S"), "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    return API + "?" + urlencode(params)


def search(fetcher: Fetcher, company_name: str, around: date) -> Tuple[Optional[List[Article]], str]:
    """(articles, "ok") or (None, reason). Never raises; a non-JSON reply (GDELT's text errors) is a failure."""
    r, reason = fetcher.fetch(query_url(company_name, around))
    if r is None:
        return None, f"GDELT unavailable: {reason}"
    try:
        data = json.loads(r.body.decode("utf-8", "replace") or "{}")
    except ValueError:
        return None, "GDELT returned no JSON: " + r.body[:80].decode("utf-8", "replace").strip()
    out = []
    for a in data.get("articles") or []:
        seen = (a.get("seendate") or "")[:8]
        try:
            published = datetime.strptime(seen, "%Y%m%d").date() if seen else None
        except ValueError:
            published = None
        out.append(Article(url=a.get("url") or "", title=" ".join((a.get("title") or "").split()),
                           domain=(a.get("domain") or "").lower(), published=published))
    return out, "ok"
