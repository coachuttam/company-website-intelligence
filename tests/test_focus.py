"""Tests for the focused second pass (B-71). Offline: the extractor is a stub."""
import pytest

from wi.crawl.clean import CleanPage
from wi.extract.focus import FIELD_HINTS, choose_pages, focus_retry
from wi.extract.llm import LLMResult
from wi.extract.pipeline import ExtractionRun, RejectedClaim
from wi.schemas.claim import Claim, Coverage, Status

CFG = {"focus_retry": {"enabled": True, "max_pages": 4,
                        "fields": ["customers.industries", "traction.certifications"]}}

INDUSTRIES_TEXT = ("ALL INDUSTRIES\nFinancial Services\nSimplify your data in banking and insurance.\n"
                   "Healthcare & Life Sciences\nBuild a foundation for research.\nManufacturing\n"
                   "Public Sector\nRetail & Consumer Goods\nTelecom\n" * 2)
SECURITY_TEXT = "Security\nWe are SOC 2 Type II certified and ISO 27001 compliant. HIPAA and GDPR ready.\n" * 3
HOME_TEXT = "Welcome to Example. We build great software for everyone.\n" * 5


def page(url, text):
    return CleanPage(url=url, title=None, text=text)


PAGES = [
    page("https://x.com/", HOME_TEXT),
    page("https://x.com/security", SECURITY_TEXT),
    page("https://x.com/solutions/industries", INDUSTRIES_TEXT),
    page("https://x.com/blog/random", HOME_TEXT),
]


def nf(field):
    return Claim(claim_id=f"x:{field}:0", field=field, status=Status.not_found,
                 coverage=Coverage(page_types_checked=["home"], pages_checked=1))


def got(field, value, evidence, status=Status.extracted):
    return Claim(claim_id=f"other:{field}:9", field=field, value=value, status=status,
                 source_url="https://x.com/solutions/industries", evidence=evidence,
                 retrieved_at="2026-10-06")


def usage(p=1000, c=50):
    return LLMResult(content="", model="m", prompt_tokens=p, completion_tokens=c,
                     total_tokens=p + c, elapsed_s=1.0)


class StubExtractor:
    def __init__(self, claims, rejected=None, cache_status="miss", error=None):
        self.claims, self.rejected, self.cache_status, self.error = claims, rejected or [], cache_status, error
        self.calls = []

    def __call__(self, site_url, pages, config, completer, retrieved_at=None, cache=None):
        self.calls.append([p.url for p in pages])
        if self.error:
            raise self.error
        r = ExtractionRun(site_url=site_url, claims=self.claims, rejected=self.rejected)
        r.usage, r.cache_status = usage(), self.cache_status
        return r


def first_pass(*claims):
    r = ExtractionRun(site_url="https://x.com/", claims=list(claims))
    r.usage = usage(5000, 200)
    return r


def by_field(run):
    return {c.field: c for c in run.claims}


def test_choose_pages_picks_the_page_that_looks_like_the_field():
    assert choose_pages("customers.industries", PAGES)[0].url == "https://x.com/solutions/industries"
    assert choose_pages("traction.certifications", PAGES)[0].url == "https://x.com/security"
    assert choose_pages("traction.partnerships", [PAGES[0], PAGES[3]]) == []


def test_every_field_hint_compiles():
    import re
    for url_pat, text_pat in FIELD_HINTS.values():
        re.compile(url_pat), re.compile(text_pat)


def test_disabled_does_nothing():
    run = first_pass(nf("customers.industries"))
    ext = StubExtractor([])
    assert focus_retry(run, PAGES, {}, None, "2026-10-06", extractor=ext) == {"enabled": False}
    assert ext.calls == []


def test_adopts_a_not_found_field_and_only_that_field():
    run = first_pass(nf("customers.industries"),
                     got("company_identity.name", "Example", "Example"))
    ext = StubExtractor([got("customers.industries", ["Financial Services", "Manufacturing"],
                             ["Financial Services", "Manufacturing"]),
                         got("company_identity.name", "WRONG", "WRONG")])
    report = focus_retry(run, PAGES, CFG, None, "2026-10-06", extractor=ext)
    c = by_field(run)
    assert c["customers.industries"].status == Status.extracted
    assert c["customers.industries"].value == ["Financial Services", "Manufacturing"]
    assert c["customers.industries"].claim_id == "x:customers.industries:0"       # keeps its slot
    assert "second pass" in c["customers.industries"].notes
    assert c["company_identity.name"].value == "Example"                           # never touched
    assert report["fields"][0]["adopted"] is True and report["calls"] == 1


def test_an_answered_field_is_never_asked_again():
    run = first_pass(got("customers.industries", ["Retail"], ["Retail"]),
                     nf("traction.certifications"))
    ext = StubExtractor([nf("traction.certifications")])
    report = focus_retry(run, PAGES, CFG, None, "2026-10-06", extractor=ext)
    assert [e["field"] for e in report["fields"]] == ["traction.certifications"]
    assert ext.calls == [["https://x.com/security"]]


def test_second_pass_not_found_leaves_the_field_not_found():
    run = first_pass(nf("customers.industries"))
    ext = StubExtractor([nf("customers.industries")])
    report = focus_retry(run, PAGES, CFG, None, "2026-10-06", extractor=ext)
    assert by_field(run)["customers.industries"].status == Status.not_found
    assert report["fields"][0]["adopted"] is False


def test_rejected_second_pass_claim_is_recorded_not_adopted():
    run = first_pass(nf("customers.industries"))
    rej = RejectedClaim(field="customers.industries", reason="quote not found",
                        attempted_value=["Mining"], attempted_evidence=["Mining"],
                        source_url="https://x.com/solutions/industries")
    ext = StubExtractor([nf("customers.industries")], rejected=[rej])
    focus_retry(run, PAGES, CFG, None, "2026-10-06", extractor=ext)
    assert by_field(run)["customers.industries"].status == Status.not_found
    assert run.rejected[-1].reason.startswith("[second pass]")


def test_an_extractor_failure_leaves_the_first_pass_untouched():
    run = first_pass(nf("customers.industries"))
    report = focus_retry(run, PAGES, CFG, None, "2026-10-06",
                         extractor=StubExtractor([], error=RuntimeError("boom")))
    assert "boom" in report["error"] and by_field(run)["customers.industries"].status == Status.not_found
    assert run.usage.prompt_tokens == 5000


def test_usage_is_added_and_a_cache_hit_counts_no_call():
    run = first_pass(nf("customers.industries"))
    ext = StubExtractor([nf("customers.industries")], cache_status="hit")
    report = focus_retry(run, PAGES, CFG, None, "2026-10-06", extractor=ext)
    assert run.usage.prompt_tokens == 6000 and report["calls"] == 0


def test_page_cap_and_no_candidate_page_means_no_call():
    cfg = {"focus_retry": {"enabled": True, "max_pages": 1,
                            "fields": ["customers.industries", "traction.certifications"]}}
    run = first_pass(nf("customers.industries"), nf("traction.certifications"))
    ext = StubExtractor([nf("customers.industries"), nf("traction.certifications")])
    focus_retry(run, PAGES, cfg, None, "2026-10-06", extractor=ext)
    assert len(ext.calls[0]) == 1
    ext2 = StubExtractor([])
    run2 = first_pass(nf("customers.industries"))
    report = focus_retry(run2, [PAGES[0], PAGES[3]], CFG, None, "2026-10-06", extractor=ext2)
    assert ext2.calls == [] and report["fields"][0]["adopted"] is False


def test_b72_tie_prefers_shallower_path():
    deep = page("https://x.com/solutions/industries/retail", INDUSTRIES_TEXT)
    top = page("https://x.com/solutions/industries", INDUSTRIES_TEXT)
    assert choose_pages("customers.industries", [deep, top], limit=1) == [top]


def test_b72_named_customer_statistic_not_adopted():
    cfg = {"focus_retry": {"enabled": True, "fields": ["traction.named_customers"]}}
    run = ExtractionRun(site_url="https://x.com", claims=[nf("traction.named_customers")])
    pages = [page("https://x.com/customers", "Our customers: trusted by teams. Customer stories and testimonials.\n" * 6)]
    stub = StubExtractor([got("traction.named_customers", ["95% of the Fortune 500"], ["95% of the Fortune 500"])])
    report = focus_retry(run, pages, cfg, None, "2026-10-06", extractor=stub)
    assert run.claims[0].status == Status.not_found
    assert report["fields"][0]["adopted"] is False


def test_b72_named_customer_keeps_real_names_drops_statistic():
    cfg = {"focus_retry": {"enabled": True, "fields": ["traction.named_customers"]}}
    run = ExtractionRun(site_url="https://x.com", claims=[nf("traction.named_customers")])
    pages = [page("https://x.com/customers", "Our customers: trusted by teams. Customer stories and testimonials.\n" * 6)]
    stub = StubExtractor([got("traction.named_customers", ["Acme", "95% of the Fortune 500"],
                              ["Acme", "95% of the Fortune 500"])])
    focus_retry(run, pages, cfg, None, "2026-10-06", extractor=stub)
    assert run.claims[0].value == ["Acme"] and run.claims[0].evidence == ["Acme"]
