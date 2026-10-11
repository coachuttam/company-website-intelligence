"""A small polite fetcher for the news collector (B-104): robots.txt per origin, one request per second
per host, a per-request timeout, and the crawler's user agent and block detection. Separate from
wi/crawl/fetch.py's fetch_page(), which by design refuses feed content types."""
from __future__ import annotations

import time
import urllib.robotparser
from typing import Callable, Dict, NamedTuple, Optional
from urllib.parse import urljoin, urlsplit

from wi.crawl.fetch import USER_AGENT, detect_challenge


class Response(NamedTuple):
    status: int
    content_type: str
    body: bytes


Getter = Callable[[str, float], Response]   # (url, timeout_s) -> Response; raises on network error


def httpx_getter(url: str, timeout_s: float) -> Response:
    import httpx
    r = httpx.get(url, timeout=timeout_s, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
    return Response(r.status_code, r.headers.get("content-type", ""), r.content[:2_000_000])


class Fetcher:
    def __init__(self, get: Getter = httpx_getter, timeout_s: float = 15.0,
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep,
                 min_interval_s: float = 1.0, host_intervals: Optional[Dict[str, float]] = None):
        self._get, self._timeout, self._clock, self._sleep = get, timeout_s, clock, sleep
        self._interval = min_interval_s
        self._host_intervals = dict(host_intervals if host_intervals is not None
                                    else {"api.gdeltproject.org": 5.0})
        self._robots: Dict[str, urllib.robotparser.RobotFileParser] = {}
        self._last: Dict[str, float] = {}

    def _wait(self, host: str) -> None:
        last = self._last.get(host)
        interval = self._host_intervals.get(host, self._interval)
        if last is not None:
            gap = self._clock() - last
            if gap < interval:
                self._sleep(interval - gap)
        self._last[host] = self._clock()

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                self._wait(parts.netloc)
                r = self._get(urljoin(origin, "/robots.txt"), self._timeout)
                rp.parse(r.body.decode("utf-8", "replace").splitlines() if r.status == 200 else [])
            except Exception:
                rp.parse([])
            self._robots[origin] = rp
        return self._robots[origin].can_fetch(USER_AGENT, url)

    def fetch(self, url: str) -> tuple:
        """(Response or None, reason). Never raises; a block or robots refusal is a reason, never retried."""
        if not self.allowed(url):
            return None, "robots.txt disallows"
        try:
            self._wait(urlsplit(url).netloc)
            r = self._get(url, self._timeout)
        except Exception as e:
            return None, f"{type(e).__name__}"
        if r.status in (401, 403, 429) or r.status >= 400:
            return None, f"HTTP {r.status}"
        if "html" in r.content_type and detect_challenge(r.body.decode("utf-8", "replace")):
            return None, "bot challenge page"
        return r, "ok"
