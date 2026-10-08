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
