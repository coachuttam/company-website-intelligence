"""Reference profile page (wi/render, PRD Section 6). Offline, no LLM, stdlib-only.

Covers B-20 (the page renders from saved JSON with the LLM blocked) and B-55 (what the page may
and may not show: honest badges, gaps only in the gaps section, escaped third-party text)."""
import ast
import json
import socket
from pathlib import Path

import pytest

from wi.render.__main__ import main
from wi.render.page import render_file, render_profile_html

REPO = Path(__file__).resolve().parent.parent


def _claim(cid, field, value, status="extracted", quote="a quote", url="https://acme.com/about", **extra):
    base = {
        "claim_id": cid, "field": field, "value": value, "status": status, "confidence": None,
        "source_url": url, "page_title": "About Acme", "evidence": quote,
        "retrieved_at": "2026-10-03", "notes": None, "coverage": None,
    }
    base.update(extra)
    return base


def _run(**overrides):
    claims = [
        _claim("acme.com:company_identity.name:0", "company_identity.name", "Acme", quote="Acme Corp"),
        _claim("acme.com:company_identity.headquarters:1", "company_identity.headquarters",
               "Pune, India", status="inferred", quote="Pune, Maharashtra 411001"),
        _claim("acme.com:products.names:2", "products.names", ["Pay", "Payout"],
               quote=["Acme Pay", "Acme Payout"]),
        _claim("acme.com:pricing.public_plans:3", "pricing.public_plans", None, status="not_found",
               quote=None, coverage={"pages_checked": 12}),
    ]
    run = {
        "schema_version": "1",
        "limit_reached": False,
        "crawl": {"pages": [{"url": "https://www.acme.com/"}]},
        "claims": claims,
        "announcements": [],
        "profile": {
            "company_identity": {
                "name": {"value": "Acme", "status": "extracted", "claim_id": claims[0]["claim_id"]},
                "headquarters": {"value": "Pune, India", "status": "inferred", "claim_id": claims[1]["claim_id"]},
            },
            "products_services": {
                "names": {"value": ["Pay", "Payout"], "status": "extracted", "claim_id": claims[2]["claim_id"]},
            },
            "customers_positioning": {},
            "pricing_commercial": {},
            "evidence_traction": {"announcements": []},
            "company_comparisons": {},
            "coverage": {
                "pages_scanned": 40, "total_fields": 15, "fields_populated": 10,
                "fields_inferred": 3, "fields_conflicting": 0, "fields_not_found": 5,
                "evidence_support_rate": 0.5882352941176471, "last_retrieved_at": "2026-10-03",
            },
            "gaps_conflicts": [
                {"value": None, "status": "not_found", "claim_id": claims[3]["claim_id"],
                 "field": "pricing.public_plans"},
            ],
        },
    }
    run.update(overrides)
    return run


def test_header_labels_the_page_as_a_website_sourced_profile():
    page = render_profile_html(_run())
    assert "<h1>Acme" in page
    assert "Website-sourced profile" in page
    assert "acme.com" in page
    assert "self-reported" in page


def test_status_badges_use_the_ui_labels():
    page = render_profile_html(_run())
    assert 'class="badge sourced">Sourced<' in page
    assert 'class="badge inferred">Inferred<' in page


def test_coverage_strip_shows_the_profile_numbers():
    page = render_profile_html(_run())
    assert "10 of 15" in page
    assert "59%" in page
    assert "<dd>40</dd>" in page
    assert "2026-10-03" in page


def test_not_found_fields_appear_only_in_the_gaps_section():
    page = render_profile_html(_run())
    assert page.count("Public plans") == 1
    assert page.index("Public plans") > page.index('id="gaps"')
    assert "Checked 12 pages" in page


def test_empty_groups_are_omitted_not_rendered_as_empty_cards():
    page = render_profile_html(_run())
    assert 'id="overview"' in page and 'id="products"' in page
    assert 'id="comparisons"' not in page
    assert 'id="pricing"' not in page


def test_evidence_drawer_shows_quote_and_source_link():
    page = render_profile_html(_run())
    assert "<details" in page
    assert "Acme Pay" in page
    assert 'href="https://acme.com/about"' in page
    assert "Retrieved 2026-10-03" in page


def test_inferred_fact_says_it_is_an_inference():
    page = render_profile_html(_run())
    assert "does not state this directly" in page


def test_conflicting_claim_shows_both_values_and_both_quotes():
    conflict = _claim(
        "acme.com:company_identity.headquarters:9", "company_identity.headquarters",
        ["Pune", "Mumbai"], status="conflicting", quote=["HQ is Pune", "Based in Mumbai"],
    )
    run = _run()
    run["claims"].append(conflict)
    run["profile"]["gaps_conflicts"].append(
        {"value": ["Pune", "Mumbai"], "status": "conflicting", "claim_id": conflict["claim_id"],
         "field": "company_identity.headquarters"}
    )
    page = render_profile_html(run)
    gaps_part = page[page.index('id="gaps"'):page.index('id="ledger"')]
    for needle in ("Pune", "Mumbai", "HQ is Pune", "Based in Mumbai", "Conflicting"):
        assert needle in gaps_part
    assert "Neither is picked" in gaps_part


def test_limit_reached_shows_a_partial_profile_banner_and_only_then():
    assert "Partial profile" in render_profile_html(_run(limit_reached=True))
    assert "Partial profile" not in render_profile_html(_run(limit_reached=False))


def test_third_party_text_is_escaped_and_javascript_urls_stay_inert():
    run = _run()
    evil = "<script>alert(1)</script>"
    run["claims"][0]["value"] = evil
    run["claims"][0]["evidence"] = "<img src=x onerror=alert(1)>"
    run["claims"][0]["source_url"] = "javascript:alert(1)"
    run["claims"][0]["page_title"] = '"><b>bold</b>'
    run["profile"]["company_identity"]["name"]["value"] = evil
    page = render_profile_html(run)
    lowered = page.lower()
    assert "<script" not in lowered
    assert "<img" not in lowered
    assert "<b>bold" not in lowered
    assert 'href="javascript' not in lowered
    assert "&lt;script&gt;" in page


def test_page_loads_nothing_external_and_runs_no_script():
    page = render_profile_html(_run()).lower()
    assert "<script" not in page
    assert "<link" not in page
    assert " src=" not in page


def test_renders_with_the_network_blocked(monkeypatch):
    """B-20: the page needs no model and no network."""
    def _blocked(*args, **kwargs):
        raise AssertionError("the renderer must not open a socket")
    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    assert "Website-sourced profile" in render_profile_html(_run())


def test_render_package_imports_only_the_standard_library():
    # sys.stdlib_module_names only exists on Python 3.10+; the project venv is 3.9, where the
    # test would crash on the attribute rather than check anything, so skip there.
    sys_module = __import__("sys")
    if not hasattr(sys_module, "stdlib_module_names"):
        pytest.skip("needs Python 3.10+ (sys.stdlib_module_names)")
    stdlib = set(sys_module.stdlib_module_names)
    for path in (REPO / "wi" / "render").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            for name in names:
                top = name.split(".")[0]
                assert top in stdlib or name.startswith("wi.render"), path.name + " imports " + name


def test_render_file_writes_to_data_pages_by_default(tmp_path):
    runs = tmp_path / "data" / "runs"
    runs.mkdir(parents=True)
    src = runs / "acme_com.json"
    src.write_text(json.dumps(_run()), encoding="utf-8")
    out = render_file(src)
    assert out == tmp_path / "data" / "pages" / "acme_com.html"
    assert "Website-sourced profile" in out.read_text(encoding="utf-8")
    assert "acme_com.json" in out.read_text(encoding="utf-8")


def test_cli_writes_a_page_and_reports_bad_input(tmp_path, capsys):
    src = tmp_path / "run.json"
    src.write_text(json.dumps(_run()), encoding="utf-8")
    target = tmp_path / "out.html"
    assert main([str(src), "-o", str(target)]) == 0
    assert target.exists()
    assert "Wrote" in capsys.readouterr().out
    assert main([str(tmp_path / "missing.json")]) == 1
    assert "Could not render" in capsys.readouterr().out


@pytest.mark.skipif(not (REPO / "data" / "runs" / "razorpay_com.json").exists(), reason="no saved run")
def test_renders_a_real_saved_run():
    run = json.loads((REPO / "data" / "runs" / "razorpay_com.json").read_text(encoding="utf-8"))
    page = render_profile_html(run)
    assert "Razorpay" in page and "Evidence ledger" in page


def test_b85_non_english_banner_shows_only_when_flagged():
    flagged = render_profile_html(_run(non_english=True, site_language="es"))
    assert "Non-English site (detected language: es)" in flagged
    assert "Non-English site" not in render_profile_html(_run(non_english=False, site_language="en"))
    assert "Non-English site" not in render_profile_html(_run())     # older runs have no flag
