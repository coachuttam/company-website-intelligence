"""B-83: run_site.main() on an unreachable site, end to end but offline: the crawl is replaced by a
fake result, ROOT points at a temporary folder (so no real .env is read and nothing is written to
data/runs), and no API key exists. The JSON must still be written, with crawl_status, every field
not_found and no model call."""
import json

import run_site
from wi.crawl.fetch import CrawlResult, FetchResult
from wi.extract.fields import FIELDS


def test_b83_unreachable_site_writes_an_empty_result_without_any_model_call(tmp_path, monkeypatch):
    def fake_crawl(url, domains, config, js_renderer=None):
        r = CrawlResult(start_url=url)
        r.pages = [FetchResult(url=url, status="error", error="simulated connect error")]
        r.start_attempts = 3
        r.crawl_status, r.crawl_error_code = "unreachable", "SITE_UNREACHABLE"
        r.crawl_status_reason = f"start URL {url} could not be fetched after 3 attempt(s): x"
        return r

    def no_model(*a, **k):
        raise AssertionError("no model client may be built for an unreachable site")

    monkeypatch.setattr(run_site, "ROOT", tmp_path)
    monkeypatch.setattr(run_site, "crawl_site", fake_crawl)
    monkeypatch.setattr(run_site, "OpenAIChatCompleter", no_model)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert run_site.main("https://unreachable-example.com/") == 0

    out = json.loads((tmp_path / "data" / "runs" / "unreachable-example_com.json").read_text())
    assert out["crawl_status"] == "unreachable"
    assert out["crawl_error_code"] == "SITE_UNREACHABLE"
    assert "3 attempt(s)" in out["crawl_status_reason"]
    assert out["profile"]["coverage"]["crawl_status"] == "unreachable"
    assert {c["field"] for c in out["claims"]} == set(FIELDS)
    assert all(c["status"] == "not_found" and c["coverage"]["pages_checked"] == 0 for c in out["claims"])
    assert out["usage"] is None and out["cache_status"] == "not_run"
    assert out["classifier"]["enabled"] is False and out["focus_retry"]["enabled"] is False


def test_b84_blocked_site_writes_an_empty_result_without_any_model_call(tmp_path, monkeypatch):
    def fake_crawl(url, domains, config, js_renderer=None):
        r = CrawlResult(start_url=url)
        r.pages = [FetchResult(url=url, status="error", status_code=403, error_code="BLOCKED",
                               error="HTTP 403")]
        r.start_attempts = 1
        r.crawl_status, r.crawl_error_code = "blocked", "SITE_BLOCKED"
        r.crawl_status_reason = f"start URL {url} refused the crawler after 1 attempt(s): HTTP 403"
        return r

    def no_model(*a, **k):
        raise AssertionError("no model client may be built for a blocked site")

    monkeypatch.setattr(run_site, "ROOT", tmp_path)
    monkeypatch.setattr(run_site, "crawl_site", fake_crawl)
    monkeypatch.setattr(run_site, "OpenAIChatCompleter", no_model)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert run_site.main("https://blocked-example.com/") == 0
    out = json.loads((tmp_path / "data" / "runs" / "blocked-example_com.json").read_text())
    assert (out["crawl_status"], out["crawl_error_code"]) == ("blocked", "SITE_BLOCKED")
    assert out["profile"]["coverage"]["crawl_status"] == "blocked"
    assert all(c["status"] == "not_found" for c in out["claims"]) and out["usage"] is None


# --- B-85: non-English site is flagged, and extraction still runs ---------------------------------

def test_b85_non_english_site_is_flagged_and_extraction_still_runs(tmp_path, monkeypatch, capsys):
    from tests.test_language import SPANISH
    from wi.extract.llm import LLMResult
    import eval.check_gate as check_gate

    home = f'<html lang="es"><head><title>Acme</title></head><body><p>{SPANISH}</p></body></html>'
    about = f'<html lang="es"><head><title>Sobre nosotros</title></head><body><p>{SPANISH}</p></body></html>'

    def fake_crawl(url, domains, config, js_renderer=None):
        r = CrawlResult(start_url=url)
        r.pages = [FetchResult(url="https://acme-ejemplo.com/", status="ok", status_code=200, html=home),
                   FetchResult(url="https://acme-ejemplo.com/sobre", status="ok", status_code=200, html=about)]
        r.start_attempts = 1
        return r

    quote = "Acme ayuda a las pequeñas y medianas empresas a cobrar más rápido."
    claims = [{"field": f, "status": "not_found", "value": None, "confidence": None, "source_url": None,
               "page_title": None, "evidence": None, "notes": None,
               "coverage": {"page_types_checked": ["home"], "pages_checked": 1}} for f in FIELDS]
    claims[FIELDS.index("company_identity.description")] = {
        "field": "company_identity.description", "status": "extracted", "value": quote, "confidence": 0.9,
        "source_url": "https://acme-ejemplo.com/", "page_title": "Acme", "evidence": quote,
        "notes": None, "coverage": None}
    calls = []

    class FakeCompleter:
        def __init__(self, *a, **k):
            pass

        def complete(self, messages, model):
            calls.append(model)
            return LLMResult(content=json.dumps({"claims": claims, "announcements": []}), model=model,
                             prompt_tokens=100, completion_tokens=50, total_tokens=150, elapsed_s=0.01)

    monkeypatch.setattr(run_site, "ROOT", tmp_path)
    monkeypatch.setattr(run_site, "crawl_site", fake_crawl)
    monkeypatch.setattr(run_site, "OpenAIChatCompleter", FakeCompleter)
    monkeypatch.setattr(run_site, "apply_classifier", lambda *a, **k: {"provider": "jev", "enabled": False})
    monkeypatch.setenv("OPENAI_API_KEY", "fake-key")

    assert run_site.main("https://acme-ejemplo.com/", use_cache=False) == 0
    assert calls, "extraction must still run for a non-English site"
    assert "WARNING: the site's text looks non-English" in capsys.readouterr().out

    path = tmp_path / "data" / "runs" / "acme-ejemplo_com.json"
    out = json.loads(path.read_text())
    assert (out["site_language"], out["site_language_source"], out["non_english"]) == ("es", "text + html lang", True)
    assert out["profile"]["coverage"]["non_english"] is True
    assert out["crawl_status"] == "ok"
    desc = next(c for c in out["claims"] if c["field"] == "company_identity.description")
    assert desc["status"] == "extracted"                 # the gate still accepted a real Spanish quote
    langs = out["crawl"]["page_languages"]
    assert [(p["declared_lang"], p["guessed_lang"], p["sent_to_model"]) for p in langs] == \
        [("es", "non-en", True), ("es", "non-en", True)]
    assert check_gate.main(str(path)) == 0               # schema and evidence presence still pass


# --- B-86: off-domain start redirect ----------------------------------------------------------------

def _redirected_crawl(final_url, code):
    def fake_crawl(url, domains, config, js_renderer=None):
        r = CrawlResult(start_url=url)
        r.pages = [FetchResult(url=final_url, status="error", status_code=200, error_code=code,
                               error=f"redirected off the approved domains to {final_url}",
                               requested_url=url)]
        r.start_attempts, r.final_url = 1, final_url
        r.crawl_status, r.crawl_error_code = "redirected", code
        r.crawl_status_reason = f"start URL {url} redirects to {final_url}, outside the approved domains"
        return r
    return fake_crawl


def _no_model(*a, **k):
    raise AssertionError("no model client may be built")


def test_b86_off_domain_redirect_writes_an_empty_result_without_any_model_call(tmp_path, monkeypatch):
    monkeypatch.setattr(run_site, "ROOT", tmp_path)
    monkeypatch.setattr(run_site, "crawl_site",
                        _redirected_crawl("https://www.atlassian.com/software/loom", "REDIRECTED_OFF_DOMAIN"))
    monkeypatch.setattr(run_site, "OpenAIChatCompleter", _no_model)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    assert run_site.main("https://moved-example.com/") == 0
    out = json.loads((tmp_path / "data" / "runs" / "moved-example_com.json").read_text())
    assert (out["crawl_status"], out["crawl_error_code"]) == ("redirected", "REDIRECTED_OFF_DOMAIN")
    assert out["final_url"] == "https://www.atlassian.com/software/loom"
    assert all(c["status"] == "not_found" for c in out["claims"]) and out["usage"] is None


def test_b86_redirect_to_a_restricted_platform_is_rejected_like_validation(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(run_site, "ROOT", tmp_path)
    monkeypatch.setattr(run_site, "crawl_site",
                        _redirected_crawl("https://www.linkedin.com/company/acme", "RESTRICTED_PLATFORM"))
    monkeypatch.setattr(run_site, "OpenAIChatCompleter", _no_model)

    assert run_site.main("https://acme-example.com/") == 1
    assert "REJECTED (RESTRICTED_PLATFORM)" in capsys.readouterr().out
    assert not (tmp_path / "data" / "runs").exists()      # existing handling: no JSON written
