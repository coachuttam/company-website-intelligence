"""B-105: the rendered page's separate news section (wi/render/page.py). Fixtures only, no model call."""
from __future__ import annotations

import json

from wi.render.page import NEWS_TITLE, esc, render_file, render_profile_html

TITLE = esc(NEWS_TITLE)   # as it appears in the HTML

RUN = {"schema_version": "schema-v1", "crawl_status": "ok", "claims": [],
       "profile": {"company_identity": {"name": {"value": "Acme", "status": "extracted"}}, "coverage": {},
                   "gaps_conflicts": []},
       "crawl": {"pages": [{"url": "https://www.acme.com/"}]}}
NEWS_OK = {"status": "ok", "lookback_days": 90, "retrieved_at": "2026-10-11", "items": [
    {"published_at": "2026-10-09", "headline": "Acme ships <Rocket> 2", "url": "https://www.acme.com/blog/rocket-2",
     "publisher": "Acme Blog", "source_class": "company_announcement", "event_type": "other"},
    {"published_at": "2026-10-01", "headline": "Unsafe link", "url": "javascript:alert(1)",
     "publisher": "Acme", "source_class": "company_announcement", "event_type": "funding"}]}


def test_no_news_file_leaves_the_page_unchanged(tmp_path):
    (tmp_path / "runs").mkdir()
    run_path = tmp_path / "runs" / "acme_com.json"
    run_path.write_text(json.dumps(RUN))
    out = render_file(run_path)
    assert out.read_text() == render_profile_html(RUN, source_name="acme_com.json")
    assert TITLE not in out.read_text()


def test_news_section_lists_items_at_the_bottom(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "news").mkdir()
    run_path = tmp_path / "runs" / "acme_com.json"
    run_path.write_text(json.dumps(RUN))
    (tmp_path / "news" / "acme_com.json").write_text(json.dumps(NEWS_OK))
    page = render_file(run_path).read_text()
    plain = render_profile_html(RUN, source_name="acme_com.json")
    assert page.index(TITLE) > page.index("Evidence ledger") and page.index(TITLE) < page.index("<footer>")
    section = page[page.index('<section id="news">'):page.index("</section>", page.index('<section id="news">')) + 10]
    assert page.replace(section, "") == plain                       # profile sections unchanged
    assert '<a href="https://www.acme.com/blog/rocket-2"' in section and "Acme ships &lt;Rocket&gt; 2" in section
    assert "2026-10-09" in section and "Acme Blog" in section and "company_announcement" in section
    assert "event type (rule-based): other" in section and "not verified" in section
    assert 'href="javascript:' not in section and "Unsafe link" in section


def test_not_found_shows_its_reason():
    html = render_profile_html(RUN, news={"status": "not_found", "reason": "no company feed found", "items": [],
                                          "lookback_days": 90, "retrieved_at": "2026-10-11"})
    assert TITLE in html and "not_found: no company feed found" in html


def test_unreadable_news_file_is_ignored(tmp_path):
    (tmp_path / "runs").mkdir()
    (tmp_path / "news").mkdir()
    run_path = tmp_path / "runs" / "acme_com.json"
    run_path.write_text(json.dumps(RUN))
    (tmp_path / "news" / "acme_com.json").write_text("{not json")
    assert TITLE not in render_file(run_path).read_text()
