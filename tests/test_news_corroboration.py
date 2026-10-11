"""B-106: news corroboration, cut line 1 (GDELT headlines + rules; no article fetch, no model call).
A fake HTTP getter only: no network."""
from __future__ import annotations

import json
from datetime import date

import pytest
from pydantic import ValidationError

from wi.news.collect import collect
from wi.news.corroborate import corroborate, entity_match, independent, qualifies
from wi.news.entity import Company
from wi.news.http import Fetcher, Response
from wi.news.schema import Corroboration, NewsItem

TODAY = date(2026, 10, 11)
ACME = Company(company_id="acme_com", name="Acme", domain="acme.com", home_url="https://www.acme.com/")
PRODUCTS = ["Acme Rocket", "Launchpad"]


def _item(event="product_launch", feed="https://www.acme.com/blog/feed", day="2026-10-05", head="Acme launches Rocket 2"):
    return NewsItem(news_id="news_001", company_id="acme_com", source_class="company_announcement", publisher="Acme",
                    url="https://www.acme.com/news/rocket-2", headline=head, published_at=day, retrieved_at="2026-10-11",
                    evidence="x", event_type=event, relevance_status="matched", feed_url=feed)


def _gdelt(articles):
    return Response(200, "application/json", json.dumps({"articles": articles}).encode())


def _art(title, url, domain, seen="20261006T120000Z"):
    return {"title": title, "url": url, "domain": domain, "seendate": seen}


class FakeGet:
    def __init__(self, reply):
        self.reply, self.urls = reply, []

    def __call__(self, url, timeout_s):
        self.urls.append(url)
        if url.startswith("https://api.gdeltproject.org/api/v2/doc/doc"):
            if isinstance(self.reply, Exception):
                raise self.reply
            return self.reply
        return Response(404, "text/plain", b"")


def _run(items, reply):
    get = FakeGet(reply)
    counts = corroborate(items, ACME, PRODUCTS, Fetcher(get=get, sleep=lambda s: None, min_interval_s=0.0,
                                                          host_intervals={}))
    return counts, get


def test_step0_qualifying_rule():
    assert qualifies(_item(event="other", feed="https://www.acme.com/newsroom/rss.xml"))[0]
    assert qualifies(_item(event="other", feed="https://www.acme.com/press-releases/feed"))[0]
    assert qualifies(_item(event="funding", feed="https://www.acme.com/blog/feed"))[0]
    ok, why = qualifies(_item(event="other", feed="https://www.acme.com/blog/feed"))
    assert not ok and "blog" in why


def test_possible_coverage_needs_name_plus_domain_or_product_and_independence():
    items = [_item()]
    counts, _ = _run(items, _gdelt([
        _art("Acme unveils Acme Rocket 2 for small teams", "https://technews.example/acme-rocket", "technews.example"),
        _art("Acme Rocket 2 is here", "https://www.acme.com/blog/x", "acme.com"),                 # company's own
        _art("Acme Rocket 2 ships", "https://www.prnewswire.com/news/acme", "prnewswire.com"),     # press wire
        _art("Acme Corp (Ohio) opens plant", "https://local.example/acme", "local.example"),      # same name, no product
        _art("Acme Launchpad review", "https://old.example/x", "old.example", seen="20260901T000000Z"),  # outside +/-7 days
    ]))
    c = items[0].corroboration
    assert c.status == "possible_coverage" and [s.url for s in c.sources] == ["https://technews.example/acme-rocket"]
    assert c.sources[0].source_class == "third_party_news" and c.sources[0].excerpt is None
    assert counts["candidates_seen"] == 5 and counts["candidates_matched"] == 1


def test_product_without_company_prefix_and_domain_in_title():
    assert entity_match("Acme ships Rocket to everyone", ACME, PRODUCTS)            # "Rocket" from "Acme Rocket"
    assert entity_match("Why Acme (acme.com) matters", ACME, [])
    assert not entity_match("Acme opens a plant", ACME, PRODUCTS)
    assert not entity_match("Rocket and acme.com", ACME, PRODUCTS)                 # name must be a whole phrase
    assert not independent("https://blog.acme.com/x", "blog.acme.com", ACME)


def test_not_corroborated_and_not_checked_paths():
    items = [_item()]
    _run(items, _gdelt([_art("Unrelated story", "https://x.example/a", "x.example")]))
    assert items[0].corroboration.status == "not_corroborated"
    for reply in (Response(503, "text/plain", b""), Response(200, "text/plain", b"Your search was too short"),
                  RuntimeError("boom")):
        items = [_item()]
        counts, _ = _run(items, reply)
        assert items[0].corroboration.status == "not_checked" and counts["gdelt_failures"] == 1
    items = [_item(event="other", feed="https://www.acme.com/blog/feed")]
    counts, get = _run(items, _gdelt([]))
    assert items[0].corroboration.status == "not_checked" and get.urls == [] and counts["items_qualified"] == 0


def test_query_budget():
    items = [_item(head=f"Acme launches thing {i}") for i in range(7)]
    counts, _ = _run(items, _gdelt([]))
    assert counts["gdelt_queries"] == 5
    assert [i.corroboration.status for i in items].count("not_checked") == 2


def test_never_corroborated_or_verified():
    for status in ("corroborated", "verified"):
        with pytest.raises(ValidationError):
            Corroboration(status=status, reason="x")


def test_gdelt_failure_never_breaks_the_snapshot():
    feed = ('<?xml version="1.0"?><rss version="2.0"><channel><title>Acme News</title><item><title>Acme raises $5M</title>'
            '<link>https://www.acme.com/news/raise</link><pubDate>Mon, 05 Oct 2026 10:00:00 GMT</pubDate>'
            '<description>Funding.</description></item></channel></rss>').encode()
    pages = {"https://www.acme.com/": Response(200, "text/html",
             b'<html><head><link rel="alternate" type="application/rss+xml" href="/news/rss.xml"></head></html>'),
             "https://www.acme.com/news/rss.xml": Response(200, "application/rss+xml", feed)}

    def get(url, timeout_s):
        if "gdeltproject" in url:
            raise TimeoutError("GDELT down")
        return pages.get(url, Response(404, "text/html", b""))
    rep = collect(ACME, Fetcher(get=get, sleep=lambda s: None, min_interval_s=0.0, host_intervals={}), today=TODAY)
    assert rep.status == "ok" and rep.items[0].corroboration.status == "not_checked"
    assert rep.record["corroboration"]["gdelt_failures"] == 1 and rep.record["model_calls"] == 0
