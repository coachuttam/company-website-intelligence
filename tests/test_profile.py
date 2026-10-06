"""Tests for wi.profile.builder (Final PRD OUT-01, B-19). Claims are constructed directly
(never via a real LLM call) so these test the profile-assembly logic in isolation from
extraction -- build_profile() is pure reorganisation of an already-built ExtractionRun.
"""
from __future__ import annotations

import json

from wi.crawl.clean import CleanPage
from wi.extract.fields import FIELDS
from wi.extract.pipeline import ExtractionRun, RejectedClaim, extract_claims
from wi.extract.llm import LLMResult
from wi.profile.builder import GROUP_MAP, build_profile
from wi.schemas.announcement import Announcement
from wi.schemas.claim import Claim, Coverage, Status


def _not_found(field: str, pages_checked: int = 3) -> Claim:
    return Claim(
        claim_id=f"nf:{field}", field=field, status=Status.not_found,
        coverage=Coverage(page_types_checked=["homepage"], pages_checked=pages_checked),
    )


def _extracted(field: str, value, evidence="Some real page text.", confidence=0.9) -> Claim:
    return Claim(
        claim_id=f"ex:{field}", field=field, status=Status.extracted, value=value,
        confidence=confidence, source_url="https://example.com/", page_title="Example",
        evidence=evidence, retrieved_at="2026-09-27",
    )


def _inferred(field: str, value, notes="Inferred from context.") -> Claim:
    return Claim(
        claim_id=f"inf:{field}", field=field, status=Status.inferred, value=value,
        confidence=0.6, source_url="https://example.com/", page_title="Example",
        evidence="Contact sales for pricing.", retrieved_at="2026-09-27", notes=notes,
    )


def _conflicting(field: str, value=None) -> Claim:
    # B-06/EVD-05 (2026-09-27): conflicting claims now require a paired value/evidence list
    # (see wi/schemas/claim.py) -- a single descriptive string is no longer valid.
    value = value or ["A on page 1", "B on page 2"]
    return Claim(
        claim_id=f"cf:{field}", field=field, status=Status.conflicting, value=value,
        evidence=["Headquartered in A.", "Headquartered in B."], retrieved_at="2026-09-27",
    )


def _announcement(text="$5M Series A funding round", category="funding", date="March 2025"):
    return Announcement(
        announcement_id="ann:0", text=text, category=category, date=date,
        source_url="https://example.com/newsroom",
        evidence="We're thrilled to announce our $5M Series A funding round.",
        retrieved_at="2026-09-27",
    )


def _run_with(claims, rejected_count=0, dropped_pages=None, announcements=None) -> ExtractionRun:
    run = ExtractionRun(site_url="https://example.com/")
    run.claims = claims
    run.rejected = [
        RejectedClaim(field="x", reason="test", attempted_value="v", attempted_evidence="e")
        for _ in range(rejected_count)
    ]
    run.dropped_pages = dropped_pages or []
    run.announcements = announcements or []
    return run


def _all_not_found_run() -> ExtractionRun:
    return _run_with([_not_found(f) for f in FIELDS])


def test_group_map_covers_every_field_prefix_in_fields_py():
    # A living contract: if fields.py ever grows a field under a new prefix (a 7th group, say),
    # this fails loudly instead of that field silently landing under a group named after its
    # raw prefix (GROUP_MAP.get(prefix, prefix) falls back to the prefix itself -- harmless for
    # display but a sign this mapping table was never updated to match).
    prefixes = {f.partition(".")[0] for f in FIELDS}
    assert prefixes <= set(GROUP_MAP)


def test_populated_field_appears_under_its_group_with_claim_id():
    claims = [_not_found(f) for f in FIELDS]
    idx = FIELDS.index("company_identity.name")
    claims[idx] = _extracted("company_identity.name", "Example Co")
    run = _run_with(claims)

    result = build_profile(run, pages_scanned=3, retrieved_at="2026-09-27")

    entry = result["profile"]["company_identity"]["name"]
    assert entry == {"value": "Example Co", "status": "extracted",
                      "claim_id": "ex:company_identity.name", "confidence": 0.9}
    # not_found fields never appear as an entry under their group (PRD Section 6 item 9).
    assert "headquarters" not in result["profile"]["company_identity"]


def test_inferred_field_also_appears_under_its_group():
    claims = [_not_found(f) for f in FIELDS]
    idx = FIELDS.index("pricing.sales_motion")
    claims[idx] = _inferred("pricing.sales_motion", "sales-led")
    run = _run_with(claims)

    result = build_profile(run, pages_scanned=3, retrieved_at="2026-09-27")

    assert result["profile"]["pricing_commercial"]["sales_motion"]["status"] == "inferred"


def test_not_found_field_lands_in_gaps_conflicts_not_under_its_group():
    run = _all_not_found_run()
    result = build_profile(run, pages_scanned=2, retrieved_at="2026-09-27")

    assert result["profile"]["company_identity"] == {}
    gap = next(g for g in result["profile"]["gaps_conflicts"]
               if g["field"] == "company_identity.headquarters")
    assert gap["status"] == "not_found"
    assert gap["claim_id"] == "nf:company_identity.headquarters"


def test_conflicting_field_lands_in_gaps_conflicts_not_under_its_group():
    # EVD-05: a conflict must never be silently resolved to one value under the main heading.
    claims = [_not_found(f) for f in FIELDS]
    idx = FIELDS.index("company_identity.headquarters")
    claims[idx] = _conflicting("company_identity.headquarters")
    run = _run_with(claims)

    result = build_profile(run, pages_scanned=2, retrieved_at="2026-09-27")

    assert "headquarters" not in result["profile"]["company_identity"]
    gap = next(g for g in result["profile"]["gaps_conflicts"]
               if g["field"] == "company_identity.headquarters")
    assert gap["status"] == "conflicting"
    assert gap["claim_id"] == "cf:company_identity.headquarters"


def test_missing_claim_for_a_field_is_treated_as_not_found_defensively():
    # Shouldn't happen in practice (extract_claims guarantees one claim per field), but a
    # profile builder crashing over a missing field would be strictly worse than an honest gap.
    claims = [_not_found(f) for f in FIELDS if f != "comparisons.named_alternatives"]
    run = _run_with(claims)

    result = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")

    gap = next(g for g in result["profile"]["gaps_conflicts"]
               if g["field"] == "comparisons.named_alternatives")
    assert gap["status"] == "not_found"
    assert gap["claim_id"] is None


def test_coverage_counts_populated_inferred_conflicting_and_not_found():
    claims = [_not_found(f) for f in FIELDS]
    claims[FIELDS.index("company_identity.name")] = _extracted("company_identity.name", "Example Co")
    claims[FIELDS.index("pricing.sales_motion")] = _inferred("pricing.sales_motion", "sales-led")
    claims[FIELDS.index("company_identity.headquarters")] = _conflicting("company_identity.headquarters")
    run = _run_with(claims)

    coverage = build_profile(run, pages_scanned=5, retrieved_at="2026-09-27")["profile"]["coverage"]

    assert coverage["pages_scanned"] == 5
    assert coverage["total_fields"] == len(FIELDS)
    assert coverage["fields_populated"] == 2  # extracted + inferred
    assert coverage["fields_inferred"] == 1
    assert coverage["fields_conflicting"] == 1
    assert coverage["fields_not_found"] == len(FIELDS) - 3
    assert coverage["last_retrieved_at"] == "2026-09-27"


def test_evidence_support_rate_is_none_when_nothing_was_attempted():
    run = _all_not_found_run()  # every field genuinely not_found, nothing rejected either
    coverage = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")["profile"]["coverage"]
    assert coverage["evidence_support_rate"] is None


def test_evidence_support_rate_counts_survived_over_attempted():
    claims = [_not_found(f) for f in FIELDS]
    claims[FIELDS.index("company_identity.name")] = _extracted("company_identity.name", "Example Co")
    run = _run_with(claims, rejected_count=1)  # 1 survived, 1 was rejected -> 1/2

    coverage = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")["profile"]["coverage"]
    assert coverage["evidence_support_rate"] == 0.5


def test_limit_reached_true_when_input_budget_guard_dropped_pages():
    run = _all_not_found_run()
    run.dropped_pages = ["https://example.com/low-priority"]
    result = build_profile(run, pages_scanned=10, retrieved_at="2026-09-27")
    assert result["limit_reached"] is True


def test_limit_reached_true_when_crawl_budget_exhausted():
    run = _all_not_found_run()  # no dropped_pages at all
    result = build_profile(run, pages_scanned=25, retrieved_at="2026-09-27",
                            crawl_budget_exhausted=True)
    assert result["limit_reached"] is True


def test_limit_reached_false_when_neither_limit_was_hit():
    run = _all_not_found_run()
    result = build_profile(run, pages_scanned=3, retrieved_at="2026-09-27")
    assert result["limit_reached"] is False


def test_schema_version_is_stamped():
    run = _all_not_found_run()
    result = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")
    assert result["schema_version"] == "schema-v1"

    result_custom = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27",
                                   schema_version="schema-v2")
    assert result_custom["schema_version"] == "schema-v2"


def test_claims_list_serialises_every_run_claim():
    run = _all_not_found_run()
    result = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")
    assert len(result["claims"]) == len(FIELDS)
    assert all(isinstance(c, dict) for c in result["claims"])
    # Round-trips through JSON cleanly -- this is what actually gets written to disk.
    json.dumps(result)


def test_every_field_is_accounted_for_exactly_once_across_groups_and_gaps():
    claims = [_not_found(f) for f in FIELDS]
    claims[FIELDS.index("company_identity.name")] = _extracted("company_identity.name", "Example Co")
    run = _run_with(claims)

    result = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")

    placed_fields = set()
    for group_name in GROUP_MAP.values():
        prefix = next(p for p, g in GROUP_MAP.items() if g == group_name)
        for short_name in result["profile"][group_name]:
            # "announcements" (B-07/OUT-04, added 2026-09-27) is a THIRD kind of entry under
            # evidence_traction, alongside ordinary field entries and gaps_conflicts -- it is
            # never one of the 15 fields (that's the whole point of B-07), so it deliberately
            # doesn't reconstruct to a "prefix.short_name" in FIELDS. See wi/profile/builder.py's
            # docstring.
            if group_name == "evidence_traction" and short_name == "announcements":
                continue
            placed_fields.add(f"{prefix}.{short_name}")
    placed_fields |= {g["field"] for g in result["profile"]["gaps_conflicts"]}

    assert placed_fields == set(FIELDS)


def test_end_to_end_with_extract_claims_output():
    # Integration check: a real ExtractionRun produced by extract_claims() (via a fake
    # completer, never a real LLM call) feeds build_profile() without any special-casing.
    class FakeCompleter:
        def complete(self, messages, model):
            claims = [{"field": f, "status": "not_found", "value": None, "confidence": None,
                       "source_url": None, "page_title": None, "evidence": None, "notes": None,
                       "coverage": {"page_types_checked": ["homepage"], "pages_checked": 1}}
                      for f in FIELDS]
            claims[0] = {
                "field": "company_identity.name", "status": "extracted", "value": "Example Co",
                "confidence": 0.95, "source_url": "https://example.com/", "page_title": "Example",
                "evidence": "Example Co is project management without all the nonsense.",
                "notes": None, "coverage": None,
            }
            return LLMResult(content=json.dumps({"claims": claims}), model=model,
                              prompt_tokens=10, completion_tokens=5, total_tokens=15,
                              elapsed_s=0.01)

    page = CleanPage(url="https://example.com/", title="Example",
                      text="Example Co is project management without all the nonsense.")
    run = extract_claims("https://example.com/", [page], {"llm": {"small_model": "gpt-4o-mini"}},
                          FakeCompleter(), retrieved_at="2026-09-27")

    result = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")

    assert result["profile"]["company_identity"]["name"]["value"] == "Example Co"
    assert result["schema_version"] == "schema-v1"
    assert result["limit_reached"] is False


# --- B-07/OUT-04: dated company-reported announcements appear under evidence_traction, never
# as a core field. OUT-04's own acceptance criterion: "A funding-statement fixture appears
# under `evidence_traction` with a date and quote." -----------------------------------------

def test_B07_funding_announcement_appears_under_evidence_traction_with_date_and_quote():
    run = _run_with([_not_found(f) for f in FIELDS], announcements=[_announcement()])

    result = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")

    announcements = result["profile"]["evidence_traction"]["announcements"]
    assert len(announcements) == 1
    entry = announcements[0]
    assert entry["text"] == "$5M Series A funding round"
    assert entry["category"] == "funding"
    assert entry["date"] == "March 2025"  # the acceptance criterion's "a date"
    assert entry["evidence"]  # the acceptance criterion's "a quote"


def test_no_announcements_gives_an_empty_list_not_a_missing_key():
    run = _run_with([_not_found(f) for f in FIELDS])  # no announcements passed

    result = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")

    assert result["profile"]["evidence_traction"]["announcements"] == []


def test_announcement_never_counted_as_or_placed_under_a_core_field():
    # The whole point of B-07/OUT-04: a funding statement must never be presented as one of the
    # 15 core fields (e.g. mistakenly folded into traction.partnerships or gaps_conflicts).
    run = _run_with([_not_found(f) for f in FIELDS], announcements=[_announcement()])

    result = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")

    for group_name in GROUP_MAP.values():
        for key, entry in result["profile"][group_name].items():
            if key == "announcements":
                continue
            assert "Series A" not in json.dumps(entry)
    assert not any("Series A" in json.dumps(g) for g in result["profile"]["gaps_conflicts"])


def test_announcements_also_appear_in_the_top_level_audit_ledger():
    # Mirrors how "claims" is both grouped into the profile AND kept as a flat top-level ledger
    # (OUT-01: two outputs, an evidence ledger and a profile) -- announcements get the same
    # treatment.
    run = _run_with([_not_found(f) for f in FIELDS], announcements=[_announcement()])

    result = build_profile(run, pages_scanned=1, retrieved_at="2026-09-27")

    assert len(result["announcements"]) == 1
    assert result["announcements"][0]["text"] == "$5M Series A funding round"
