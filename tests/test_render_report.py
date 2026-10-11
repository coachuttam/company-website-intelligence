"""B-108 (print stylesheet, cover, PDF) and B-109 (inline SVG charts) for wi/render. Fixtures only:
no model call, no network; the real-browser PDF test is skipped without Playwright's Chromium."""
from __future__ import annotations

import json
from datetime import date

import pytest

from wi.render import charts
from wi.render.__main__ import main
from wi.render.page import render_file, render_pdf_file, render_profile_html
from wi.render.pdf import count_pdf_pages

RUN = {
    "schema_version": "schema-v1", "crawl_status": "ok",
    "claims": [
        {"claim_id": "acme.com:company_identity.name:1", "field": "company_identity.name", "value": "Acme",
         "status": "extracted", "source_url": "https://www.acme.com/", "evidence": "Acme"},
        {"claim_id": "acme.com:products.names:2", "field": "products.names", "value": ["Rocket", "Anvil"],
         "status": "extracted", "source_url": "https://www.acme.com/", "evidence": ["Rocket", "Anvil"]},
        {"claim_id": "acme.com:pricing.sales_motion:3", "field": "pricing.sales_motion", "value": "sales-led",
         "status": "inferred", "source_url": "https://www.acme.com/pricing", "evidence": "Contact sales"},
        {"claim_id": "acme.com:traction.named_customers:4", "field": "traction.named_customers",
         "value": ["Globex", "<Initech>"], "status": "extracted", "source_url": "https://www.acme.com/customers",
         "evidence": ["Globex", "Initech"]},
        {"claim_id": "acme.com:company_identity.headquarters:5", "field": "company_identity.headquarters",
         "value": None, "status": "not_found", "source_url": "https://www.acme.com/about"},
        {"claim_id": "acme.com:pricing.free_trial:6", "field": "pricing.free_trial", "value": None,
         "status": "something_else"},
    ],
    "evidence_sources": {"acme.com:traction.named_customers:4": [
        {"quote": "Globex", "urls": ["https://www.acme.com/customers", "https://www.acme.com/"]},
        {"quote": "Initech", "urls": ["https://www.acme.com/<case>"]}]},
    "profile": {"company_identity": {"name": {"value": "Acme", "status": "extracted",
                                              "claim_id": "acme.com:company_identity.name:1"}},
                "coverage": {"pages_scanned": 9, "last_retrieved_at": "2026-10-11"}, "gaps_conflicts": []},
    "crawl": {"pages": [{"url": "https://www.acme.com/"}]},
}
NEWS = {"status": "ok", "lookback_days": 90, "retrieved_at": "2026-10-11", "items": [
    {"published_at": "2026-10-09", "headline": "A <b>launch</b>"},
    {"published_at": "2026-10-09", "headline": "Second same day"},
    {"published_at": "2026-07-13", "headline": "Window start"},
    {"published_at": "2026-07-12", "headline": "Too old"},
    {"published_at": None, "headline": "Undated"}]}


# ---------- chart data ----------

def test_coverage_counts_per_status():
    assert charts.coverage_counts(RUN) == {"extracted": 3, "inferred": 1, "conflicting": 0, "not_found": 2}
    assert charts.coverage_counts({}) == {"extracted": 0, "inferred": 0, "conflicting": 0, "not_found": 0}


def test_page_field_counts_counts_distinct_fields_per_page_and_skips_not_found():
    pairs = charts.page_field_counts(RUN)
    assert pairs == [("https://www.acme.com/", 3), ("https://www.acme.com/<case>", 1),
                     ("https://www.acme.com/customers", 1), ("https://www.acme.com/pricing", 1)]
    assert "https://www.acme.com/about" not in dict(pairs)   # the not_found claim's page evidences nothing


def test_news_timeline_places_dates_on_the_window():
    t = charts.news_timeline(NEWS)
    assert t["start"] == date(2026, 7, 13) and t["end"] == date(2026, 10, 11) and t["days"] == 90
    assert [(d.isoformat(), off, n) for d, off, n, _ in t["points"]] == [("2026-07-13", 0, 1), ("2026-10-09", 88, 2)]
    assert t["outside"] == 2   # one before the window, one undated


def test_news_timeline_is_none_without_items():
    assert charts.news_timeline({"status": "not_found", "reason": "no feed", "items": []}) is None
    assert charts.news_timeline({"status": "ok", "items": [], "retrieved_at": "2026-10-11"}) is None
    assert charts.news_timeline({"status": "ok", "items": [{"published_at": "2026-10-01"}]}) is None   # no retrieval date


# ---------- SVG and page ----------

def test_charts_on_page_are_labelled_and_escaped():
    page = render_profile_html(RUN, news=NEWS)
    assert "Field coverage (not accuracy)" in page
    for text in ("Sourced: 3", "Inferred: 1", "Conflicting: 0", "Not found: 2"):   # label, not colour alone
        assert text in page
    assert "4 pages used as evidence of 9 pages scanned" in page
    assert "&lt;case&gt;" in page and "<case>" not in page
    assert "&lt;b&gt;launch&lt;/b&gt;" in page and "<b>launch</b>" not in page
    assert "2 items with no date or a date outside the window are not drawn" in page
    assert "<script" not in page.lower()


def test_news_not_found_shows_reason_and_no_chart():
    page = render_profile_html(RUN, news={"status": "not_found", "reason": "no company feed found", "items": [],
                                          "lookback_days": 90, "retrieved_at": "2026-10-11"})
    assert "not_found: no company feed found" in page and 'id="news-timeline"' not in page


def test_print_stylesheet_and_cover():
    page = render_profile_html(RUN)
    assert "@media print" in page and "@page" in page
    cover = page[page.index('<div class="cover">'):page.index("<header>")]
    for text in ("Website-sourced profile", "Acme", "acme.com", "Retrieved 2026-10-11"):
        assert text in cover


def test_open_drawers_only_changes_drawer_state():
    shut, opened = render_profile_html(RUN), render_profile_html(RUN, open_drawers=True)
    assert '<details class="drawer" open>' in opened and '<details class="drawer" open>' not in shut
    assert opened.replace(" open>", ">") == shut


# ---------- PDF ----------

def test_count_pdf_pages():
    data = b"<< /Type /Pages /Count 2 >> << /Type /Page >> <</Type/Page/Parent 1 0 R>>"
    assert count_pdf_pages(data) == 2


def test_render_pdf_file_default_path_and_open_drawers(tmp_path):
    (tmp_path / "runs").mkdir()
    src = tmp_path / "runs" / "acme_com.json"
    src.write_text(json.dumps(RUN))
    seen = {}

    def fake_writer(page_html, out):
        seen["html"] = page_html
        out.write_bytes(b"%PDF")
        return 3

    out, pages = render_pdf_file(src, writer=fake_writer)
    assert out == tmp_path / "pages" / "acme_com.pdf" and out.is_file() and pages == 3
    assert '<details class="drawer" open>' in seen["html"]
    assert render_file(src).read_text().count('<details class="drawer" open>') == 0   # HTML page unchanged


def test_cli_pdf_flag(tmp_path, monkeypatch, capsys):
    (tmp_path / "runs").mkdir()
    src = tmp_path / "runs" / "acme_com.json"
    src.write_text(json.dumps(RUN))
    import wi.render.pdf as pdf
    monkeypatch.setattr(pdf, "write_pdf", lambda page_html, out: (out.write_bytes(b"%PDF"), 2)[1])
    assert main([str(src), "--pdf"]) == 0
    assert "acme_com.pdf (2 pages)" in capsys.readouterr().out


def test_real_pdf_when_chromium_is_available(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from wi.render.pdf import write_pdf
    try:
        pages = write_pdf(render_profile_html(RUN, news=NEWS, open_drawers=True), tmp_path / "acme.pdf")
    except Exception as exc:   # Chromium not installed
        pytest.skip("chromium not available: " + type(exc).__name__)
    assert pages >= 2   # cover page plus the profile
    assert (tmp_path / "acme.pdf").read_bytes().startswith(b"%PDF")
