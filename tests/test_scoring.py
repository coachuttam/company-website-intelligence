"""Tests for wi.eval.scoring (Final PRD Section 12, Week 3 field-level accuracy baseline)."""
from __future__ import annotations

from wi.extract.fields import FIELDS
from wi.eval.scoring import (
    FieldScore, Verdict, extraction_vs_inference, normalize, score_field, score_run, summarize,
)
from wi.schemas.claim import Claim, Coverage, Status


def _claim(field: str, status: Status, value=None, **kw) -> Claim:
    defaults = dict(
        claim_id=f"c:{field}", field=field, status=status, value=value,
        source_url="https://example.com/", page_title="Example",
        evidence=kw.pop("evidence", "Some page text."), retrieved_at="2026-09-27",
    )
    if status == Status.not_found:
        defaults = dict(claim_id=f"c:{field}", field=field, status=status,
                         coverage=Coverage(page_types_checked=["home"], pages_checked=1))
    if status == Status.inferred:
        defaults["notes"] = "inferred for a reason"
    if status == Status.conflicting:
        # B-06/EVD-05 (2026-09-27): conflicting claims now require a paired value/evidence list
        # (wi/schemas/claim.py) instead of a single descriptive string. score_field() only ever
        # branches on claim.status for the conflicting case (never inspects claim.value's
        # content), so wrapping a single passed-in value into a 2-entry list here keeps every
        # existing call site working unchanged.
        values = value if isinstance(value, list) else [value, "an alternate value"]
        defaults["value"] = values
        defaults.pop("evidence", None)
        defaults["evidence"] = [f"Evidence for {v}" for v in values]
    defaults.update(kw)
    return Claim(**defaults)


# ---------------------------------------------------------------------------
# normalize()
# ---------------------------------------------------------------------------

def test_normalize_none_stays_none():
    assert normalize(None) is None


def test_normalize_string_casefolds_strips_and_collapses_whitespace():
    assert normalize("  Basecamp   Inc.  ") == normalize("basecamp inc.")
    assert normalize("Basecamp") == "basecamp"


def test_normalize_list_is_order_independent_set():
    assert normalize(["Zapier", "Zoho Flow"]) == normalize(["Zoho Flow", "Zapier"])


def test_normalize_list_casefolds_each_item():
    assert normalize(["Zapier"]) == normalize(["ZAPIER"])


# ---------------------------------------------------------------------------
# score_field() -- one case per PRD Section 12 row, plus the conflicting extension
# ---------------------------------------------------------------------------

def test_label_not_found_system_not_found_is_correct_abstention():
    label = {"status": "not_found"}
    claim = _claim("company_identity.headquarters", Status.not_found)
    result = score_field("company_identity.headquarters", label, claim)
    assert result.verdict == Verdict.correct_abstention


def test_label_has_value_system_not_found_is_miss():
    label = {"status": "extracted", "value": "Bengaluru"}
    claim = _claim("company_identity.headquarters", Status.not_found)
    result = score_field("company_identity.headquarters", label, claim)
    assert result.verdict == Verdict.miss


def test_label_not_found_system_returns_value_is_unsupported():
    label = {"status": "not_found"}
    claim = _claim("company_identity.headquarters", Status.extracted, value="Bengaluru")
    result = score_field("company_identity.headquarters", label, claim)
    assert result.verdict == Verdict.unsupported


def test_label_not_found_system_conflicting_is_also_unsupported():
    # The site's own ground truth says nothing is there -- a conflict is still an assertion
    # the label doesn't support, however many values it names.
    label = {"status": "not_found"}
    claim = _claim("company_identity.headquarters", Status.conflicting, value="A vs B")
    result = score_field("company_identity.headquarters", label, claim)
    assert result.verdict == Verdict.unsupported


def test_matching_value_after_normalising_is_correct():
    label = {"status": "extracted", "value": "Basecamp"}
    claim = _claim("company_identity.name", Status.extracted, value="  basecamp  ")
    result = score_field("company_identity.name", label, claim)
    assert result.verdict == Verdict.correct


def test_matching_list_value_regardless_of_order_is_correct():
    label = {"status": "extracted", "value": ["Zapier", "Zoho Flow"]}
    claim = _claim("traction.partnerships", Status.extracted, value=["Zoho Flow", "Zapier"])
    result = score_field("traction.partnerships", label, claim)
    assert result.verdict == Verdict.correct


def test_differing_value_is_incorrect():
    label = {"status": "extracted", "value": "Basecamp"}
    claim = _claim("company_identity.name", Status.extracted, value="Basecamp Inc")
    result = score_field("company_identity.name", label, claim)
    assert result.verdict == Verdict.incorrect


def test_inferred_status_can_still_be_correct():
    label = {"status": "extracted", "value": "sales-led"}
    claim = _claim("pricing.sales_motion", Status.inferred, value="sales-led")
    result = score_field("pricing.sales_motion", label, claim)
    assert result.verdict == Verdict.correct


def test_conflicting_against_a_valued_label_is_its_own_verdict_not_correct_or_incorrect():
    # Even if the conflicting claim's description happens to contain the right answer, a
    # conflict isn't a confident correct assertion -- it gets its own bucket (AC-11: conflict
    # handling reported separately from extraction/inference accuracy).
    label = {"status": "extracted", "value": "Mumbai"}
    claim = _claim("company_identity.headquarters", Status.conflicting,
                    value="Mumbai on the about page, Bengaluru on the careers page")
    result = score_field("company_identity.headquarters", label, claim)
    assert result.verdict == Verdict.conflicting


def test_missing_claim_is_treated_defensively_as_not_found():
    label = {"status": "extracted", "value": "Basecamp"}
    result = score_field("company_identity.name", label, claim=None)
    assert result.verdict == Verdict.miss
    assert result.system_status == "not_found"
    assert result.system_claim_id is None


def test_shape_mismatch_between_scalar_and_list_still_compares_sensibly():
    # Defensive only -- shouldn't happen given MULTI_VALUE_FIELDS enforcement in wi.schemas.claim,
    # but a single-item list should still be recognised as matching the equivalent bare string.
    label = {"status": "extracted", "value": "Basecamp"}
    claim = _claim("products.names", Status.extracted, value=["Basecamp"])
    result = score_field("products.names", label, claim)
    assert result.verdict == Verdict.correct


# ---------------------------------------------------------------------------
# B-45: multi-value overlap credit (Verdict.correct_partial)
# ---------------------------------------------------------------------------

def test_multi_value_field_with_real_overlap_but_no_exact_match_is_correct_partial():
    # Found live on plaid.com: the model and the label both name real products, but different
    # subsets of a 15+ item list -- neither an exact match nor a total miss.
    label = {"status": "extracted", "value": ["Auth", "Identity", "Balance", "Transfer"]}
    claim = _claim("products.names", Status.extracted, value=["Auth", "Payments"])
    result = score_field("products.names", label, claim)
    assert result.verdict == Verdict.correct_partial


def test_multi_value_field_with_zero_overlap_is_still_incorrect():
    # Overlap credit must not paper over a genuinely disjoint list.
    label = {"status": "extracted", "value": ["Auth", "Identity"]}
    claim = _claim("products.names", Status.extracted, value=["Completely Different Thing"])
    result = score_field("products.names", label, claim)
    assert result.verdict == Verdict.incorrect


def test_overlap_credit_is_scoped_to_multi_value_fields_only():
    # wi.schemas.claim.Claim already refuses a list value on a field outside MULTI_VALUE_FIELDS
    # (so this shape can't reach score_field() from a real run), but score_field()'s own gate --
    # `field in MULTI_VALUE_FIELDS` -- is what actually enforces the scoping, independent of that
    # upstream guarantee. Exercise it directly: same real-overlap shape that earns correct_partial
    # on products.names must NOT do so if the field argument itself isn't a multi-value field.
    from wi.eval.scoring import _has_list_overlap
    assert _has_list_overlap(["Auth", "Identity"], ["Auth", "Payments"])  # the mechanism works
    label = {"status": "extracted", "value": "Bengaluru"}
    claim = _claim("company_identity.headquarters", Status.extracted, value="Mumbai")
    result = score_field("company_identity.headquarters", label, claim)
    assert result.verdict == Verdict.incorrect  # never even reaches the overlap check


def test_overlap_credit_does_not_apply_when_the_system_value_is_a_bare_string():
    # _has_list_overlap() requires BOTH sides to be genuinely list-shaped -- a single-string
    # system value on a multi-value field must go through the ordinary (non-overlap) path.
    label = {"status": "extracted", "value": ["Auth", "Identity"]}
    claim = _claim("products.names", Status.extracted, value="Something else entirely")
    result = score_field("products.names", label, claim)
    assert result.verdict == Verdict.incorrect


# ---------------------------------------------------------------------------
# score_run() / summarize()
# ---------------------------------------------------------------------------

def test_score_run_covers_every_field_in_fields_py():
    label_doc = {"fields": {f: {"status": "not_found"} for f in FIELDS}}
    claims = [_claim(f, Status.not_found) for f in FIELDS]
    scores = score_run(label_doc, claims)
    assert {s.field for s in scores} == set(FIELDS)
    assert len(scores) == len(FIELDS)


def test_score_run_handles_a_field_the_run_never_produced_a_claim_for():
    label_doc = {"fields": {f: {"status": "not_found"} for f in FIELDS}}
    claims = [_claim(f, Status.not_found) for f in FIELDS if f != "comparisons.named_alternatives"]
    scores = score_run(label_doc, claims)
    missing = next(s for s in scores if s.field == "comparisons.named_alternatives")
    assert missing.verdict == Verdict.correct_abstention  # label not_found, no claim => treated as not_found


def test_summarize_counts_every_verdict_and_computes_accuracy():
    scores = [
        FieldScore("a", Verdict.correct, "extracted", "x", "extracted", "x", "id1"),
        FieldScore("b", Verdict.correct_abstention, "not_found", None, "not_found", None, None),
        FieldScore("c", Verdict.incorrect, "extracted", "x", "extracted", "y", "id2"),
        FieldScore("d", Verdict.miss, "extracted", "x", "not_found", None, None),
        FieldScore("e", Verdict.unsupported, "not_found", None, "extracted", "z", "id3"),
        FieldScore("f", Verdict.conflicting, "extracted", "x", "conflicting", "x or y", "id4"),
    ]
    result = summarize(scores)
    assert result["total"] == 6
    assert result["counts"] == {
        "correct": 1, "incorrect": 1, "correct_abstention": 1,
        "miss": 1, "unsupported": 1, "conflicting": 1,
        "correct_partial": 0, "correct_semantic": 0,  # B-45: present, just unused by this set
    }
    # right calls = correct + correct_abstention = 2 of 6
    assert result["accuracy"] == 2 / 6


def test_summarize_accuracy_is_none_for_an_empty_score_list():
    assert summarize([])["accuracy"] is None


# ---------------------------------------------------------------------------
# extraction_vs_inference()
# ---------------------------------------------------------------------------

def test_extraction_vs_inference_splits_correctness_by_system_status():
    scores = [
        FieldScore("a", Verdict.correct, "extracted", "x", "extracted", "x", "id1"),
        FieldScore("b", Verdict.incorrect, "extracted", "x", "extracted", "y", "id2"),
        FieldScore("c", Verdict.correct, "extracted", "x", "inferred", "x", "id3"),
        FieldScore("d", Verdict.correct_abstention, "not_found", None, "not_found", None, None),
        FieldScore("e", Verdict.conflicting, "extracted", "x", "conflicting", "x or y", "id4"),
    ]
    result = extraction_vs_inference(scores)
    assert result["extraction_accuracy"] == 0.5  # 1 correct of 2 extracted
    assert result["inference_accuracy"] == 1.0   # 1 correct of 1 inferred
    assert result["conflicting_count"] == 1


def test_extraction_vs_inference_is_none_when_nothing_of_that_status_was_scored():
    scores = [FieldScore("a", Verdict.correct_abstention, "not_found", None, "not_found", None, None)]
    result = extraction_vs_inference(scores)
    assert result["extraction_accuracy"] is None
    assert result["inference_accuracy"] is None
    assert result["conflicting_count"] == 0


def test_extraction_vs_inference_counts_correct_partial_and_correct_semantic_as_correct():
    # B-45: both new verdicts must count toward AC-11's per-status accuracy exactly like `correct`.
    scores = [
        FieldScore("products.names", Verdict.correct_partial, "extracted", ["Auth"],
                   "extracted", ["Auth", "Identity"], "id1"),
        FieldScore("company_identity.description", Verdict.correct_semantic, "extracted", "x",
                   "extracted", "a different-worded x", "id2"),
        FieldScore("company_identity.name", Verdict.incorrect, "extracted", "x",
                   "extracted", "y", "id3"),
    ]
    result = extraction_vs_inference(scores)
    assert result["extraction_accuracy"] == 2 / 3


# ---------------------------------------------------------------------------
# B-45: LLM-as-judge semantic equivalence (Verdict.correct_semantic)
# ---------------------------------------------------------------------------

class _FakeJudge:
    """Test double for wi.extract.llm.JudgeCompleter -- never touches the network, matches the
    existing ChatCompleter-fake pattern used for pipeline tests elsewhere in this project."""

    def __init__(self, verdicts_by_pair: dict):
        self._verdicts = verdicts_by_pair
        self.calls = []

    def judge(self, label_text, system_text, field, model) -> bool:
        self.calls.append((label_text, system_text, field, model))
        return self._verdicts[(label_text, system_text)]


def test_free_text_judged_fields_widened_by_b46_and_b54():
    from wi.eval.scoring import FREE_TEXT_JUDGED_FIELDS
    assert FREE_TEXT_JUDGED_FIELDS == {
        "company_identity.description", "products.delivery_model",
        "customers.segments", "pricing.sales_motion", "company_identity.headquarters",
    }


def test_semantic_judge_upgrades_an_incorrect_free_text_verdict_when_it_agrees():
    from wi.eval.scoring import apply_semantic_judging
    scores = [FieldScore("company_identity.description", Verdict.incorrect, "extracted",
                          "Helps teams manage social media.", "extracted",
                          "A tool for managing your team's social media presence.", "id1")]
    judge = _FakeJudge({("Helps teams manage social media.",
                         "A tool for managing your team's social media presence."): True})
    result = apply_semantic_judging(scores, judge, model="gpt-4o-mini")
    assert result[0].verdict == Verdict.correct_semantic
    assert judge.calls == [("Helps teams manage social media.",
                            "A tool for managing your team's social media presence.",
                            "company_identity.description", "gpt-4o-mini")]


def test_semantic_judge_leaves_a_genuinely_wrong_answer_incorrect():
    from wi.eval.scoring import apply_semantic_judging
    scores = [FieldScore("company_identity.description", Verdict.incorrect, "extracted",
                          "Helps teams manage social media.", "extracted",
                          "A payments processing platform.", "id1")]
    judge = _FakeJudge({("Helps teams manage social media.", "A payments processing platform."): False})
    result = apply_semantic_judging(scores, judge, model="gpt-4o-mini")
    assert result[0].verdict == Verdict.incorrect


def test_semantic_judge_is_scoped_to_free_text_fields_only():
    from wi.eval.scoring import apply_semantic_judging
    # Same "incorrect" shape, but a field outside FREE_TEXT_JUDGED_FIELDS -- must never even call
    # the judge, let alone upgrade the verdict.
    scores = [FieldScore("company_identity.name", Verdict.incorrect, "extracted", "Basecamp",
                          "extracted", "Basecamp Inc", "id1")]
    judge = _FakeJudge({})  # no verdicts registered -- a call here would KeyError
    result = apply_semantic_judging(scores, judge, model="gpt-4o-mini")
    assert result[0].verdict == Verdict.incorrect
    assert judge.calls == []


def test_semantic_judge_reaches_customers_segments_after_b46_widening():
    # B-46: customers.segments was flat 0% on the live run with neither B-45 mechanism able to
    # touch it (not multi-value, not previously in FREE_TEXT_JUDGED_FIELDS) -- confirms it's now
    # reachable the same way company_identity.description already was.
    from wi.eval.scoring import apply_semantic_judging
    scores = [FieldScore("customers.segments", Verdict.incorrect, "extracted",
                          "Creators, small businesses, agencies, and nonprofits", "extracted",
                          "Creators, brands, and agencies", "id1")]
    judge = _FakeJudge({("Creators, small businesses, agencies, and nonprofits",
                         "Creators, brands, and agencies"): True})
    result = apply_semantic_judging(scores, judge, model="gpt-4o-mini")
    assert result[0].verdict == Verdict.correct_semantic


def test_semantic_judge_reaches_pricing_sales_motion_after_b46_widening():
    from wi.eval.scoring import apply_semantic_judging
    scores = [FieldScore("pricing.sales_motion", Verdict.incorrect, "extracted",
                          "Self-serve online signup; no enterprise tier", "inferred",
                          "Self-serve signup", "id1")]
    judge = _FakeJudge({("Self-serve online signup; no enterprise tier",
                         "Self-serve signup"): True})
    result = apply_semantic_judging(scores, judge, model="gpt-4o-mini")
    assert result[0].verdict == Verdict.correct_semantic


def test_semantic_judge_reaches_headquarters_after_b54_widening():
    # B-54: the real razorpay.com case B-53 unlocked -- a genuine, well-evidenced address claim
    # that's now a coarser city/state/country summary rather than the label's full street
    # address. Same "elaboration, not a different fact" shape as the other B-45/B-46 fields,
    # reversing B-46's earlier exclusion of this field (see module docstring).
    from wi.eval.scoring import apply_semantic_judging
    scores = [FieldScore(
        "company_identity.headquarters", Verdict.incorrect, "extracted",
        "1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, Karnataka - 560030",
        "extracted", "Bengaluru, Karnataka, India", "id1",
    )]
    judge = _FakeJudge({
        ("1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, Karnataka - 560030",
         "Bengaluru, Karnataka, India"): True
    })
    result = apply_semantic_judging(scores, judge, model="gpt-4o-mini")
    assert result[0].verdict == Verdict.correct_semantic


def test_semantic_judge_still_rejects_a_genuinely_different_headquarters():
    # A real, non-elaboration mismatch (a different city entirely) must stay incorrect even
    # though the field is now judge-eligible -- the judge, not a blanket exemption, is what
    # decides, same as every other field in FREE_TEXT_JUDGED_FIELDS.
    from wi.eval.scoring import apply_semantic_judging
    scores = [FieldScore(
        "company_identity.headquarters", Verdict.incorrect, "extracted",
        "600 Route 25A, East Setauket, New York 11733",
        "extracted", "520 Madison Avenue, New York, New York 10022", "id1",
    )]
    judge = _FakeJudge({
        ("600 Route 25A, East Setauket, New York 11733",
         "520 Madison Avenue, New York, New York 10022"): False
    })
    result = apply_semantic_judging(scores, judge, model="gpt-4o-mini")
    assert result[0].verdict == Verdict.incorrect


def test_semantic_judge_never_touches_non_incorrect_verdicts():
    from wi.eval.scoring import apply_semantic_judging
    scores = [
        FieldScore("company_identity.description", Verdict.correct, "extracted", "x",
                   "extracted", "x", "id1"),
        FieldScore("company_identity.description", Verdict.miss, "extracted", "x",
                   "not_found", None, None),
        FieldScore("company_identity.description", Verdict.correct_abstention, "not_found",
                   None, "not_found", None, None),
    ]
    judge = _FakeJudge({})
    result = apply_semantic_judging(scores, judge, model="gpt-4o-mini")
    assert [s.verdict for s in result] == [Verdict.correct, Verdict.miss, Verdict.correct_abstention]
    assert judge.calls == []


# ---------------------------------------------------------------------------
# B-58: pricing.public_plans is scored by plan name plus price
# ---------------------------------------------------------------------------

PLANS = "pricing.public_plans"


def _plans(label_items, system_items):
    label = {"status": "extracted", "value": label_items}
    claim = _claim(PLANS, Status.extracted, value=system_items)
    return score_field(PLANS, label, claim).verdict


def test_b58_same_plans_with_different_separator_and_spacing_are_correct():
    assert _plans(
        ["Free — Always free", "Standard — $10/seat/mo", "Teams — $16/seat/mo"],
        ["Free", "Standard, $10 /seat/mo", "Teams, $16/seat/mo"],
    ) == Verdict.correct


def test_b58_thousands_comma_and_trailing_gst_do_not_matter():
    assert _plans(["Business — ₹1,499/month + GST"], ["Business, ₹1,499 / month"]) == Verdict.correct


def test_b58_a_wrong_amount_is_not_a_match():
    assert _plans(["Standard — $10/seat/mo"], ["Standard, $12/seat/mo"]) == Verdict.incorrect


def test_b58_a_different_currency_is_not_a_match():
    assert _plans(["Standard — $499/mo"], ["Standard, ₹499/month"]) == Verdict.incorrect


def test_b58_a_names_only_label_does_not_match_a_priced_item():
    assert _plans(["Standard", "Business"], ["Standard, ₹499/month", "Business, ₹1,499/month"]) == Verdict.incorrect


def test_b58_some_plans_in_common_is_correct_partial():
    assert _plans(
        ["Free", "Standard — $10/seat/mo", "Teams — $16/seat/mo"],
        ["Free", "Standard, $10/seat/mo"],
    ) == Verdict.correct_partial


def test_b58_a_trial_length_is_not_mistaken_for_the_price():
    assert _plans(["Plus — $379/mo"], ["Plus, 379USD/mo after 14 days"]) == Verdict.correct


def test_b58_a_trailing_plan_word_is_ignored():
    assert _plans(["Free"], ["Free plan"]) == Verdict.correct


def test_b58_other_list_fields_keep_exact_matching():
    label = {"status": "extracted", "value": ["SOC 2 Type II"]}
    claim = _claim("traction.certifications", Status.extracted, value=["SOC 2 Type II"])
    assert score_field("traction.certifications", label, claim).verdict == Verdict.correct


# ---- B-63: a spelled-out number equals its digits ---------------------------------------------
def test_b63_spelled_out_number_matches_digits():
    from wi.eval.scoring import normalize
    assert normalize("Seven-day trial") == normalize("7-day trial")
    assert normalize("Fourteen day free trial") == normalize("14 day free trial")


def test_b63_number_words_only_inside_whole_words():
    from wi.eval.scoring import normalize
    assert normalize("Stone") == "stone" and normalize("Someone") == "someone"
    assert normalize("Seven-day trial") != normalize("14-day trial")
