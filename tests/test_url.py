"""URL validation tests. Maps to PRD requirements INP-01, INP-02 and behaviour B-11."""
import pytest

from wi.crawl.url import validate_company_url

MALFORMED = [
    "not-a-url", "", "   ", None, 123, "http://", "ftp://example.com",
    "http://localhost", "http://192.168.1.1", "exa mple.com", "https://-bad-.com",
]


@pytest.mark.parametrize("raw", MALFORMED)
def test_malformed_input_returns_invalid_url(raw):   # B-11
    r = validate_company_url(raw)
    assert r.status == "error" and r.error_code == "INVALID_URL"


def test_bare_domain_gets_https_and_approved_domains():
    r = validate_company_url("northledger.example")
    assert r.status == "ok"
    assert r.url == "https://northledger.example/"
    assert r.approved_domains == ["northledger.example", "www.northledger.example"]


def test_www_input_approves_apex_too():
    r = validate_company_url("https://www.northledger.example/pricing")
    assert r.approved_domains == ["northledger.example", "www.northledger.example"]


def test_http_is_supported():
    assert validate_company_url("http://northledger.example").status == "ok"


@pytest.mark.parametrize("raw", ["https://linkedin.com/company/x", "https://www.twitter.com/x", "x.com/acme"])
def test_restricted_platforms_rejected(raw):
    r = validate_company_url(raw)
    assert r.status == "error" and r.error_code == "RESTRICTED_PLATFORM"
