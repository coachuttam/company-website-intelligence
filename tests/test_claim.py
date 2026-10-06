"""Claim contract tests. Maps to PRD requirements EVD-01, EVD-03, EVD-04 and behaviours B-09, B-10."""
import pytest
from pydantic import ValidationError

from wi.schemas.claim import Claim, Coverage, Status

GOOD = dict(
    claim_id="c001",
    field="company_identity.name",
    value="NorthLedger",
    status="extracted",
    source_url="https://northledger.example/about",
    evidence="NorthLedger helps small businesses send invoices.",
    retrieved_at="2026-09-21",
)


def test_valid_extracted_claim_passes():
    assert Claim(**GOOD).status == Status.extracted


@pytest.mark.parametrize("missing", ["value", "source_url", "evidence", "retrieved_at"])
def test_extracted_claim_missing_evidence_field_fails(missing):
    data = {**GOOD}
    data.pop(missing)
    with pytest.raises(ValidationError):
        Claim(**data)


def test_not_found_requires_coverage():
    with pytest.raises(ValidationError):
        Claim(claim_id="c002", field="pricing.public_plans", status="not_found")


def test_not_found_with_coverage_passes():
    c = Claim(
        claim_id="c002",
        field="pricing.public_plans",
        status="not_found",
        coverage=Coverage(page_types_checked=["pricing", "product"], pages_checked=12),
    )
    assert c.value is None


def test_inference_on_non_whitelisted_field_fails():  # B-09
    with pytest.raises(ValidationError):
        Claim(**{**GOOD, "field": "company_identity.headquarters", "status": "inferred", "notes": "guess"})


def test_inference_on_whitelisted_field_needs_note():
    data = {**GOOD, "field": "pricing.sales_motion", "value": "sales-led", "status": "inferred"}
    with pytest.raises(ValidationError):
        Claim(**data)
    assert Claim(**{**data, "notes": "Site does not name its sales motion."}).status == Status.inferred


def test_unknown_status_rejected():
    with pytest.raises(ValidationError):
        Claim(**{**GOOD, "status": "verified"})  # "verified" must never exist


def test_confidence_range():
    with pytest.raises(ValidationError):
        Claim(**{**GOOD, "confidence": 1.5})


# --- Multi-span evidence (decided 2026-09-23) ------------------------------------------------
# Fixes a real bug: basecamp.com's pricing plans sit on four separate lines, so one evidence
# string forced the model to fabricate a combined quote. A list-valued claim may now carry one
# evidence quote per value entry -- but only in that exact shape, enforced here.

def test_evidence_list_matching_value_list_length_passes():
    claim = Claim(**{
        **GOOD,
        "field": "pricing.public_plans",
        "value": ["Freelancer, $25/mo", "Studio, $59/mo"],
        "evidence": ["Freelancer, $25/mo", "Studio, $59/mo"],
    })
    assert claim.value == ["Freelancer, $25/mo", "Studio, $59/mo"]
    assert claim.evidence == ["Freelancer, $25/mo", "Studio, $59/mo"]


def test_evidence_list_shorter_than_value_list_fails():
    with pytest.raises(ValidationError):
        Claim(**{
            **GOOD,
            "field": "pricing.public_plans",
            "value": ["Freelancer, $25/mo", "Studio, $59/mo", "Pro, $99/mo"],
            "evidence": ["Freelancer, $25/mo", "Studio, $59/mo"],  # one short
        })


def test_evidence_list_longer_than_value_list_fails():
    with pytest.raises(ValidationError):
        Claim(**{
            **GOOD,
            "field": "pricing.public_plans",
            "value": ["Freelancer, $25/mo"],
            "evidence": ["Freelancer, $25/mo", "Studio, $59/mo"],  # one extra
        })


def test_evidence_list_with_a_single_string_value_fails():
    # A list of quotes only makes sense paired with a list of values -- one quote per entry.
    with pytest.raises(ValidationError):
        Claim(**{**GOOD, "evidence": ["NorthLedger helps small businesses send invoices."]})


# --- Field/value-shape enforcement (decided 2026-09-24) --------------------------------------
# Reproduces a real bug: on a live basecamp.com run the model returned a list `value` for
# customers.segments -- a field that's supposed to stay a single descriptive string -- three
# separate times, with different fabricated contents each time. Nothing previously stopped a
# list value on a field the prompt never authorised as list-shaped; it was only ever caught
# because the fabricated *contents* didn't match the quote, never because the *shape* itself
# was wrong. This enforces the shape structurally, for every field, not just this one.

def test_list_value_on_a_non_multi_value_field_fails():
    with pytest.raises(ValidationError):
        Claim(**{
            **GOOD,
            "field": "customers.segments",  # not in MULTI_VALUE_FIELDS
            "value": ["Small Business", "Freelancers", "Non-Profits", "Teams"],
            "evidence": "Trusted by small businesses, freelancers, non-profits and teams.",
        })


def test_list_value_on_a_multi_value_field_still_passes():
    # pricing.public_plans was added to MULTI_VALUE_FIELDS alongside this fix (2026-09-24) --
    # both the model and the hand-labelled basecamp.com reference already treated it as list-
    # shaped, so this formalises what was already true in practice.
    claim = Claim(**{
        **GOOD,
        "field": "pricing.public_plans",
        "value": ["Freelancer, $25/mo", "Studio, $59/mo"],
        "evidence": "Freelancer, $25/mo and Studio, $59/mo are both available today.",
    })
    assert claim.value == ["Freelancer, $25/mo", "Studio, $59/mo"]


def test_single_string_value_on_a_non_multi_value_field_still_passes():
    # The new check only rejects the list shape on the wrong field -- a normal single-string
    # claim on a non-multi-value field is untouched.
    assert Claim(**{**GOOD, "field": "customers.segments", "value": "Small businesses"}).value == (
        "Small businesses"
    )


# --- Conflicting-status shape enforcement (B-06/EVD-05, decided 2026-09-27) -------------------
# Reproduces a real gap: `status="conflicting"` previously required nothing at all -- not even a
# value or evidence -- and passed validation untouched. Now it must carry the same paired-array
# shape rule 6 already uses for multi-value fields, on ANY field (even one not in
# MULTI_VALUE_FIELDS), since a conflict inherently needs two values.

def test_conflicting_claim_with_no_value_or_evidence_fails():
    with pytest.raises(ValidationError):
        Claim(claim_id="c003", field="company_identity.headquarters", status="conflicting")


def test_conflicting_claim_with_a_single_string_value_fails():
    # "value describing both in one sentence" is exactly the invented-sentence shape this fix
    # moves away from -- must be a list of the differing raw values instead.
    with pytest.raises(ValidationError):
        Claim(
            claim_id="c003", field="company_identity.headquarters", status="conflicting",
            value="Bengaluru according to one page, Mumbai according to another",
            evidence="Headquartered in Bengaluru. Visit our Mumbai office.",
        )


def test_conflicting_claim_with_only_one_value_fails():
    with pytest.raises(ValidationError):
        Claim(
            claim_id="c003", field="company_identity.headquarters", status="conflicting",
            value=["Bengaluru, India"], evidence=["Headquartered in Bengaluru, India."],
        )


def test_conflicting_claim_evidence_length_mismatch_fails():
    with pytest.raises(ValidationError):
        Claim(
            claim_id="c003", field="company_identity.headquarters", status="conflicting",
            value=["Bengaluru, India", "Mumbai"],
            evidence=["Headquartered in Bengaluru, India."],  # one short
        )


def test_conflicting_claim_list_value_allowed_even_on_a_non_multi_value_field():
    # company_identity.headquarters is NOT in MULTI_VALUE_FIELDS, but conflicting status is
    # exempted from that check (unlike extracted/inferred, which would still be rejected).
    claim = Claim(
        claim_id="c003", field="company_identity.headquarters", status="conflicting",
        value=["Bengaluru, India", "Mumbai"],
        evidence=["Headquartered in Bengaluru, India.", "Visit our Mumbai head office."],
    )
    assert claim.value == ["Bengaluru, India", "Mumbai"]
    assert claim.status == Status.conflicting


# --- B-10: "mixed forms" for one field type (bare value, `null`, and literal "not_found") ----
# must all be rejected. Two of the three sub-cases turn out to already be caught by existing
# rules; the tests below confirm all three, and document which rule catches which.

def test_claim_with_no_status_at_all_is_rejected():
    # A bare/status-missing claim: Pydantic's own required-field check on the Status enum
    # already catches this -- no new code needed, just confirming it here.
    data = {k: v for k, v in GOOD.items() if k != "status"}
    with pytest.raises(ValidationError):
        Claim(**data)


def test_extracted_claim_with_null_value_is_rejected():
    # A `null` value on an extracted/inferred claim: already caught by the pre-existing
    # "{status} claim is missing 'value'" check (`not getattr(self, name)` is true for None).
    with pytest.raises(ValidationError):
        Claim(**{**GOOD, "value": None})


def test_extracted_claim_with_literal_not_found_string_value_is_rejected():
    # The one genuine gap B-10 surfaced: nothing previously stopped an extracted/inferred claim
    # from using the literal string "not_found" (or "not found") as its value -- self-
    # contradictory (claiming a value while stating there is none), but schema-valid before
    # this fix since it's just an ordinary non-empty string to every earlier check.
    with pytest.raises(ValidationError):
        Claim(**{**GOOD, "value": "not_found"})
    with pytest.raises(ValidationError):
        Claim(**{**GOOD, "value": "Not Found"})  # case-insensitive
    with pytest.raises(ValidationError):
        Claim(**{**GOOD, "value": "not found"})  # underscore-insensitive too


def test_literal_not_found_string_rejected_inside_a_list_value_too():
    # A multi-value field with one legitimate item and one laundered-abstention item must still
    # be rejected -- the check applies per-item, not just to a single-string value.
    with pytest.raises(ValidationError):
        Claim(**{
            **GOOD,
            "field": "traction.named_customers",
            "value": ["Real Customer Inc", "not_found"],
            "evidence": "Real Customer Inc is a real quote from the page.",
        })


def test_extracted_status_on_a_non_multi_value_field_still_rejects_list_value():
    # The conflicting exemption must not leak into extracted/inferred -- those still enforce
    # MULTI_VALUE_FIELDS exactly as before (test_list_value_on_a_non_multi_value_field_fails
    # above covers the base case; this confirms the new exemption is scoped to conflicting only).
    with pytest.raises(ValidationError):
        Claim(**{
            **GOOD,
            "field": "company_identity.headquarters",
            "value": ["Bengaluru, India", "Mumbai"],
            "evidence": ["Headquartered in Bengaluru, India.", "Visit our Mumbai head office."],
        })
