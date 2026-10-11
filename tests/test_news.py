"""B-104 and P1 behaviours B-22 to B-25: the company-own news snapshot (wi/news). A fake HTTP getter
only: no network, no model call."""
from __future__ import annotations

import json
from datetime import date

import pytest
from pydantic import ValidationError

from wi.news.classify import event_type
from wi.news.collect import collect, collect_for_run
from wi.news.entity import Company, belongs_to, company_from_run
from wi.news.http import Fetcher, Response
from wi.news.schema import MAX_ITEMS, NewsItem

TODAY = date(2026, 10, 11)
ACME = Company(company_id="acme_com", name="Acme", domain="acme.com", home_url="https://www.acme.com/")
HOME = b'<html><head><link rel="alternate" type="application/rss+xml" href="/news/rss.xml"></head><body>Acme</body></html>'


def _rss(items):
    body = "".join(
        f"<item><title>{t}</title><link>{link}</link>"
        + (f"<pubDate>{d}</pubDate>" if d else "") + (f"<description>{s}</description>" if s else "") + "</item>"
        for t, link, d, s in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>Acme News</title>{body}</channel></rss>'.encode()


def _getter(pages, calls=None):
    def get(url, timeout_s):
        if calls is not None:
            calls.append(url)
        if url in pages:
            return pages[url]
        return Response(404, "text/html", b"")
    return get


def _fetcher(pages, calls=None, sleeps=None):
    return Fetcher(get=_getter(pages, calls), sleep=(sleeps.append if sleeps is not None else (lambda s: None)),
                   min_interval_s=0.0)


def _site(items, extra=None):
    pages = {"https://www.acme.com/": Response(200, "text/html", HOME),
             "https://www.acme.com/news/rss.xml": Response(200, "application/rss+xml", _rss(items))}
    pages.update(extra or {})
    return pages


def test_company_items_within_lookback_are_kept_newest_first():
    rep = collect(ACME, _fetcher(_site([
        ("Acme raises $20M Series B", "https://www.acme.com/news/series-b", "Mon, 05 Oct 2026 10:00:00 GMT", "Acme raised funding."),
        ("Acme launches Rocket 2", "https://www.acme.com/news/rocket-2", "Tue, 01 Sep 2026 10:00:00 GMT", "Now available."),
        ("Old news", "https://www.acme.com/news/old", "Mon, 06 Jul 2026 10:00:00 GMT", "91 days ago."),
        ("No date", "https://www.acme.com/news/undated", None, "Undated."),
    ])), today=TODAY)
    assert rep.status == "ok" and [i.headline for i in rep.items] == ["Acme raises $20M Series B", "Acme launches Rocket 2"]
    assert [i.event_type for i in rep.items] == ["funding", "product_launch"]
    assert rep.record["undated_entries"] == 1 and rep.record["model_calls"] == 0 and rep.record["estimated_cost_usd"] == 0.0
    assert all(i.source_class == "company_announcement" for i in rep.items)


def test_b22_same_name_company_on_another_domain_is_rejected():
    rep = collect(ACME, _fetcher(_site([
        ("Acme Corp (Ohio) opens plant", "https://www.acme-ohio.com/news/plant", "Mon, 05 Oct 2026 10:00:00 GMT", "x"),
        ("Acme ships v3", "https://blog.acme.com/v3", "Mon, 05 Oct 2026 10:00:00 GMT", "Subdomain is ours."),
    ])), today=TODAY)
    assert [i.url for i in rep.items] == ["https://blog.acme.com/v3"] and rep.record["off_domain_entries"] == 1
    assert belongs_to("https://news.acme.com/x", "acme.com") and not belongs_to("https://notacme.com/x", "acme.com")


def test_b23_syndicated_copies_collapse_to_one():
    rep = collect(ACME, _fetcher(_site([
        ("Acme partners with Globex", "https://www.acme.com/news/globex", "Mon, 05 Oct 2026 10:00:00 GMT", "p"),
        ("Acme partners with Globex!", "https://www.acme.com/blog/globex-partnership", "Tue, 06 Oct 2026 10:00:00 GMT", "p"),
        ("Acme partners with Globex", "https://acme.com/news/globex/?utm_source=rss", "Mon, 05 Oct 2026 10:00:00 GMT", "p"),
    ])), today=TODAY)
    assert len(rep.items) == 1 and rep.items[0].url == "https://www.acme.com/news/globex"
    assert rep.record["duplicates_collapsed"] == 2 and rep.items[0].event_type == "partnership"


def test_b24_forced_failure_is_non_blocking(tmp_path):
    class Boom(Fetcher):
        def fetch(self, url):
            raise RuntimeError("forced news failure")
    rep = collect(ACME, Boom(get=_getter({})), today=TODAY)
    assert rep.status == "unavailable" and "forced news failure" in rep.reason and rep.items == []
    run = {"claims": [{"field": "company_identity.name", "status": "extracted", "value": "Acme"}],
           "crawl": {"pages": [{"url": "https://www.acme.com/"}]}}
    run_path = tmp_path / "runs" / "acme_com.json"
    run_path.parent.mkdir()
    run_path.write_text(json.dumps(run))
    before = run_path.read_bytes()
    report, out = collect_for_run(run_path, tmp_path / "news", fetcher=Boom(get=_getter({})), today=TODAY)
    assert run_path.read_bytes() == before and out == tmp_path / "news" / "acme_com.json"
    assert json.loads(out.read_text())["status"] == "unavailable"


def test_b25_never_first_party_or_verified():
    with pytest.raises(ValidationError):
        NewsItem(news_id="n", company_id="c", source_class="first_party", publisher="p", url="u", headline="h",
                 published_at="2026-10-01", retrieved_at="2026-10-11", evidence="e", event_type="other",
                 relevance_status="matched")
    with pytest.raises(ValidationError):
        NewsItem(news_id="n", company_id="c", source_class="company_announcement", publisher="p", url="u",
                 headline="h", published_at="2026-10-01", retrieved_at="2026-10-11", evidence="e",
                 event_type="other", relevance_status="verified")


def test_cap_headline_only_items_and_off_domain_feed():
    items = [(f"Update {i}", f"https://www.acme.com/news/{i}", f"Mon, {i + 1:02d} Oct 2026 10:00:00 GMT", "s" if i else "")
             for i in range(12)]
    home = HOME.replace(b"</head>", b'<link rel="alternate" type="application/rss+xml" href="https://feeds.feedburner.com/acme"></head>')
    rep = collect(ACME, _fetcher(_site(items, {"https://www.acme.com/": Response(200, "text/html", home)})), today=TODAY)
    assert len(rep.items) == MAX_ITEMS
    assert any(s["url"].startswith("https://feeds.feedburner.com") and s["status"] == "skipped" for s in rep.sources)
    rep2 = collect(ACME, _fetcher(_site([("Acme news", "https://www.acme.com/n", "Mon, 05 Oct 2026 10:00:00 GMT", "")])),
                   today=TODAY)
    assert rep2.items[0].relevance_status == "inaccessible" and rep2.items[0].evidence is None


def test_robots_and_blocks_are_respected_without_retry():
    calls = []
    pages = _site([("Acme raises", "https://www.acme.com/news/r", "Mon, 05 Oct 2026 10:00:00 GMT", "x")], {
        "https://www.acme.com/robots.txt": Response(200, "text/plain", b"User-agent: *\nDisallow: /news/\n"),
        "https://www.acme.com/press": Response(403, "text/html", b"")})
    rep = collect(ACME, _fetcher(pages, calls), today=TODAY)
    assert "https://www.acme.com/news/rss.xml" not in calls and rep.status == "not_found"
    assert calls.count("https://www.acme.com/press") == 1
    assert any(s["url"].endswith("/press") and s["reason"] == "HTTP 403" for s in rep.sources)


def test_rate_limit_waits_between_requests_to_one_host():
    sleeps, t = [], [0.0]
    f = Fetcher(get=_getter({"https://www.acme.com/": Response(200, "text/html", b"x")}),
                clock=lambda: t[0], sleep=lambda s: sleeps.append(s), min_interval_s=1.0)
    f.fetch("https://www.acme.com/")
    f.fetch("https://www.acme.com/")
    assert sleeps and all(s > 0 for s in sleeps)


def test_event_type_rules_and_entity_from_run():
    assert event_type("Acme acquires Initech") == "acquisition"
    assert event_type("Acme appoints new CFO") == "leadership_change"
    assert event_type("Quarterly community update") == "other"
    run = {"claims": [{"field": "company_identity.name", "status": "extracted", "value": "Acme"}],
           "crawl": {"pages": [{"url": "https://www.acme.com/en"}]}}
    assert company_from_run(run) == Company("acme_com", "Acme", "acme.com", "https://www.acme.com/")
