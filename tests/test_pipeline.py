"""Tests for wi.extract.pipeline. A FakeCompleter stands in for the LLM so
these never call OpenAI or need an API key -- they test the deterministic
half of the system: schema validation and the evidence gate.
"""
from __future__ import annotations

import json

from wi.crawl.clean import CleanPage
from wi.extract.fields import FIELDS
from wi.extract.llm import LLMResult
from wi.extract.pipeline import _fit_pages_to_input_budget, diagnostics_from_run, extract_claims
from wi.schemas.claim import Status

CONFIG = {"llm": {"small_model": "gpt-4o-mini"}}

PAGE = CleanPage(
    url="https://example.com/",
    title="Example",
    text="Example Co is project management without all the nonsense. "
         "Start a 30-day free trial today.",
)


class FakeCompleter:
    """Returns a fixed JSON payload; counts calls so tests can assert the LLM
    was (or wasn't) actually invoked. Also records the last messages it was
    called with, so a test can check exactly what page text reached the prompt."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = 0
        self.last_messages = None

    def complete(self, messages, model):
        self.calls += 1
        self.last_messages = messages
        return LLMResult(
            content=json.dumps(self.payload),
            model=model,
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            elapsed_s=0.01,
        )


def _all_not_found_claims():
    return [{"field": f, "status": "not_found", "value": None, "confidence": None,
             "source_url": None, "page_title": None, "evidence": None, "notes": None,
             "coverage": {"page_types_checked": ["homepage"], "pages_checked": 1}}
            for f in FIELDS]


def test_happy_path_extracted_claim_passes_evidence_check():
    claims = _all_not_found_claims()
    claims[0] = {
        "field": "company_identity.name", "status": "extracted", "value": "Example Co",
        "confidence": 0.95, "source_url": "https://example.com/", "page_title": "Example",
        "evidence": "Example Co is project management without all the nonsense.",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    assert completer.calls == 1
    assert len(run.claims) == len(FIELDS)
    assert not run.rejected
    assert not run.schema_errors
    name_claim = next(c for c in run.claims if c.field == "company_identity.name")
    assert name_claim.status == Status.extracted
    assert name_claim.retrieved_at == "2026-09-22"  # code-assigned, not model-assigned


def test_hallucinated_quote_is_downgraded_not_dropped():
    claims = _all_not_found_claims()
    claims[0] = {
        "field": "company_identity.name", "status": "extracted", "value": "Wrong Name Inc",
        "confidence": 0.9, "source_url": "https://example.com/", "page_title": "Example",
        "evidence": "This sentence does not appear on the page at all.",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    assert len(run.rejected) == 1
    assert run.rejected[0].field == "company_identity.name"
    assert run.rejected[0].attempted_value == "Wrong Name Inc"
    # The claim actually kept must be the safe not_found replacement, never the hallucination.
    name_claim = next(c for c in run.claims if c.field == "company_identity.name")
    assert name_claim.status == Status.not_found


def test_malformed_json_falls_back_to_all_not_found():
    class BrokenCompleter:
        def complete(self, messages, model):
            return LLMResult(content="not valid json{{{", model=model,
                              prompt_tokens=10, completion_tokens=5, total_tokens=15, elapsed_s=0.01)

    run = extract_claims("https://example.com/", [PAGE], CONFIG, BrokenCompleter(), retrieved_at="2026-09-22")

    assert run.schema_errors
    assert len(run.claims) == len(FIELDS)
    assert all(c.status == Status.not_found for c in run.claims)


# --- B-18: one corrective retry on malformed model JSON, decided 2026-09-27 -------------------
# Before this, a single unparseable response fell straight back to all-not_found with no second
# attempt. Now extract_claims() makes exactly one extra completer.complete() call, showing the
# model its own bad output plus a specific correction, before giving up. The pre-existing
# test_malformed_json_falls_back_to_all_not_found above must keep passing unchanged: a
# BrokenCompleter that ALWAYS returns bad JSON still ends up all-not_found, just via 2 calls
# instead of 1 -- covered explicitly below rather than changing that test's own assertions.

class _BadThenGoodCompleter:
    """First call returns unparseable content; second (the corrective retry) returns a good
    payload. Counts calls so a test can confirm the retry actually happened exactly once."""

    def __init__(self, good_payload: dict):
        self.good_payload = good_payload
        self.calls = 0

    def complete(self, messages, model):
        self.calls += 1
        if self.calls == 1:
            return LLMResult(content="not valid json{{{", model=model, prompt_tokens=10,
                              completion_tokens=5, total_tokens=15, elapsed_s=0.01)
        return LLMResult(content=json.dumps(self.good_payload), model=model, prompt_tokens=120,
                          completion_tokens=60, total_tokens=180, elapsed_s=0.02)


def test_malformed_json_recovers_via_one_corrective_retry():
    good_claims = _all_not_found_claims()
    good_claims[FIELDS.index("company_identity.name")] = {
        "field": "company_identity.name", "status": "extracted", "value": "Example Co",
        "confidence": 0.9, "source_url": "https://example.com/", "page_title": "Example",
        "evidence": "Example Co is project management without all the nonsense.",
        "notes": None, "coverage": None,
    }
    completer = _BadThenGoodCompleter({"claims": good_claims})

    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    assert completer.calls == 2  # the original attempt plus exactly one corrective retry
    assert any("could not parse" in e for e in run.schema_errors)  # the first failure is logged
    name_claim = next(c for c in run.claims if c.field == "company_identity.name")
    assert name_claim.status == Status.extracted
    assert name_claim.value == "Example Co"
    # Both calls' token cost is real cost incurred for this run -- usage reports the sum.
    assert run.usage.prompt_tokens == 10 + 120
    assert run.usage.completion_tokens == 5 + 60
    assert run.usage.total_tokens == 15 + 180


def test_malformed_json_retry_also_failing_still_falls_back_to_all_not_found():
    class AlwaysBrokenCompleter:
        def __init__(self):
            self.calls = 0

        def complete(self, messages, model):
            self.calls += 1
            return LLMResult(content=f"still not json {self.calls}{{{{", model=model,
                              prompt_tokens=10, completion_tokens=5, total_tokens=15, elapsed_s=0.01)

    completer = AlwaysBrokenCompleter()
    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    assert completer.calls == 2  # the retry happened, it just didn't help
    assert len(run.claims) == len(FIELDS)
    assert all(c.status == Status.not_found for c in run.claims)
    # Both failures are on record, not just the last one.
    assert any("could not parse" in e for e in run.schema_errors)
    assert any("retry also failed" in e for e in run.schema_errors)


def test_corrective_retry_shows_the_model_its_own_bad_output_and_a_correction():
    # The retry messages must actually carry the original conversation, the bad assistant
    # response, and a corrective instruction -- not just a bare re-ask.
    good_claims = _all_not_found_claims()
    completer = _BadThenGoodCompleter({"claims": good_claims})

    extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    # The FakeCompleter-style class above doesn't record messages itself, so wrap it to inspect
    # what the second call actually received.
    class RecordingBadThenGood(_BadThenGoodCompleter):
        def __init__(self, good_payload):
            super().__init__(good_payload)
            self.messages_by_call: list = []

        def complete(self, messages, model):
            self.messages_by_call.append(messages)
            return super().complete(messages, model)

    recorder = RecordingBadThenGood({"claims": good_claims})
    extract_claims("https://example.com/", [PAGE], CONFIG, recorder, retrieved_at="2026-09-22")

    assert len(recorder.messages_by_call) == 2
    first_messages, retry_messages = recorder.messages_by_call
    assert len(retry_messages) == len(first_messages) + 2
    assert retry_messages[-2] == {"role": "assistant", "content": "not valid json{{{"}
    assert retry_messages[-1]["role"] == "user"
    assert "claims" in retry_messages[-1]["content"]


def test_model_skipping_a_field_is_backfilled_and_logged():
    claims = _all_not_found_claims()[:-1]  # drop the last field entirely
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    missing_field = FIELDS[-1]
    assert any(missing_field in e for e in run.schema_errors)
    assert any(c.field == missing_field and c.status == Status.not_found for c in run.claims)


def test_no_pages_skips_the_llm_call_entirely():
    completer = FakeCompleter({"claims": _all_not_found_claims()})

    run = extract_claims("https://example.com/", [], CONFIG, completer, retrieved_at="2026-09-22")

    assert completer.calls == 0
    assert len(run.claims) == len(FIELDS)
    assert all(c.status == Status.not_found for c in run.claims)


# --- B-03: an inferred subscription revenue_model from a "Contact sales" quote must be
# downgraded end-to-end through the pipeline, not just at the evidence-check unit level -------

CONTACT_SALES_PRICING_PAGE = CleanPage(
    url="https://example.com/pricing", title="Pricing",
    text="Our enterprise plans are tailored to your needs. Contact sales to get a quote.",
)


def test_pipeline_downgrades_contact_sales_subscription_over_inference_to_not_found():
    claims = _all_not_found_claims()
    claims[FIELDS.index("pricing.revenue_model")] = {
        "field": "pricing.revenue_model", "status": "inferred", "value": "subscription",
        "confidence": 0.6, "source_url": "https://example.com/pricing", "page_title": "Pricing",
        "evidence": "Contact sales to get a quote.",
        "notes": "Inferred from the pricing page's sales-contact call to action.",
        "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [CONTACT_SALES_PRICING_PAGE], CONFIG, completer,
                          retrieved_at="2026-09-27")

    rejected = [r for r in run.rejected if r.field == "pricing.revenue_model"]
    assert len(rejected) == 1
    assert "subscription" in rejected[0].reason
    revenue_claim = next(c for c in run.claims if c.field == "pricing.revenue_model")
    assert revenue_claim.status == Status.not_found


# --- B-07/OUT-04: dated company-reported announcements, entirely separate from FIELDS --------

FUNDING_PAGE = CleanPage(
    url="https://example.com/newsroom", title="Newsroom",
    text="Posted March 2025 -- We're thrilled to announce our $5M Series A funding round, "
         "led by Example Capital.",
)


def _payload_with_announcements(announcements):
    return {"claims": _all_not_found_claims(), "announcements": announcements}


def test_B07_funding_announcement_appears_separately_never_as_a_core_field():
    completer = FakeCompleter(_payload_with_announcements([{
        "text": "$5M Series A funding round", "category": "funding", "date": "March 2025",
        "source_url": "https://example.com/newsroom", "page_title": "Newsroom",
        "evidence": "We're thrilled to announce our $5M Series A funding round, led by "
                    "Example Capital.",
    }]))

    run = extract_claims("https://example.com/", [FUNDING_PAGE], CONFIG, completer,
                          retrieved_at="2026-09-27")

    assert not run.rejected_announcements
    assert len(run.announcements) == 1
    ann = run.announcements[0]
    assert ann.category == "funding"
    assert ann.date == "March 2025"
    assert ann.retrieved_at == "2026-09-27"  # code-assigned, not model-assigned
    # Never counted as, or folded into, one of the 15 core fields.
    assert all(c.field != "traction.named_customers" or c.status == Status.not_found
               for c in run.claims)
    assert len(run.claims) == len(FIELDS)  # the 15-field ledger is completely unaffected


def test_missing_announcements_key_defaults_to_empty_list_not_an_error():
    # Backward compatibility: a payload with no "announcements" key at all (every pipeline
    # test written before B-07, and any real cached payload from before this feature shipped)
    # must behave exactly as before -- zero announcements, no schema error.
    completer = FakeCompleter({"claims": _all_not_found_claims()})  # no "announcements" key

    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-27")

    assert run.announcements == []
    assert run.rejected_announcements == []
    assert not any("announcement" in e for e in run.schema_errors)


def test_announcement_with_fabricated_quote_is_dropped_and_logged():
    completer = FakeCompleter(_payload_with_announcements([{
        "text": "$50M acquisition", "category": "acquisition", "date": "2025",
        "source_url": "https://example.com/newsroom", "page_title": "Newsroom",
        "evidence": "This sentence never appears on the page at all.",
    }]))

    run = extract_claims("https://example.com/", [FUNDING_PAGE], CONFIG, completer,
                          retrieved_at="2026-09-27")

    assert run.announcements == []
    assert len(run.rejected_announcements) == 1
    assert "not found" in run.rejected_announcements[0].reason
    assert run.rejected_announcements[0].attempted_text == "$50M acquisition"


def test_announcement_missing_a_date_fails_schema_and_is_dropped():
    # Rule 10's own instruction: an undated statement must never be reported at all. If the
    # model does so anyway, Announcement's own validator (wi/schemas/announcement.py) rejects
    # it, and the pipeline drops it rather than inventing a not_found replacement.
    completer = FakeCompleter(_payload_with_announcements([{
        "text": "Partnered with several leading firms", "category": "partnership", "date": "",
        "source_url": "https://example.com/newsroom", "page_title": "Newsroom",
        "evidence": "We're thrilled to announce our $5M Series A funding round, led by "
                    "Example Capital.",
    }]))

    run = extract_claims("https://example.com/", [FUNDING_PAGE], CONFIG, completer,
                          retrieved_at="2026-09-27")

    assert run.announcements == []
    assert len(run.rejected_announcements) == 1
    assert any("announcement" in e for e in run.schema_errors)


def test_announcement_with_unknown_category_is_dropped():
    completer = FakeCompleter(_payload_with_announcements([{
        "text": "Something happened", "category": "gossip", "date": "March 2025",
        "source_url": "https://example.com/newsroom", "page_title": "Newsroom",
        "evidence": "We're thrilled to announce our $5M Series A funding round, led by "
                    "Example Capital.",
    }]))

    run = extract_claims("https://example.com/", [FUNDING_PAGE], CONFIG, completer,
                          retrieved_at="2026-09-27")

    assert run.announcements == []
    assert len(run.rejected_announcements) == 1


def test_multiple_announcements_and_a_mix_of_valid_and_invalid_are_handled_independently():
    page_b = CleanPage(url="https://example.com/press", title="Press",
                        text="April 2024: we launched our new mobile app.")
    completer = FakeCompleter(_payload_with_announcements([
        {
            "text": "$5M Series A funding round", "category": "funding", "date": "March 2025",
            "source_url": "https://example.com/newsroom", "page_title": "Newsroom",
            "evidence": "We're thrilled to announce our $5M Series A funding round, led by "
                        "Example Capital.",
        },
        {
            "text": "New mobile app launch", "category": "product_launch", "date": "April 2024",
            "source_url": "https://example.com/press", "page_title": "Press",
            "evidence": "April 2024: we launched our new mobile app.",
        },
        {
            "text": "Fabricated announcement", "category": "other", "date": "2025",
            "source_url": "https://example.com/newsroom", "page_title": "Newsroom",
            "evidence": "This never appears on any page.",
        },
    ]))

    run = extract_claims("https://example.com/", [FUNDING_PAGE, page_b], CONFIG, completer,
                          retrieved_at="2026-09-27")

    assert len(run.announcements) == 2
    assert {a.category for a in run.announcements} == {"funding", "product_launch"}
    assert len(run.rejected_announcements) == 1


def test_list_valued_claim_survives_the_pipeline_intact():
    # Claim.value can now be a list (decided 2026-09-22) -- confirm the pipeline passes a
    # list value straight through the evidence check without mangling it into a string.
    # Both list items must actually be backed by the quote for the check to pass, so the
    # evidence here is the page's own text (which does mention both).
    claims = _all_not_found_claims()
    claims[FIELDS.index("products.names")] = {
        "field": "products.names", "status": "extracted",
        "value": ["Example Co", "project management"],
        "confidence": 0.9, "source_url": "https://example.com/", "page_title": "Example",
        "evidence": "Example Co is project management without all the nonsense.",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    assert not run.rejected
    names_claim = next(c for c in run.claims if c.field == "products.names")
    assert names_claim.value == ["Example Co", "project management"]


# --- Conflicting-claim evidence check (B-06/EVD-05, decided 2026-09-27) -----------------------
# Reproduces a real gap: conflicting claims used to reach run.claims with zero verification --
# the loop only ever called check_claim() for extracted/inferred, and check_claim() itself
# short-circuits conflicting to True. A hallucinated "these two pages disagree" claim would have
# sailed straight through. These two pages give the two real quotes a genuine conflict needs.

PAGE_HQ_A = CleanPage(url="https://example.com/about", title="About",
                       text="Headquartered in Bengaluru, India, since 2015.")
PAGE_HQ_B = CleanPage(url="https://example.com/contact", title="Contact",
                       text="Visit our Mumbai head office by appointment.")


def _conflicting_hq_claim(evidence):
    return {
        "field": "company_identity.headquarters", "status": "conflicting",
        "value": ["Bengaluru, India", "Mumbai"],
        "confidence": None, "source_url": None, "page_title": None,
        "evidence": evidence, "notes": None, "coverage": None,
    }


def test_conflicting_claim_verified_against_the_whole_corpus_and_both_values_kept():
    # The two evidence quotes come from two different pages -- confirms the pipeline checks
    # each one against the full crawled corpus rather than one fixed source_url, and keeps both
    # values intact (B-06's own wording: "both values are kept").
    claims = _all_not_found_claims()
    claims[FIELDS.index("company_identity.headquarters")] = _conflicting_hq_claim([
        "Headquartered in Bengaluru, India, since 2015.",
        "Visit our Mumbai head office by appointment.",
    ])
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [PAGE_HQ_A, PAGE_HQ_B], CONFIG, completer,
                          retrieved_at="2026-09-22")

    assert not run.rejected
    hq_claim = next(c for c in run.claims if c.field == "company_identity.headquarters")
    assert hq_claim.status == Status.conflicting
    assert hq_claim.value == ["Bengaluru, India", "Mumbai"]


def test_conflicting_claim_with_a_fabricated_quote_is_downgraded_and_logged():
    claims = _all_not_found_claims()
    claims[FIELDS.index("company_identity.headquarters")] = _conflicting_hq_claim([
        "Headquartered in Bengaluru, India, since 2015.",
        "This sentence appears on neither crawled page.",
    ])
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [PAGE_HQ_A, PAGE_HQ_B], CONFIG, completer,
                          retrieved_at="2026-09-22")

    assert len(run.rejected) == 1
    assert run.rejected[0].field == "company_identity.headquarters"
    hq_claim = next(c for c in run.claims if c.field == "company_identity.headquarters")
    assert hq_claim.status == Status.not_found  # never silently kept, per EVD-05


PRICING_PAGE = CleanPage(
    url="https://example.com/pricing",
    title="Pricing",
    text="Freelancer, $25/mo\nStudio, $59/mo\nPro, $99/mo\nUnlimited, $299/mo\n",
)


def test_multi_span_evidence_survives_the_pipeline_intact():
    # Reproduces the real basecamp.com pricing bug end-to-end: four plans on four separate
    # lines. Returned as a list value with one evidence quote per entry (instead of one
    # fabricated combined quote), the claim should survive the pipeline as `extracted`,
    # not get downgraded to not_found.
    claims = _all_not_found_claims()
    claims[FIELDS.index("pricing.public_plans")] = {
        "field": "pricing.public_plans", "status": "extracted",
        "value": ["Freelancer, $25/mo", "Studio, $59/mo", "Pro, $99/mo", "Unlimited, $299/mo"],
        "evidence": ["Freelancer, $25/mo", "Studio, $59/mo", "Pro, $99/mo", "Unlimited, $299/mo"],
        "confidence": 0.9, "source_url": "https://example.com/pricing", "page_title": "Pricing",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [PRICING_PAGE], CONFIG, completer, retrieved_at="2026-09-23")

    assert not run.rejected
    plans_claim = next(c for c in run.claims if c.field == "pricing.public_plans")
    assert plans_claim.status == Status.extracted
    assert plans_claim.value == [
        "Freelancer, $25/mo", "Studio, $59/mo", "Pro, $99/mo", "Unlimited, $299/mo",
    ]


# --- Partial credit for a multi-value claim, B-40 (decided 2026-09-27) -----------------------
# Reproduces the real temenos.com held-out bug: 3 named partnerships, 2 with real evidence and
# 1 whose evidence doesn't actually support it. Before this fix, one bad item downgraded the
# WHOLE claim to not_found, losing the 2 good partners too -- see wi/extract/pipeline.py and
# wi/validate/evidence.py's module docstrings for the full diagnosis.

def test_one_bad_item_in_a_list_claim_no_longer_discards_the_good_items():
    claims = _all_not_found_claims()
    claims[FIELDS.index("traction.partnerships")] = {
        "field": "traction.partnerships", "status": "extracted",
        "value": ["Alpha Bank", "Beta Consulting", "Gamma Corp"],
        "evidence": [
            "Alpha Bank is a Global Certified Partner.",
            "Beta Consulting is a Global Certified Partner.",
            "We also offer exclusive delivery services in the region.",  # real quote, but never names "Gamma Corp"
        ],
        "confidence": 0.9, "source_url": "https://example.com/partners", "page_title": "Partners",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})
    partners_page = CleanPage(
        url="https://example.com/partners", title="Partners",
        text="Alpha Bank is a Global Certified Partner. Beta Consulting is a Global Certified "
             "Partner. We also offer exclusive delivery services in the region.",
    )

    run = extract_claims("https://example.com/", [partners_page], CONFIG, completer, retrieved_at="2026-09-27")

    partners_claim = next(c for c in run.claims if c.field == "traction.partnerships")
    assert partners_claim.status == Status.extracted
    assert partners_claim.value == ["Alpha Bank", "Beta Consulting"]  # Gamma Corp dropped, not the whole claim
    assert partners_claim.evidence == [
        "Alpha Bank is a Global Certified Partner.", "Beta Consulting is a Global Certified Partner.",
    ]
    # The full original attempt (all 3 items) is still recorded in the audit trail.
    assert len(run.rejected) == 1
    assert run.rejected[0].field == "traction.partnerships"
    assert run.rejected[0].attempted_value == ["Alpha Bank", "Beta Consulting", "Gamma Corp"]
    assert "partial" in run.rejected[0].reason and "2/3" in run.rejected[0].reason


def test_a_list_claim_with_every_item_bad_still_falls_back_to_not_found_as_before():
    claims = _all_not_found_claims()
    claims[FIELDS.index("traction.partnerships")] = {
        "field": "traction.partnerships", "status": "extracted",
        "value": ["Delta Inc", "Epsilon LLC"],
        "evidence": ["This sentence never appears on the page.", "Neither does this one."],
        "confidence": 0.9, "source_url": "https://example.com/partners", "page_title": "Partners",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})
    partners_page = CleanPage(url="https://example.com/partners", title="Partners",
                               text="We work with a range of trusted partners.")

    run = extract_claims("https://example.com/", [partners_page], CONFIG, completer, retrieved_at="2026-09-27")

    partners_claim = next(c for c in run.claims if c.field == "traction.partnerships")
    assert partners_claim.status == Status.not_found
    assert len(run.rejected) == 1
    assert "partial" not in run.rejected[0].reason  # nothing survived -- the old, unqualified reason


def test_mismatched_value_evidence_length_keeps_the_paired_prefix_instead_of_discarding_everything():
    # B-49 (2026-09-27): reproduces the real bug found root-causing the B-48 held-out run -- the
    # model listed 3 certifications but only quoted 2 of them. Before this fix, Claim's schema
    # validator raised ValueError on the length mismatch and the WHOLE claim (all 3 items) was
    # discarded to not_found, even though the first 2 had perfectly good, verifiable quotes.
    claims = _all_not_found_claims()
    claims[FIELDS.index("traction.certifications")] = {
        "field": "traction.certifications", "status": "extracted",
        "value": ["SOC 2 Type II", "ISO/IEC 27001", "PCI DSS SAQ D"],  # 3 values
        "evidence": [
            "Certified for SOC 2 Type II.",
            "Certified for ISO/IEC 27001.",
        ],  # only 2 evidence quotes -- the mismatch B-49 fixes
        "confidence": 0.9, "source_url": "https://example.com/trust", "page_title": "Trust",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})
    trust_page = CleanPage(
        url="https://example.com/trust", title="Trust",
        text="Certified for SOC 2 Type II. Certified for ISO/IEC 27001.",
    )

    run = extract_claims("https://example.com/", [trust_page], CONFIG, completer, retrieved_at="2026-09-27")

    certs_claim = next(c for c in run.claims if c.field == "traction.certifications")
    assert certs_claim.status == Status.extracted
    assert certs_claim.value == ["SOC 2 Type II", "ISO/IEC 27001"]  # kept, not discarded
    assert any("B-49" in err for err in run.schema_errors)


def test_mismatched_value_evidence_pair_still_goes_through_real_verification():
    # The truncated prefix is NOT trusted blindly -- a paired item that still doesn't verify
    # (fabricated quote) is filtered out by the same per-item check (B-40) as always.
    claims = _all_not_found_claims()
    claims[FIELDS.index("traction.certifications")] = {
        "field": "traction.certifications", "status": "extracted",
        "value": ["SOC 2 Type II", "Made-Up Certification", "PCI DSS SAQ D"],  # 3 values
        "evidence": [
            "Certified for SOC 2 Type II.",
            "This sentence never appears on the page.",  # fabricated -- should still be dropped
        ],  # only 2 evidence quotes, so B-49 truncates value to the first 2 before verifying
        "confidence": 0.9, "source_url": "https://example.com/trust", "page_title": "Trust",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})
    trust_page = CleanPage(
        url="https://example.com/trust", title="Trust",
        text="Certified for SOC 2 Type II.",
    )

    run = extract_claims("https://example.com/", [trust_page], CONFIG, completer, retrieved_at="2026-09-27")

    certs_claim = next(c for c in run.claims if c.field == "traction.certifications")
    assert certs_claim.status == Status.extracted
    assert certs_claim.value == ["SOC 2 Type II"]  # the fabricated one is still caught and dropped


def test_mismatched_value_evidence_that_truncates_to_nothing_falls_back_to_not_found():
    claims = _all_not_found_claims()
    claims[FIELDS.index("traction.certifications")] = {
        "field": "traction.certifications", "status": "extracted",
        "value": ["SOC 2 Type II", "ISO/IEC 27001"],
        "evidence": [],  # zero evidence quotes at all
        "confidence": 0.9, "source_url": "https://example.com/trust", "page_title": "Trust",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})
    trust_page = CleanPage(url="https://example.com/trust", title="Trust", text="Certified.")

    run = extract_claims("https://example.com/", [trust_page], CONFIG, completer, retrieved_at="2026-09-27")

    certs_claim = next(c for c in run.claims if c.field == "traction.certifications")
    assert certs_claim.status == Status.not_found  # safe fallback, exactly as before this fix


def test_list_value_on_non_multi_value_field_is_rejected_by_schema_not_silently_kept():
    # Reproduces a real live-run bug (decided 2026-09-24): the model returned a fabricated list
    # value for customers.segments, a field that's supposed to stay a single string. Claim()
    # now rejects that shape outright, so the pipeline must backfill it to not_found exactly
    # like any other malformed claim -- never silently keep the model's invented list.
    claims = _all_not_found_claims()
    claims[FIELDS.index("customers.segments")] = {
        "field": "customers.segments", "status": "extracted",
        "value": ["Small Business", "Freelancers", "Non-Profits", "Teams"],
        "confidence": 0.8, "source_url": "https://example.com/", "page_title": "Example",
        "evidence": "Trusted by small businesses, freelancers, non-profits and teams.",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    assert any("customers.segments" in e for e in run.schema_errors)
    seg_claim = next(c for c in run.claims if c.field == "customers.segments")
    assert seg_claim.status == Status.not_found


def test_disallowed_inference_field_is_rejected_by_schema_not_silently_kept():
    claims = _all_not_found_claims()
    # customers.segments is NOT in INFERENCE_WHITELIST -- Claim() must reject this.
    claims[FIELDS.index("customers.segments")] = {
        "field": "customers.segments", "status": "inferred", "value": "Enterprises",
        "confidence": 0.6, "source_url": "https://example.com/", "page_title": "Example",
        "evidence": "Example Co is project management without all the nonsense.",
        "notes": "guessed from tone", "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    assert any("customers.segments" in e for e in run.schema_errors)
    seg_claim = next(c for c in run.claims if c.field == "customers.segments")
    assert seg_claim.status == Status.not_found


# --- B-01/B-02/B-08 confirmation tests (2026-09-27) -------------------------------------------
# Investigated as part of the same behaviour-testing pass as B-03/B-10/B-18/B-07 above, but
# these three turned out to already be correctly handled by existing code (pricing.public_plans'
# free-text list design from the basecamp.com multi-span fix; pricing.sales_motion already in
# INFERENCE_WHITELIST; not_found's existing coverage requirement) -- no code changes, just the
# dedicated pipeline-level tests these behaviours were missing.

def test_B01_pricing_page_plan_amount_currency_and_period_captured_with_quote():
    # A pricing page's plan line ("Starter -- Rs. 499/month") captured as a single extracted,
    # list-shaped pricing.public_plans entry, quoted verbatim -- covers plan name, amount,
    # currency symbol and billing period all riding in the one free-text value/evidence pair.
    page = CleanPage(
        url="https://example.com/pricing", title="Pricing",
        text="Starter -- Rs. 499/month\nGrowth -- Rs. 1499/month",
    )
    claims = _all_not_found_claims()
    claims[FIELDS.index("pricing.public_plans")] = {
        "field": "pricing.public_plans", "status": "extracted",
        "value": ["Starter -- Rs. 499/month", "Growth -- Rs. 1499/month"],
        "evidence": ["Starter -- Rs. 499/month", "Growth -- Rs. 1499/month"],
        "confidence": 0.9, "source_url": "https://example.com/pricing", "page_title": "Pricing",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [page], CONFIG, completer, retrieved_at="2026-09-27")

    assert not run.rejected
    plans_claim = next(c for c in run.claims if c.field == "pricing.public_plans")
    assert plans_claim.status == Status.extracted
    assert plans_claim.value == ["Starter -- Rs. 499/month", "Growth -- Rs. 1499/month"]


def test_B02_contact_sales_only_infers_sales_led_motion_and_leaves_plans_not_found():
    # No amounts anywhere on the page -- only a "Contact sales" call to action. sales_motion
    # is correctly inferred sales-led (whitelisted field, real quote, notes explaining the
    # inference); public_plans stays an honest not_found rather than a guess.
    page = CleanPage(
        url="https://example.com/pricing", title="Pricing",
        text="Enterprise plans tailored to your needs. Contact sales to get a quote.",
    )
    claims = _all_not_found_claims()
    claims[FIELDS.index("pricing.public_plans")] = {
        "field": "pricing.public_plans", "status": "not_found", "value": None,
        "confidence": None, "source_url": None, "page_title": None, "evidence": None,
        "notes": None,
        "coverage": {"page_types_checked": ["pricing"], "pages_checked": 1},
    }
    claims[FIELDS.index("pricing.sales_motion")] = {
        "field": "pricing.sales_motion", "status": "inferred",
        "value": "Sales-led (contact sales, no self-serve checkout shown)",
        "confidence": 0.7, "source_url": "https://example.com/pricing", "page_title": "Pricing",
        "evidence": "Contact sales to get a quote.",
        "notes": "No public pricing or self-serve checkout is shown; the only path to buy is "
                 "contacting sales.",
        "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [page], CONFIG, completer, retrieved_at="2026-09-27")

    assert not run.rejected
    plans_claim = next(c for c in run.claims if c.field == "pricing.public_plans")
    assert plans_claim.status == Status.not_found
    assert plans_claim.coverage is not None
    motion_claim = next(c for c in run.claims if c.field == "pricing.sales_motion")
    assert motion_claim.status == Status.inferred
    assert "sales-led" in motion_claim.value.lower()


def test_B08_no_customer_evidence_leaves_named_customers_not_found_with_coverage():
    # No logos, case studies or testimonials anywhere on the crawled pages -- named_customers
    # must stay not_found, and (EVD-04) must carry a coverage record of what was checked.
    page = CleanPage(
        url="https://example.com/", title="Example Co",
        text="Example Co is project management without all the nonsense.",
    )
    claims = _all_not_found_claims()
    claims[FIELDS.index("traction.named_customers")] = {
        "field": "traction.named_customers", "status": "not_found", "value": None,
        "confidence": None, "source_url": None, "page_title": None, "evidence": None,
        "notes": None,
        "coverage": {"page_types_checked": ["homepage", "customers", "case-studies"],
                     "pages_checked": 1},
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [page], CONFIG, completer, retrieved_at="2026-09-27")

    customers_claim = next(c for c in run.claims if c.field == "traction.named_customers")
    assert customers_claim.status == Status.not_found
    assert customers_claim.coverage is not None
    assert customers_claim.coverage.pages_checked == 1


# --- Input-budget guard (decided 2026-09-26 after a real bajajauto.com crash: 25 real pages
# added up to more tokens than gpt-4o-mini's context window, and the whole run died with an
# unhandled openai.BadRequestError) -------------------------------------------------------

def _page(url: str, n_chars: int) -> CleanPage:
    return CleanPage(url=url, title=url, text="x" * n_chars)


def test_fit_pages_to_input_budget_keeps_pages_that_fit():
    pages = [_page("https://example.com/a", 100), _page("https://example.com/b", 100)]
    kept, dropped = _fit_pages_to_input_budget(pages, max_input_tokens=1000)  # 4000 chars
    assert kept == pages
    assert dropped == []


def test_fit_pages_to_input_budget_drops_lowest_priority_pages_first():
    # pages arrive in crawl priority order; trimming must drop from the END, keeping the
    # earlier (higher-priority) pages intact.
    pages = [_page("https://example.com/a", 100), _page("https://example.com/b", 100),
              _page("https://example.com/c", 100)]
    kept, dropped = _fit_pages_to_input_budget(pages, max_input_tokens=50, chars_per_token=1)  # 50 chars
    assert [p.url for p in kept] == ["https://example.com/a"]
    assert dropped == ["https://example.com/b", "https://example.com/c"]


def test_fit_pages_to_input_budget_always_keeps_at_least_one_page():
    # Even a single page that alone exceeds the budget is kept -- a partial extraction from
    # one page beats an empty one from zero.
    pages = [_page("https://example.com/huge", 10_000)]
    kept, dropped = _fit_pages_to_input_budget(pages, max_input_tokens=10, chars_per_token=1)
    assert kept == pages
    assert dropped == []


def test_extract_claims_drops_pages_over_the_configured_input_budget():
    # Integration: two pages, a tiny budget that only fits the first. The FakeCompleter must
    # never see the second page's text, and run.dropped_pages must record what was cut.
    page_a = CleanPage(url="https://example.com/a", title="A", text="Example Co home page text.")
    page_b = CleanPage(url="https://example.com/b", title="B", text="Second page text that must not reach the LLM.")
    config = {"llm": {"small_model": "gpt-4o-mini", "max_input_tokens_per_run": 10}}  # ~40 chars
    completer = FakeCompleter({"claims": _all_not_found_claims()})

    run = extract_claims("https://example.com/", [page_a, page_b], config, completer,
                          retrieved_at="2026-09-22")

    assert run.dropped_pages == ["https://example.com/b"]
    user_content = completer.last_messages[1]["content"]
    assert "Example Co home page text." in user_content
    assert "Second page text that must not reach the LLM." not in user_content


def test_extract_claims_with_no_input_budget_configured_sends_every_page():
    # Backward compatibility: a config without llm.max_input_tokens_per_run (like this
    # file's own CONFIG) must behave exactly as before -- no trimming at all.
    page_a = CleanPage(url="https://example.com/a", title="A", text="First page.")
    page_b = CleanPage(url="https://example.com/b", title="B", text="Second page.")
    completer = FakeCompleter({"claims": _all_not_found_claims()})

    run = extract_claims("https://example.com/", [page_a, page_b], CONFIG, completer,
                          retrieved_at="2026-09-22")

    assert run.dropped_pages == []
    user_content = completer.last_messages[1]["content"]
    assert "First page." in user_content
    assert "Second page." in user_content


# --- Evidence check may cite the page title, not just the body text (decided 2026-09-26,
# after company_identity.name was evidence-rejected on 2 of 4 live dev-set runs) ----------

def test_extracted_claim_with_evidence_only_in_the_page_title_is_accepted():
    # The model is shown both TITLE and TEXT for every page (see wi/extract/prompt.py); a
    # quote drawn from the title is real content it was given, not a fabrication.
    page = CleanPage(url="https://example.com/", title="Widgetco -- Home",
                      text="Welcome to our site. We sell things.")
    claims = _all_not_found_claims()
    claims[FIELDS.index("company_identity.name")] = {
        "field": "company_identity.name", "status": "extracted", "value": "Widgetco",
        "confidence": 1.0, "source_url": "https://example.com/", "page_title": "Widgetco -- Home",
        "evidence": "Widgetco -- Home", "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [page], CONFIG, completer, retrieved_at="2026-09-22")

    name_claim = next(c for c in run.claims if c.field == "company_identity.name")
    assert name_claim.status == Status.extracted
    assert name_claim.value == "Widgetco"
    assert run.rejected == []


# --- source_url is normalised before the evidence-text lookup (decided 2026-09-26, after
# company_identity.name failed evidence -- value and evidence BOTH the literal string "Bajaj
# Auto" -- on a real bajajauto.com run even after the title fix above. An exact-string match
# still failing rules out a fuzzy-matching or title-vs-body explanation; the only thing that
# reliably produces that symptom is check_claim() being handed empty page_text, which happens
# when claim.source_url doesn't match any crawled page's URL at all) -------------------------

def test_claim_source_url_with_trailing_slash_mismatch_still_finds_the_page_text():
    # crawl_site's own normalize_url would fetch/store this page as
    # "https://example.com/about" (no trailing slash) -- if the model reproduces it WITH a
    # trailing slash, the lookup must not silently fall through to empty page text.
    page = CleanPage(url="https://example.com/about", title="About",
                      text="Example Co is a real company that makes real things.")
    claims = _all_not_found_claims()
    claims[FIELDS.index("company_identity.description")] = {
        "field": "company_identity.description", "status": "extracted",
        "value": "Example Co is a real company that makes real things.",
        "confidence": 1.0, "source_url": "https://example.com/about/",  # trailing slash the crawled page doesn't have
        "page_title": "About",
        "evidence": "Example Co is a real company that makes real things.",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [page], CONFIG, completer, retrieved_at="2026-09-22")

    desc_claim = next(c for c in run.claims if c.field == "company_identity.description")
    assert desc_claim.status == Status.extracted
    assert run.rejected == []


# --- Corpus-wide quote fallback, the "CloseKnit Health" fix (B-36, decided 2026-09-27) -------
# End-to-end version of the real thoughtbot.com dev-set bug: the model cites the case-studies
# INDEX page as source_url for a fact that's only genuinely quotable on that client's own
# DEDICATED subpage -- also crawled in the same run, just not the page named. See
# wi/validate/evidence.py's module docstring for the full live diagnosis.

INDEX_PAGE = CleanPage(
    url="https://example.com/case-studies", title="Case studies",
    text="CloseKnit -- a healthcare scheduling platform. Other Client Inc.",
)
SUBPAGE = CleanPage(
    url="https://example.com/case-studies/closeknit-health", title="CloseKnit Health",
    text='Client: CloseKnit Health. "Working with the team was great," says a director '
         "at CloseKnit Health.",
)


def test_claim_citing_the_wrong_crawled_page_still_passes_via_the_corpus_fallback():
    claims = _all_not_found_claims()
    claims[FIELDS.index("traction.named_customers")] = {
        "field": "traction.named_customers", "status": "extracted", "value": "CloseKnit Health",
        "confidence": 0.9, "source_url": "https://example.com/case-studies",  # the WRONG page
        "page_title": "Case studies", "evidence": "CloseKnit Health",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [INDEX_PAGE, SUBPAGE], CONFIG, completer,
                          retrieved_at="2026-09-27")

    claim = next(c for c in run.claims if c.field == "traction.named_customers")
    assert claim.status == Status.extracted
    assert claim.value == "CloseKnit Health"
    assert run.rejected == []


def test_claim_citing_a_page_where_the_quote_truly_never_appears_still_fails():
    # Same two pages, but the quote is fabricated outright -- must still be rejected regardless
    # of the corpus fallback now being available.
    claims = _all_not_found_claims()
    claims[FIELDS.index("traction.named_customers")] = {
        "field": "traction.named_customers", "status": "extracted", "value": "NorthLedger Inc",
        "confidence": 0.9, "source_url": "https://example.com/case-studies",
        "page_title": "Case studies",
        "evidence": "NorthLedger Inc has used our platform since 2019",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [INDEX_PAGE, SUBPAGE], CONFIG, completer,
                          retrieved_at="2026-09-27")

    assert len(run.rejected) == 1
    assert run.rejected[0].field == "traction.named_customers"
    claim = next(c for c in run.claims if c.field == "traction.named_customers")
    assert claim.status == Status.not_found


def test_rejected_claim_records_the_source_url_the_model_claimed():
    # Diagnostic added precisely so a real run's output can show whether a "quote not found"
    # rejection is a genuinely fabricated quote or the model citing a URL that was never
    # actually crawled at all (empty page_text either way, but very different root causes).
    page = CleanPage(url="https://example.com/", title="Example", text="Nothing relevant here.")
    claims = _all_not_found_claims()
    claims[FIELDS.index("company_identity.name")] = {
        "field": "company_identity.name", "status": "extracted", "value": "Example Co",
        "confidence": 1.0, "source_url": "https://example.com/never-crawled",
        "page_title": None, "evidence": "Example Co", "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})

    run = extract_claims("https://example.com/", [page], CONFIG, completer, retrieved_at="2026-09-22")

    assert len(run.rejected) == 1
    assert run.rejected[0].source_url == "https://example.com/never-crawled"


# diagnostics_from_run (2026-09-27, crawl-coverage-misses investigation, see PROGRESS.md):
# run.rejected and run.schema_errors were always computed correctly, but run_site.py only ever
# printed them to the console -- never wrote them to data/runs/<slug>.json, so a "miss" in
# eval/baseline.py looked identical whether the model was rejected, failed schema validation,
# or never attempted the field at all. These tests cover the function that makes that ledger
# persistable.

def test_diagnostics_from_run_surfaces_a_rejected_claim_by_field_and_reason():
    claims = _all_not_found_claims()
    claims[0] = {
        "field": "company_identity.name", "status": "extracted", "value": "Wrong Name Inc",
        "confidence": 0.9, "source_url": "https://example.com/", "page_title": "Example",
        "evidence": "This sentence does not appear on the page at all.",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})
    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    diag = diagnostics_from_run(run)

    assert len(diag["rejected"]) == 1
    assert diag["rejected"][0]["field"] == "company_identity.name"
    assert diag["rejected"][0]["attempted_value"] == "Wrong Name Inc"
    assert "reason" in diag["rejected"][0]
    assert diag["schema_errors"] == []
    assert diag["rejected_announcements"] == []


def test_diagnostics_from_run_surfaces_schema_errors_and_is_json_serialisable():
    import json

    claims = _all_not_found_claims()
    # customers.segments is not in MULTI_VALUE_FIELDS -- a list value fails schema validation
    # and is logged to schema_errors, exactly the real basecamp.com finding this fix was built
    # to make visible without re-running the site.
    claims[FIELDS.index("customers.segments")] = {
        "field": "customers.segments", "status": "extracted", "value": ["a", "b"],
        "confidence": 0.8, "source_url": "https://example.com/", "page_title": "Example",
        "evidence": "Example Co is project management without all the nonsense.",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})
    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    diag = diagnostics_from_run(run)

    assert len(diag["schema_errors"]) == 1
    assert "customers.segments" in diag["schema_errors"][0]
    json.dumps(diag)  # must not raise -- this is going straight into a run's output JSON


def test_diagnostics_from_run_on_a_clean_run_is_all_empty():
    claims = _all_not_found_claims()
    claims[0] = {
        "field": "company_identity.name", "status": "extracted", "value": "Example Co",
        "confidence": 1.0, "source_url": "https://example.com/", "page_title": "Example",
        "evidence": "Example Co is project management without all the nonsense.",
        "notes": None, "coverage": None,
    }
    completer = FakeCompleter({"claims": claims})
    run = extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")

    diag = diagnostics_from_run(run)

    assert diag == {"rejected": [], "schema_errors": [], "rejected_announcements": []}


# --- B-77: cite the page the evidence is actually on ------------------------------------------

def _named_customers_claim(value, evidence, source_url, page_title="Case studies"):
    claims = _all_not_found_claims()
    claims[FIELDS.index("traction.named_customers")] = {
        "field": "traction.named_customers", "status": "extracted", "value": value,
        "confidence": 0.9, "source_url": source_url, "page_title": page_title,
        "evidence": evidence, "notes": None, "coverage": None,
    }
    return claims


def test_b77_quote_found_only_on_another_page_is_re_pointed_to_that_page():
    # The B-36 case above: the quote is real, but on the client's own page, not the index cited.
    # Found on freshworks.com: "Freshsales Pricing & Plans" cited under /products is the title of
    # /crm/pricing.
    claims = _named_customers_claim("CloseKnit Health", "CloseKnit Health",
                                    "https://example.com/case-studies")
    run = extract_claims("https://example.com/", [INDEX_PAGE, SUBPAGE], CONFIG,
                          FakeCompleter({"claims": claims}), retrieved_at="2026-10-07")

    claim = next(c for c in run.claims if c.field == "traction.named_customers")
    assert claim.status == Status.extracted                         # acceptance unchanged
    assert claim.source_url == "https://example.com/case-studies/closeknit-health"
    assert claim.page_title == "CloseKnit Health"
    assert any("B-77" in e and "re-pointed" in e for e in run.schema_errors)


def test_b77_quote_on_the_cited_page_keeps_its_citation():
    claims = _named_customers_claim("Other Client Inc", "Other Client Inc.",
                                    "https://example.com/case-studies")
    run = extract_claims("https://example.com/", [INDEX_PAGE, SUBPAGE], CONFIG,
                          FakeCompleter({"claims": claims}), retrieved_at="2026-10-07")

    claim = next(c for c in run.claims if c.field == "traction.named_customers")
    assert claim.source_url == "https://example.com/case-studies"
    assert not any("B-77" in e for e in run.schema_errors)


def test_b77_evidence_split_across_the_cited_page_and_another_is_left_and_noted():
    # One quote on the cited index, one only on the client page: no single page holds both, so
    # the citation stays and the split is recorded. The claim itself still passes as before.
    claims = _named_customers_claim(["Other Client Inc", "CloseKnit Health"],
                                    ["Other Client Inc.", "CloseKnit Health"],
                                    "https://example.com/case-studies")
    run = extract_claims("https://example.com/", [INDEX_PAGE, SUBPAGE], CONFIG,
                          FakeCompleter({"claims": claims}), retrieved_at="2026-10-07")

    claim = next(c for c in run.claims if c.field == "traction.named_customers")
    assert claim.status == Status.extracted
    assert claim.source_url == "https://example.com/case-studies"
    assert any("B-77" in e and "more than one page" in e for e in run.schema_errors)


def test_b77_a_cited_url_that_was_never_crawled_moves_to_the_page_holding_the_quote():
    claims = _named_customers_claim("CloseKnit Health", "CloseKnit Health",
                                    "https://example.com/customers/closeknit")  # never crawled
    run = extract_claims("https://example.com/", [INDEX_PAGE, SUBPAGE], CONFIG,
                          FakeCompleter({"claims": claims}), retrieved_at="2026-10-07")

    claim = next(c for c in run.claims if c.field == "traction.named_customers")
    assert claim.source_url == "https://example.com/case-studies/closeknit-health"


# --- B-79: not_found coverage comes from the pages actually sent -----------------------------

def test_b79_model_reported_coverage_is_replaced_by_the_pages_sent():
    # Found on freshworks.com: four not_found fields said "home, about, 2 pages checked" after the
    # model was sent 40 pages.
    pages = [CleanPage(url=f"https://example.com/p{i}", title=f"P{i}", text="Nothing relevant.")
             for i in range(3)]
    claims = _all_not_found_claims()   # every one claims {"homepage"}, 1 page
    run = extract_claims("https://example.com/", pages, CONFIG, FakeCompleter({"claims": claims}),
                          retrieved_at="2026-10-07")

    for claim in run.claims:
        assert claim.status == Status.not_found
        assert claim.coverage.pages_checked == 3
        assert claim.coverage.page_types_checked == ["all pages sent to the model"]


def test_b79_pages_dropped_by_the_input_budget_are_not_counted_as_checked():
    pages = [_page("https://example.com/a", 30), _page("https://example.com/b", 30),
             _page("https://example.com/c", 30)]
    config = {"llm": {"small_model": "gpt-4o-mini", "max_input_tokens_per_run": 10}}  # ~40 chars
    run = extract_claims("https://example.com/", pages, config,
                          FakeCompleter({"claims": _all_not_found_claims()}), retrieved_at="2026-10-07")

    assert len(run.dropped_pages) == 2
    assert {c.coverage.pages_checked for c in run.claims} == {1}
