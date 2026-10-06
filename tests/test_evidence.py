"""Evidence check tests. Maps to PRD requirement EVD-02 and behaviours B-04, B-05, B-06."""
from wi.schemas.claim import Claim
from wi.validate.evidence import (
    check_claim,
    check_claim_items,
    check_conflicting_claim,
    quote_in_page,
    value_supported_by_quote,
)

PAGE = (
    "# Pricing\n"
    "Starter ₹499 per month. Growth ₹1,499 per month.\n"
    "Start your 14-day free trial. No credit card required.\n"
    "Trusted by thousands of small businesses."
)


def _claim(**kw):
    base = dict(
        claim_id="c1", field="pricing.public_plans", value="Starter INR 499/month",
        status="extracted", source_url="https://x.example/pricing",
        evidence="Starter ₹499 per month.", retrieved_at="2026-09-21",
    )
    base.update(kw)
    return Claim(**base)


def test_exact_quote_found():
    assert quote_in_page("Starter ₹499 per month.", PAGE)


def test_quote_found_despite_whitespace_and_case():
    assert quote_in_page("starter ₹499   PER month.", PAGE)


def test_fake_quote_rejected():  # B-04
    assert not quote_in_page("NorthLedger serves over 10,000 customers", PAGE)


def test_valid_claim_passes():
    ok, _ = check_claim(_claim(), PAGE)
    assert ok


def test_quote_exists_but_does_not_support_value():  # B-05
    claim = _claim(value="Starter INR 999/month")   # 999 is not in the quote
    ok, reason = check_claim(claim, PAGE)
    assert not ok and "support" in reason


def test_comma_numbers_match():
    assert value_supported_by_quote("Growth INR 1,499/month", "Growth ₹1,499 per month.")


def test_fabricated_quote_fails_claim_check():
    claim = _claim(evidence="NorthLedger serves over 10,000 customers", value="10,000 customers")
    ok, reason = check_claim(claim, PAGE)
    assert not ok and "not found" in reason


# --- Non-numeric hallucination coverage -----------------------------------------------------
# Reproduces a real bug found on the live basecamp.com run: the model attached a fabricated,
# specific industries list to a genuine page quote that names no specific industries at all.
# Because the value had no digits in it, the old numbers-only check passed it straight through.

def test_fabricated_list_attached_to_vague_but_real_quote_fails():
    value = ("Engineering, marketing, manufacturing, design, software development, "
             "construction, client services, PR communications, publishing, education, "
             "religious institutions, governments, NGOs")
    quote = ("Basecamp is used in over 100 countries, on every populated continent, "
             "across every industry imaginable.")
    assert not value_supported_by_quote(value, quote)


def test_fabricated_list_fails_claim_check_end_to_end():
    quote = ("Basecamp is used in over 100 countries, on every populated continent, "
             "across every industry imaginable.")
    claim = _claim(
        field="customers.industries",
        value="Engineering, marketing, manufacturing, construction, publishing",
        evidence=quote,
    )
    page = "Some intro text. " + quote + " Some outro text."
    ok, reason = check_claim(claim, page)
    assert not ok and "support" in reason


def test_legitimate_named_list_passes_when_quote_actually_names_them():
    value = "Yatra, Mahindra Logistics, TVS Motor"
    quote = "Trusted by leading brands including Yatra, Mahindra Logistics and TVS Motor."
    assert value_supported_by_quote(value, quote)


def test_partial_overlap_below_threshold_fails():
    # Only one of three claimed items is actually backed by the quote.
    value = "Yatra, Completely Invented Co, Another Fake Ltd"
    quote = "Trusted by leading brands including Yatra and many more."
    assert not value_supported_by_quote(value, quote)


def test_comma_inside_number_is_not_split_into_bogus_items():
    # "1,499" must not be split into separate "1" / "499" items by the comma-splitting logic.
    assert value_supported_by_quote("Growth INR 1,499/month", "Growth ₹1,499 per month.")


def test_bare_value_with_no_significant_words_is_not_penalised():
    # A short, mostly-stopword/number value shouldn't be rejected for lacking "significant" words.
    assert value_supported_by_quote("Yes", "Yes, a 14-day free trial is available.")


def test_semicolon_separated_multi_address_value_is_not_shredded_by_comma_splitting():
    # B-44, found live on innovaccer.com: a multi-location headquarters value joins four whole
    # addresses with semicolons, each address having its OWN internal commas. Splitting on every
    # comma regardless of which address it belongs to produced meaningless cross-address
    # fragments like "CA 94105; Tower 3" that matched no real evidence line. Splitting on the
    # semicolon first (never re-splitting each resulting address by comma) fixes this.
    value = (
        "Suite 2900, San Francisco, CA 94105; "
        "Tower 3, Candor Techspace Sector 62, 201309, India"
    )
    quote = (
        "Suite 2900, San Francisco, CA 94105\n"
        "Tower 3, Candor Techspace Sector 62, 201309, India"
    )
    assert value_supported_by_quote(value, quote)


def test_a_semicolon_separated_item_that_is_genuinely_missing_still_fails():
    # The semicolon fix (above) must not become a way to smuggle a fabricated address past the
    # check just because it's joined to a real one with a semicolon.
    value = "Suite 2900, San Francisco, CA 94105; 1 Fake Plaza, Nowhere, ZZ 00000"
    quote = "Suite 2900, San Francisco, CA 94105"
    assert not value_supported_by_quote(value, quote)


def test_renamed_place_in_value_matches_the_older_name_still_used_in_the_quote():
    # B-44, found live on razorpay.com: the model's value said "Bengaluru" (the city's current
    # official name) while the page's own address, quoted verbatim, still says "Bangalore" (the
    # pre-2014 name) -- a real, common Indian-city renaming, not a hallucination. Both names must
    # be treated as the same place. (The live value also appended ", India" -- that fails for an
    # unrelated, still-open reason: this exact address never states a country at all, so any
    # bare country name is its own independent, unsupported comma-split item. That's a separate,
    # not-yet-decided problem -- see PROGRESS.md -- so this test isolates just the alias fix.)
    value = "Bengaluru, Karnataka"
    quote = "1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, Karnataka - 560030"
    assert value_supported_by_quote(value, quote)


def test_renamed_place_in_quote_matches_the_modern_name_used_in_the_value():
    # The reverse direction of the above: the VALUE uses the older colonial-era name and the
    # QUOTE states the modern one. Canonicalisation must work both ways, not just the one
    # direction seen live.
    value = "Bombay, Maharashtra"
    quote = "Our head office is located in Mumbai, Maharashtra."
    assert value_supported_by_quote(value, quote)


def test_a_genuinely_wrong_city_is_still_rejected_not_papered_over_by_the_alias_list():
    # The alias list must stay narrow: a real, different city (not one of the known renamings)
    # should still fail exactly as before.
    value = "Hyderabad, Telangana, India"
    quote = "1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, Karnataka - 560030"
    assert not value_supported_by_quote(value, quote)


# --- List-valued claims (Claim.value can now be a list, decided 2026-09-22) -----------------
# A list value is checked item by item directly -- no comma-splitting guesswork needed, since
# the model (or the hand-label file) already drew the item boundaries for us.

def test_list_value_with_every_item_backed_by_the_quote_passes():
    value = ["Yatra", "Mahindra Logistics", "TVS Motor"]
    quote = "Trusted by leading brands including Yatra, Mahindra Logistics and TVS Motor."
    assert value_supported_by_quote(value, quote)


def test_list_value_with_one_fabricated_item_fails():
    value = ["Yatra", "Completely Invented Co"]
    quote = "Trusted by leading brands including Yatra and many more."
    assert not value_supported_by_quote(value, quote)


def test_list_value_reproduces_the_industries_bug_as_a_real_list():
    # Same real basecamp.com bug as test_fabricated_list_attached_to_vague_but_real_quote_fails,
    # but as an actual list (what the model is now asked to return) instead of a comma string.
    value = ["Engineering", "marketing", "manufacturing", "construction", "publishing"]
    quote = ("Basecamp is used in over 100 countries, on every populated continent, "
             "across every industry imaginable.")
    assert not value_supported_by_quote(value, quote)


def test_claim_accepts_a_list_value_and_keeps_it_as_a_list():
    claim = _claim(
        field="traction.named_customers",
        value=["Yatra", "Mahindra Logistics"],
        evidence="Trusted by Yatra, Mahindra Logistics and more.",
    )
    assert claim.value == ["Yatra", "Mahindra Logistics"]
    ok, _ = check_claim(claim, "Trusted by Yatra, Mahindra Logistics and more.")
    assert ok


# --- Multi-span evidence (decided 2026-09-23) ------------------------------------------------
# Reproduces the real basecamp.com pricing bug: the plans sit on four separate lines, so one
# evidence string forced the model to fabricate a combined quote that never appears on the
# page, and got correctly rejected -- downgrading a real claim to not_found. A list-valued
# claim can now carry one evidence quote per value entry, checked pairwise.

PRICING_PAGE = (
    "# Pricing\n"
    "Freelancer, $25/mo\n"
    "Studio, $59/mo\n"
    "Pro, $99/mo\n"
    "Unlimited, $299/mo\n"
)


def test_multiple_real_evidence_spans_each_supporting_its_own_value_passes():
    claim = _claim(
        field="pricing.public_plans",
        value=["Freelancer, $25/mo", "Studio, $59/mo", "Pro, $99/mo", "Unlimited, $299/mo"],
        evidence=["Freelancer, $25/mo", "Studio, $59/mo", "Pro, $99/mo", "Unlimited, $299/mo"],
    )
    ok, reason = check_claim(claim, PRICING_PAGE)
    assert ok, reason


def test_old_fabricated_combined_quote_still_fails_exactly_as_before():
    # The bug itself: cramming all four plans into ONE evidence string. This quote never
    # appears verbatim on the page, so it must still be rejected -- the fix does not relax
    # the single-evidence path at all.
    claim = _claim(
        field="pricing.public_plans",
        value=["Freelancer, $25/mo", "Studio, $59/mo", "Pro, $99/mo", "Unlimited, $299/mo"],
        evidence=("Freelancer costs $25/mo, Studio costs $59/mo, Pro costs $99/mo, "
                  "and Unlimited costs $299/mo."),
    )
    ok, reason = check_claim(claim, PRICING_PAGE)
    assert not ok and "not found" in reason


def test_one_fabricated_span_among_real_ones_still_fails():
    # Partial evidence: three spans are real, one ("Enterprise, $999/mo") was never on the
    # page at all. A fabricated span must not be able to hide behind the real ones.
    claim = _claim(
        field="pricing.public_plans",
        value=["Freelancer, $25/mo", "Studio, $59/mo", "Enterprise, $999/mo"],
        evidence=["Freelancer, $25/mo", "Studio, $59/mo", "Enterprise, $999/mo"],
    )
    ok, reason = check_claim(claim, PRICING_PAGE)
    assert not ok and "not found" in reason and "999" in reason


def test_one_span_present_but_not_supporting_its_value_still_fails():
    # Partial evidence, different failure mode: the quote for "Studio" is real page text, but
    # it's been paired with the wrong price -- the span exists, it just doesn't back this value.
    claim = _claim(
        field="pricing.public_plans",
        value=["Freelancer, $25/mo", "Studio, $999/mo"],  # wrong price for Studio
        evidence=["Freelancer, $25/mo", "Studio, $59/mo"],  # real quote, but for $59 not $999
    )
    ok, reason = check_claim(claim, PRICING_PAGE)
    assert not ok and "support" in reason


# --- Per-item verdicts for partial credit, B-40 (added 2026-09-27) --------------------------
# check_claim() itself stays all-or-nothing (tests above confirm that's unchanged). These test
# check_claim_items(), the new per-item counterpart wi/extract/pipeline.py uses to keep only the
# items that independently verify -- see that module's and evidence.py's docstrings for the real
# temenos.com traction.partnerships bug this exists to fix.

def test_check_claim_items_reports_one_verdict_per_value_with_the_real_quote_kept():
    claim = _claim(
        field="pricing.public_plans",
        value=["Freelancer, $25/mo", "Studio, $59/mo", "Enterprise, $999/mo"],
        evidence=["Freelancer, $25/mo", "Studio, $59/mo", "Enterprise, $999/mo"],
    )
    results = check_claim_items(claim, PRICING_PAGE)
    assert [ok for ok, _, _ in results] == [True, True, False]
    assert results[0][2] == "Freelancer, $25/mo"
    assert results[1][2] == "Studio, $59/mo"
    assert results[2][2] is None
    assert "999" in results[2][1]


def test_check_claim_items_flags_a_real_quote_that_does_not_support_its_value():
    claim = _claim(
        field="pricing.public_plans",
        value=["Freelancer, $25/mo", "Studio, $999/mo"],  # wrong price for Studio
        evidence=["Freelancer, $25/mo", "Studio, $59/mo"],  # real quote, but for $59 not $999
    )
    results = check_claim_items(claim, PRICING_PAGE)
    assert [ok for ok, _, _ in results] == [True, False]
    assert "support" in results[1][1]


def test_check_claim_items_handles_the_multiline_evidence_string_shape_too():
    claim = _claim(
        field="pricing.public_plans",
        value=["Freelancer, $25/mo", "Studio, $59/mo", "Enterprise, $999/mo"],
        evidence="Freelancer, $25/mo\nStudio, $59/mo\nEnterprise, $999/mo",
    )
    results = check_claim_items(claim, PRICING_PAGE)
    assert [ok for ok, _, _ in results] == [True, True, False]
    assert results[0][2] == "Freelancer, $25/mo"


def test_check_claim_items_returns_none_for_a_single_string_value():
    # Nothing to partially filter -- a single-string claim's value/evidence pair is one atomic
    # unit, exactly like check_claim()'s own plain path.
    assert check_claim_items(_claim(), PRICING_PAGE) is None


def test_check_claim_items_returns_none_for_a_single_line_evidence_string_on_a_list_value():
    # The one shape this deliberately doesn't cover -- see the module docstring. No per-item
    # boundary exists inside one undifferentiated quote to split credit across.
    claim = _claim(
        field="pricing.public_plans",
        value=["Freelancer, $25/mo", "Studio, $59/mo"],
        evidence="Freelancer, $25/mo and Studio, $59/mo",
    )
    assert check_claim_items(claim, PRICING_PAGE) is None


# --- Multi-LINE evidence string paired with a list value (added 2026-09-27) -----------------
# The real basecamp.com pricing bug, but as it actually happened on two separate live runs: the
# model gave "value" as the correct 5-item list but ignored rule 6 (wi/extract/prompt.py) and
# joined "evidence" into ONE newline-separated string instead of a matching list -- so the
# pairwise check above (which only triggers when evidence is itself a list) never even runs.
# See wi/validate/evidence.py's module docstring for the full diagnosis.

PRICING_PAGE_WITH_FILLER = (
    "# Pricing\n"
    "Free\n"
    "One free project for personal use.\n"
    "Try it now\n"
    "Freelancer, $25/mo\n"
    "For solo freelancers\n"
    "Studio, $59/mo\n"
    "For small studios\n"
    "Pro, $99/mo\n"
    "For growing teams\n"
    "Unlimited, $299/mo\n"
    "For everyone\n"
)


def test_multiline_evidence_string_for_a_list_value_passes_when_every_line_is_real():
    # This is the exact shape observed live: value is a proper list, but evidence is a single
    # "\n"-joined string, not a matching list. Before the fix, quote_in_page() on the whole
    # joined string failed (a ~70% partial-ratio against the real page -- the filler lines like
    # "Try it now" between plans break contiguity) even though every individual plan/price is
    # real, verbatim page text.
    claim = _claim(
        field="pricing.public_plans",
        value=["Free", "Freelancer, $25/mo", "Studio, $59/mo", "Pro, $99/mo", "Unlimited, $299/mo"],
        evidence=("Free\nOne free project for personal use.\nFreelancer, $25/mo\n"
                  "Studio, $59/mo\nPro, $99/mo\nUnlimited, $299/mo"),
    )
    ok, reason = check_claim(claim, PRICING_PAGE_WITH_FILLER)
    assert ok, reason


def test_multiline_evidence_string_with_one_fabricated_line_still_fails():
    # Same shape, but one line ("Enterprise, $999/mo") was never on the page. A fabricated line
    # must not be able to pass just because it's bundled inside an otherwise-real block.
    claim = _claim(
        field="pricing.public_plans",
        value=["Free", "Freelancer, $25/mo", "Enterprise, $999/mo"],
        evidence="Free\nFreelancer, $25/mo\nEnterprise, $999/mo",
    )
    ok, reason = check_claim(claim, PRICING_PAGE_WITH_FILLER)
    assert not ok and "999" in reason


def test_multiline_evidence_string_with_a_line_that_does_not_support_its_value_still_fails():
    # Every line is real page text, but "Studio, $59/mo" has been paired with the wrong value
    # ("Studio, $999/mo") -- the fragment is real, it just doesn't back this claimed value.
    claim = _claim(
        field="pricing.public_plans",
        value=["Free", "Studio, $999/mo"],
        evidence="Free\nStudio, $59/mo",
    )
    ok, reason = check_claim(claim, PRICING_PAGE_WITH_FILLER)
    assert not ok and "999" in reason


def test_single_line_evidence_string_for_a_list_value_is_unaffected_by_the_multiline_fix():
    # Only one line -- must still go through the plain single-quote path exactly as before (see
    # test_old_fabricated_combined_quote_still_fails_exactly_as_before above).
    claim = _claim(
        field="pricing.public_plans",
        value=["Freelancer, $25/mo"],
        evidence="Freelancer, $25/mo",
    )
    ok, reason = check_claim(claim, PRICING_PAGE_WITH_FILLER)
    assert ok, reason


# --- Multi-LINE evidence string for a single-STRING value, B-42 (added 2026-09-27) ----------
# The same mechanism above, generalised to a plain-string value: customers.segments' facts often
# come from genuinely separate parts of a page, and a single-string field previously had no
# legal way to cite more than one real quote at all -- see the module docstring's B-42 section.

SEGMENTS_PAGE = (
    "# About\n"
    "We work with fast-growing startups every day, helping them ship faster.\n"
    "Later in the year we expanded our security certifications.\n"
    "Enterprise IT teams also rely on our platform for compliance and governance.\n"
)


def test_multiline_evidence_string_for_a_single_string_value_passes_when_every_line_is_real():
    claim = _claim(
        field="customers.segments",
        value="Startups, enterprise IT teams",
        evidence=("We work with fast-growing startups every day, helping them ship faster.\n"
                  "Enterprise IT teams also rely on our platform for compliance and governance."),
    )
    ok, reason = check_claim(claim, SEGMENTS_PAGE)
    assert ok, reason


def test_multiline_evidence_string_for_a_single_string_value_with_one_fabricated_line_still_fails():
    # "Startups" is real; "aerospace regulators" was never on this page at all.
    claim = _claim(
        field="customers.segments",
        value="Startups, aerospace regulators",
        evidence=("We work with fast-growing startups every day, helping them ship faster.\n"
                  "Trusted by aerospace regulators worldwide."),
    )
    ok, reason = check_claim(claim, SEGMENTS_PAGE)
    assert not ok and "aerospace regulators" in reason


def test_a_composed_paraphrase_for_a_single_string_value_still_fails():
    # The real sarvam.ai bug this whole fix was root-caused from: the model composed its own
    # introductory sentence instead of quoting the real one, even though every underlying fact
    # is individually true. A single fabricated line, with no newline to split on, must not slip
    # through just because multi-fragment evidence is now legal elsewhere.
    claim = _claim(
        field="customers.segments",
        value="Startups, enterprise IT teams",
        evidence="We serve both startups and enterprise IT teams.",
    )
    ok, reason = check_claim(claim, SEGMENTS_PAGE)
    assert not ok


def test_single_line_evidence_string_for_a_single_string_value_is_unaffected_by_b42():
    # Only one line -- still goes through the plain single-quote path exactly as before.
    claim = _claim(
        field="customers.segments",
        value="Startups",
        evidence="We work with fast-growing startups every day, helping them ship faster.",
    )
    ok, reason = check_claim(claim, SEGMENTS_PAGE)
    assert ok, reason


# --- Conflicting-claim verification (B-06/EVD-05, decided 2026-09-27) -------------------------
# Reproduces a real gap: `conflicting` claims previously reached check_claim() only to be
# short-circuited to True with no check at all (check_claim()'s own docstring says why -- a
# conflict's two values legitimately come from two different pages, unlike every other status
# here which is checked against one fixed page_text). check_conflicting_claim() closes that gap
# by checking each evidence[i] against the WHOLE crawled corpus instead of one page.

HQ_PAGE_A = "# About us\nHeadquartered in Bengaluru, India, since 2015."
HQ_PAGE_B = "# Contact\nVisit our Mumbai head office by appointment."


def _conflicting_claim(**kw):
    base = dict(
        claim_id="c9", field="company_identity.headquarters", status="conflicting",
        value=["Bengaluru, India", "Mumbai"],
        evidence=["Headquartered in Bengaluru, India, since 2015.",
                  "Visit our Mumbai head office by appointment."],
    )
    base.update(kw)
    return Claim(**base)


def test_conflicting_claim_with_real_quotes_on_different_pages_passes():
    claim = _conflicting_claim()
    ok, reason = check_conflicting_claim(claim, [HQ_PAGE_A, HQ_PAGE_B])
    assert ok, reason


def test_conflicting_claim_fails_against_a_single_page_missing_the_second_quote():
    # The whole reason this checks the full corpus rather than one page: a real conflicting
    # claim's two quotes are never both on the same page.
    claim = _conflicting_claim()
    ok, reason = check_conflicting_claim(claim, [HQ_PAGE_A])  # HQ_PAGE_B never given
    assert not ok and "not found" in reason


def test_conflicting_claim_with_a_fabricated_quote_fails():  # the B-06 anti-hallucination floor
    claim = _conflicting_claim(evidence=[
        "Headquartered in Bengaluru, India, since 2015.",
        "This sentence never appears on either page.",
    ])
    ok, reason = check_conflicting_claim(claim, [HQ_PAGE_A, HQ_PAGE_B])
    assert not ok and "not found" in reason


def test_conflicting_claim_with_a_real_quote_that_does_not_support_its_value_fails():
    # The quote is real (it's on HQ_PAGE_B), but it's been paired with the wrong value.
    claim = _conflicting_claim(value=["Bengaluru, India", "Delhi"])  # page B never says Delhi
    ok, reason = check_conflicting_claim(claim, [HQ_PAGE_A, HQ_PAGE_B])
    assert not ok and "support" in reason


# --- B-03: "Contact sales" evidence must not support an inferred subscription revenue model ---
# Real, live-observed failure mode (darwinbox.com, bajajauto.com, thoughtbot.com dev-set runs,
# 2026-09-27): the general inferred-claim exemption (only quote_in_page runs, not
# value_supported_by_quote -- see check_claim's docstring) lets a real "Contact sales" quote
# pass through paired with a fabricated "subscription" conclusion, since "contact sales" is real
# page text and inference is never checked for word support. This narrow, field-scoped guard
# closes exactly that gap without touching any other inferred field.

CONTACT_SALES_PAGE = (
    "# Pricing\nOur enterprise plans are tailored to your needs. Contact sales to get a quote."
)


def test_inferred_subscription_revenue_model_from_contact_sales_quote_is_rejected():
    claim = Claim(
        claim_id="c10", field="pricing.revenue_model", status="inferred",
        value="subscription", source_url="https://x.example/pricing",
        evidence="Contact sales to get a quote.", retrieved_at="2026-09-27",
        notes="Inferred from the pricing page's sales-contact call to action.",
    )
    ok, reason = check_claim(claim, CONTACT_SALES_PAGE)
    assert not ok
    assert "subscription" in reason and "contact sales" in reason.lower()


def test_inferred_recurring_revenue_model_from_contact_sales_quote_is_also_rejected():
    # "recurring" is the other word this guard watches for, not just the literal "subscription".
    claim = Claim(
        claim_id="c11", field="pricing.revenue_model", status="inferred",
        value="Recurring subscription billing", source_url="https://x.example/pricing",
        evidence="Contact sales to get a quote.", retrieved_at="2026-09-27",
        notes="Inferred from the pricing page's sales-contact call to action.",
    )
    ok, reason = check_claim(claim, CONTACT_SALES_PAGE)
    assert not ok


def test_contact_sales_inference_of_sales_led_motion_is_unaffected():
    # B-02's own legitimate inference (pricing.sales_motion, not revenue_model) from the exact
    # same kind of quote must keep working -- this guard is scoped to revenue_model only.
    claim = Claim(
        claim_id="c12", field="pricing.sales_motion", status="inferred",
        value="Sales-led (contact sales, no self-serve checkout)",
        source_url="https://x.example/pricing", evidence="Contact sales to get a quote.",
        retrieved_at="2026-09-27", notes="No public pricing or self-serve checkout is shown.",
    )
    ok, reason = check_claim(claim, CONTACT_SALES_PAGE)
    assert ok, reason


def test_inferred_non_subscription_revenue_model_from_contact_sales_quote_still_passes():
    # The guard only blocks a SUBSCRIPTION/RECURRING conclusion from this evidence shape -- an
    # inference to something else entirely (e.g. usage-based) is not this bug and must not be
    # collaterally blocked.
    claim = Claim(
        claim_id="c13", field="pricing.revenue_model", status="inferred",
        value="Custom, sales-negotiated enterprise pricing",
        source_url="https://x.example/pricing", evidence="Contact sales to get a quote.",
        retrieved_at="2026-09-27", notes="No plan pricing is shown; sales-negotiated only.",
    )
    ok, reason = check_claim(claim, CONTACT_SALES_PAGE)
    assert ok, reason


# --- Corpus-wide quote fallback, the "CloseKnit Health" fix (B-36, decided 2026-09-27) -------
# Reproduces the real thoughtbot.com dev-set bug: the model cited the WRONG page among several
# correctly crawled ones for a real, quotable fact -- see wi/validate/evidence.py's module
# docstring for the full live diagnosis (two direct fetches of the real index and subpage).

INDEX_PAGE = "# Case studies\nCloseKnit -- a healthcare scheduling platform.\nOther Client Inc."
SUBPAGE = ("# CloseKnit Health\nClient: CloseKnit Health\n"
           '"Working with the team was great," says a director at CloseKnit Health.')


def test_quote_missing_from_cited_page_but_found_elsewhere_in_corpus_passes_with_fallback():
    # The claim cites INDEX_PAGE as source_url, but "CloseKnit Health" (the full name) only
    # appears verbatim on SUBPAGE -- the exact shape of the real bug. Without corpus_texts this
    # must still fail (see the next test); with it, the real quote is found and the claim passes.
    claim = _claim(
        field="traction.named_customers", value="CloseKnit Health", evidence="CloseKnit Health",
    )
    ok, reason = check_claim(claim, INDEX_PAGE, corpus_texts=[INDEX_PAGE, SUBPAGE])
    assert ok, reason


def test_same_claim_still_fails_without_the_corpus_fallback():
    # Confirms the fallback is what fixes it, not some other change -- omitting corpus_texts
    # (the default, and every pre-existing call site) reproduces the original bug exactly.
    claim = _claim(
        field="traction.named_customers", value="CloseKnit Health", evidence="CloseKnit Health",
    )
    ok, reason = check_claim(claim, INDEX_PAGE)
    assert not ok and "not found" in reason


def test_list_evidence_missing_from_cited_page_but_found_elsewhere_in_corpus_passes():
    # The actual live shape: a MULTI_VALUE_FIELDS field with list value/evidence (pairwise
    # checked), not a single string -- one real entry ("CloseKnit Health", on the wrong cited
    # page) alongside one entry that's already correct on the cited page.
    claim = _claim(
        field="traction.named_customers",
        value=["Other Client Inc.", "CloseKnit Health"],
        evidence=["Other Client Inc.", "CloseKnit Health"],
    )
    ok, reason = check_claim(claim, INDEX_PAGE, corpus_texts=[INDEX_PAGE, SUBPAGE])
    assert ok, reason


def test_corpus_fallback_still_rejects_a_quote_fabricated_on_every_page():
    # The anti-hallucination floor: the fallback widens WHERE a quote may be found, never
    # WHETHER it's real. A quote that appears on no crawled page at all -- cited or otherwise --
    # must still fail exactly as before.
    claim = _claim(
        field="traction.named_customers", value="NorthLedger Inc",
        evidence="NorthLedger Inc has used our platform since 2019",
    )
    ok, reason = check_claim(claim, INDEX_PAGE, corpus_texts=[INDEX_PAGE, SUBPAGE])
    assert not ok and "not found" in reason


def test_corpus_fallback_uses_a_stricter_fuzzy_threshold_than_the_primary_page_check():
    # Found while writing this fix's own tests (see CORPUS_FALLBACK_FUZZY_THRESHOLD's docstring):
    # "Example Co" coincidentally scores fuzz.partial_ratio == 90 (FUZZY_THRESHOLD's own cutoff)
    # against this unrelated page text. A single-page check at the normal threshold would wrongly
    # accept it; the fallback's stricter threshold must not.
    claim = _claim(field="company_identity.name", value="Example Co", evidence="Example Co")
    unrelated_page = "Example\nNothing relevant here."
    ok, reason = check_claim(claim, "", corpus_texts=[unrelated_page])
    assert not ok and "not found" in reason


def test_corpus_fallback_quote_still_must_support_its_value():
    # The quote is real (found via the fallback), but it's been paired with a value it doesn't
    # actually support -- value_supported_by_quote still applies regardless of which page the
    # quote was found on.
    claim = _claim(
        field="traction.named_customers", value="CloseKnit Health, 500 employees",
        evidence="CloseKnit Health",
    )
    ok, reason = check_claim(claim, INDEX_PAGE, corpus_texts=[INDEX_PAGE, SUBPAGE])
    assert not ok and "support" in reason


# --- B-38: an inferred revenue model needs SOME pricing/billing signal in its quote -----------
# check_claim() skips value_supported_by_quote() entirely for inferred claims (legitimate
# inferences routinely share no words with their quote), but that shouldn't mean ANY quote can
# support ANY conclusion. Real, live bug: bajajauto.com's market-cap fact was used to infer
# "product sales"; thoughtbot.com's quality/positioning statement was used to infer
# "project-based" -- neither quote says anything about pricing, billing or how money changes
# hands at all.

MARKET_CAP_PAGE = (
    "Bajaj Auto is the first two-wheeler and three-wheeler company in the world to have reached "
    "a market capitalisation of INR one trillion."
)

POSITIONING_PAGE = (
    "We specialize in building and modernizing software where reliability, compliance, and "
    "long-term maintainability matter as much as speed."
)


def test_inferred_revenue_model_from_a_market_cap_fact_is_rejected():
    claim = Claim(
        claim_id="c15", field="pricing.revenue_model", status="inferred",
        value="product sales", source_url="https://x.example/about",
        evidence=MARKET_CAP_PAGE, retrieved_at="2026-09-27",
        notes="The page discusses market capitalisation and sales, implying product sales.",
    )
    ok, reason = check_claim(claim, MARKET_CAP_PAGE)
    assert not ok
    assert "pricing/billing signal" in reason


def test_inferred_revenue_model_from_a_positioning_statement_is_rejected():
    claim = Claim(
        claim_id="c16", field="pricing.revenue_model", status="inferred",
        value="project-based", source_url="https://x.example/",
        evidence=POSITIONING_PAGE, retrieved_at="2026-09-27",
        notes="The focus on building software suggests project-based work.",
    )
    ok, reason = check_claim(claim, POSITIONING_PAGE)
    assert not ok
    assert "pricing/billing signal" in reason


def test_inferred_revenue_model_with_a_real_pricing_signal_still_passes():
    # Same shape as the two rejections above, but the quote actually mentions prices -- must not
    # be collaterally blocked by this new guard.
    claim = Claim(
        claim_id="c17", field="pricing.revenue_model", status="inferred",
        value="subscription", source_url="https://x.example/pricing",
        evidence="Just clear, fixed prices.", retrieved_at="2026-09-27",
        notes="Fixed prices, billed on an ongoing basis, indicate a subscription model.",
    )
    ok, reason = check_claim(claim, "Just clear, fixed prices. No per-user fees.")
    assert ok, reason


def test_this_guard_is_scoped_to_revenue_model_and_does_not_touch_other_inferred_fields():
    # products.delivery_model's own legitimate indirect-inference pattern (rule 8's whole reason
    # for existing) must be completely unaffected -- its quote never mentions pricing either.
    claim = Claim(
        claim_id="c18", field="products.delivery_model", status="inferred",
        value="software as a service", source_url="https://x.example/",
        evidence="Sign in from your laptop, tablet, or phone -- nothing to install.",
        retrieved_at="2026-09-27",
        notes="Multi-device, install-free access is typical of a SaaS product.",
    )
    ok, reason = check_claim(claim, "Sign in from your laptop, tablet, or phone -- nothing to install.")
    assert ok, reason


def test_market_cap_fact_still_rejected_even_with_a_currency_code_present():
    # Deliberately checks that a bare currency CODE ("INR") does not count as a pricing signal --
    # only a currency SYMBOL or an actual pricing/billing word does. The real bajajauto.com quote
    # says "INR one trillion" (market cap, spelled out, no $/₹ symbol) -- this must still fail.
    assert "inr" in MARKET_CAP_PAGE.lower()  # sanity: the currency code really is in this quote
    claim = Claim(
        claim_id="c19", field="pricing.revenue_model", status="inferred",
        value="product sales", source_url="https://x.example/about",
        evidence=MARKET_CAP_PAGE, retrieved_at="2026-09-27",
        notes="Market capitalisation implies revenue from product sales.",
    )
    ok, reason = check_claim(claim, MARKET_CAP_PAGE)
    assert not ok and "pricing/billing signal" in reason


def test_inferred_subscription_revenue_model_with_genuine_recurring_evidence_still_passes():
    # The guard fires only on contact-sales-style evidence -- a real recurring-billing quote
    # (no contact-sales phrase at all) must not be affected.
    claim = Claim(
        claim_id="c14", field="pricing.revenue_model", status="inferred",
        value="subscription", source_url="https://x.example/pricing",
        evidence="Billed automatically every month until you cancel.",
        retrieved_at="2026-09-27", notes="Recurring monthly billing implies a subscription model.",
    )
    ok, reason = check_claim(
        claim, "Billed automatically every month until you cancel. No setup fees."
    )
    assert ok, reason


# --- products.names bare-label guard (added 2026-10-02) --------------------------------------
# See wi/validate/evidence.py's module docstring for the live loom.com evidence this fixes: a
# use-case/solutions hub page lists several "[base] for [audience]" cards, and the model quotes
# each bare label back as its own "evidence" -- technically real page text (quote_in_page passes,
# value_supported_by_quote passes with 100% word overlap on itself), but proving nothing about
# whether the page actually presents it as a genuine product rather than a card/menu label.

USE_CASE_HUB_PAGE = (
    "# Explore ways to use NorthLedger across your team\n"
    "NorthLedger for Sales\n"
    "NorthLedger for Support\n"
    "NorthLedger for Design\n"
)


def test_bare_label_evidence_for_products_names_is_rejected():
    claim = _claim(
        field="products.names",
        value=["NorthLedger for Sales"],
        evidence=["NorthLedger for Sales"],  # nothing but the value itself
        source_url="https://x.example/use-case",
    )
    ok, reason = check_claim(claim, USE_CASE_HUB_PAGE)
    assert not ok and "repeated back verbatim" in reason


def test_genuine_sentence_evidence_for_products_names_still_passes():
    claim = _claim(
        field="products.names",
        value=["NorthLedger Insights"],
        evidence=["NorthLedger Insights (Products menu, own page)"],
        source_url="https://x.example/products/insights",
    )
    page = "# NorthLedger Insights\nNorthLedger Insights (Products menu, own page)\n"
    ok, reason = check_claim(claim, page)
    assert ok, reason


def test_bare_label_guard_is_scoped_to_products_names_and_does_not_touch_other_list_fields():
    # The exact same bare-repeat shape on a different list field must be unaffected -- this
    # guard is deliberately narrow to products.names only, the same scoping discipline as the
    # pricing.revenue_model guards above.
    claim = _claim(
        field="traction.named_customers",
        value=["Acme Corp"],
        evidence=["Acme Corp"],
        source_url="https://x.example/customers",
    )
    page = "# Customers\nAcme Corp\n"
    ok, reason = check_claim(claim, page)
    assert ok, reason


def test_check_claim_items_keeps_the_genuine_item_and_drops_the_bare_repeat():
    # Partial credit (B-40): one real, sentenced item alongside one bare-repeat item should keep
    # only the real one, not discard both or keep both.
    claim = _claim(
        field="products.names",
        value=["NorthLedger Insights", "NorthLedger for Sales"],
        evidence=[
            "NorthLedger Insights (Products menu, own page)",
            "NorthLedger for Sales",
        ],
        source_url="https://x.example/use-case",
    )
    page = (
        "# NorthLedger Insights\nNorthLedger Insights (Products menu, own page)\n"
        "# Explore ways to use NorthLedger\nNorthLedger for Sales\n"
    )
    results = check_claim_items(claim, page)
    assert [ok for ok, _, _ in results] == [True, False]
    assert "repeated back verbatim" in results[1][1]


# --- B-53: company_identity.headquarters country-name guard --------------------------------

def test_unquoted_country_is_accepted_for_headquarters_when_not_contradicted():
    # The real razorpay.com case (2026-10-02 held-out run): city/state genuinely verbatim-quoted
    # (Bangalore/Bengaluru via the B-44 alias), but the address block never spells out the
    # country at all. A near-certain inference, not a hallucination -- should now pass.
    value = "Bengaluru, Karnataka, India"
    quote = "1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, Karnataka - 560030"
    assert value_supported_by_quote(value, quote, field="company_identity.headquarters")


def test_unquoted_country_still_rejected_for_every_other_field():
    # The exact same value/quote pair must still fail when the field isn't headquarters --
    # B-53 is deliberately scoped, not a general relaxation of the overlap check.
    value = "Bengaluru, Karnataka, India"
    quote = "1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, Karnataka - 560030"
    assert not value_supported_by_quote(value, quote)
    assert not value_supported_by_quote(value, quote, field="customers.segments")


def test_contradicted_country_still_fails_for_headquarters():
    # A value naming a DIFFERENT country than the one the quote LITERALLY states is a genuine
    # hallucination, not an omission -- B-53's fail-safe guard must not let this through. Note
    # the quote here spells out "India" explicitly (unlike the real razorpay.com case above),
    # so this exercises the contradiction branch rather than the omission branch.
    value = "Bengaluru, Karnataka, Singapore"
    quote = (
        "1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, "
        "Karnataka, India - 560030"
    )
    assert not value_supported_by_quote(value, quote, field="company_identity.headquarters")


def test_wrong_city_still_fails_for_headquarters_despite_b53():
    # B-53 only forgives an unquoted COUNTRY -- a wrong city is still a real mismatch.
    value = "Mumbai, Karnataka, India"
    quote = "1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, Karnataka - 560030"
    assert not value_supported_by_quote(value, quote, field="company_identity.headquarters")


def test_check_claim_end_to_end_accepts_the_real_razorpay_headquarters_case():
    claim = _claim(
        field="company_identity.headquarters",
        value="Bengaluru, Karnataka, India",
        evidence=(
            "1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, "
            "Karnataka - 560030"
        ),
        source_url="https://razorpay.com/about",
    )
    page = (
        "# About Razorpay\nRegd. Office: 1st Floor, SJR Cyber, 22, Laskar Hosur Road, "
        "Adugodi, Bangalore, Karnataka - 560030\n"
    )
    ok, reason = check_claim(claim, page)
    assert ok, reason


def test_check_claim_end_to_end_still_rejects_a_hallucinated_country():
    # Unlike the real razorpay.com case above, this page literally states a country ("India")
    # -- so a value claiming a DIFFERENT country is a genuine contradiction, not an omission,
    # and must still be rejected end-to-end.
    claim = _claim(
        field="company_identity.headquarters",
        value="Bengaluru, Karnataka, Singapore",
        evidence=(
            "1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, "
            "Karnataka, India - 560030"
        ),
        source_url="https://razorpay.com/about",
    )
    page = (
        "# About Razorpay\nRegd. Office: 1st Floor, SJR Cyber, 22, Laskar Hosur Road, "
        "Adugodi, Bangalore, Karnataka, India - 560030\n"
    )
    ok, reason = check_claim(claim, page)
    assert not ok and "support" in reason


# --- B-56: a joining comma/semicolon in the model's quote must not fail an otherwise real quote ---

SIMPLESTORES_PAGE = (
    "Standard\n₹499/month + GST\nEverything needed to launch and run a focused online business.\n"
    "Business\n₹1,499/month + GST\nGrowth operations for teams selling across channels.\n"
    "Professional\n₹2,499/month + GST\nEnterprise\nCustom pricing\n"
)


# 0.97 is the corpus-wide fallback threshold (B-36), the one that actually rejected the real
# simplestores.in quote; at the default 0.90 the older fuzzy match already lets it through.
STRICT = 0.97


def test_b56_comma_joining_two_real_lines_is_accepted():
    assert quote_in_page("Business, ₹1,499/month", SIMPLESTORES_PAGE, threshold=STRICT)
    assert quote_in_page("Enterprise, Custom pricing", SIMPLESTORES_PAGE, threshold=STRICT)


def test_b56_semicolon_joining_two_adjacent_lines_is_accepted():
    assert quote_in_page("Professional; ₹2,499/month", SIMPLESTORES_PAGE, threshold=STRICT)


def _squashed_match(quote, page):
    """Only the B-56 separator-insensitive check, without the older fuzzy fallback (a one-digit
    change in a long quote can still clear the 0.90 fuzzy threshold on its own -- that was
    always the value-vs-quote number check's job, see the claim-level test below)."""
    from wi.validate.evidence import _without_joining_separators, normalise
    return _without_joining_separators(normalise(quote)) in _without_joining_separators(normalise(page))


def test_b56_separator_check_alone_rejects_a_changed_number():
    assert _squashed_match("Business, ₹1,499/month", SIMPLESTORES_PAGE)
    assert not _squashed_match("Business, ₹1,999/month", SIMPLESTORES_PAGE)


def test_b56_a_comma_between_digits_is_never_removed():
    assert not _squashed_match("Business, ₹14,99/month", SIMPLESTORES_PAGE)
    assert not _squashed_match("Business, ₹149,9/month", SIMPLESTORES_PAGE)


def test_b56_pieces_that_are_not_adjacent_are_not_matched_by_the_separator_check():
    assert not _squashed_match("Standard, ₹1,499/month", SIMPLESTORES_PAGE)


def test_b56_a_wrong_number_in_the_value_is_still_rejected_at_claim_level():
    claim = _claim(
        value="Business, ₹1,999/month", evidence="Business, ₹1,499/month",
        source_url="https://x.example/pricing/details",
    )
    ok, _ = check_claim(claim, SIMPLESTORES_PAGE)
    assert not ok


def test_b56_a_joined_quote_passes_the_full_claim_check():
    claim = _claim(
        value="Business, ₹1,499/month", evidence="Business, ₹1,499/month",
        source_url="https://x.example/pricing/details",
    )
    ok, reason = check_claim(claim, SIMPLESTORES_PAGE)
    assert ok, reason


# --- B-57: "/mo"-style per-period prices count as a billing signal for revenue_model ---

def test_b57_per_month_price_with_glued_currency_code_is_a_pricing_signal():
    page = "Plus\n379USD/mo after 14 days\nBusiness\n266USD/mo after 14 days"
    claim = _claim(
        field="pricing.revenue_model", value="subscription", status="inferred", notes="monthly price implies subscription",
        evidence="379USD/mo after 14 days", source_url="https://x.example/pricing",
    )
    ok, reason = check_claim(claim, page)
    assert ok, reason


def test_b57_a_valuation_fact_is_still_not_a_pricing_signal():
    page = "The company has a market capitalisation of INR one trillion."
    claim = _claim(
        field="pricing.revenue_model", value="subscription", status="inferred", notes="test",
        evidence="market capitalisation of INR one trillion", source_url="https://x.example/about",
    )
    ok, reason = check_claim(claim, page)
    assert not ok and "pricing/billing signal" in reason


def test_b57_words_that_merely_start_with_mo_are_not_a_pricing_signal():
    page = "Explore our products and/more features for every team."
    claim = _claim(
        field="pricing.revenue_model", value="subscription", status="inferred", notes="test",
        evidence="Explore our products and/more features", source_url="https://x.example/",
    )
    ok, reason = check_claim(claim, page)
    assert not ok and "pricing/billing signal" in reason


# --- B-59: "pricing" and usage-billing words count as a billing signal for revenue_model ---

def test_b59_consumption_based_pricing_quote_is_a_pricing_signal():
    page = "We keep pricing simple with a consumption-based pricing model."
    claim = _claim(
        field="pricing.revenue_model", value="consumption-based", status="inferred", notes="usage billing",
        evidence="We keep pricing simple with a consumption-based pricing model.", source_url="https://x.example/pricing",
    )
    ok, reason = check_claim(claim, page)
    assert ok, reason


def test_b59_pricing_alone_is_a_pricing_signal():
    page = "Transparent pricing for every team."
    claim = _claim(
        field="pricing.revenue_model", value="subscription", status="inferred", notes="test",
        evidence="Transparent pricing for every team", source_url="https://x.example/pricing",
    )
    ok, reason = check_claim(claim, page)
    assert ok, reason


def test_b59_usage_based_and_metered_are_pricing_signals():
    for quote in ("Usage-based billing that scales with you", "Metered by the second, no minimums"):
        claim = _claim(
            field="pricing.revenue_model", value="usage-based", status="inferred", notes="test",
            evidence=quote, source_url="https://x.example/pricing",
        )
        ok, reason = check_claim(claim, quote + ".")
        assert ok, (quote, reason)


def test_b59_a_quote_with_no_money_word_still_fails_the_guard():
    page = "The most ambitious companies run on us, with scalability, control, and security."
    claim = _claim(
        field="pricing.revenue_model", value="subscription", status="inferred", notes="test",
        evidence="The most ambitious companies run on us", source_url="https://x.example/",
    )
    ok, reason = check_claim(claim, page)
    assert not ok and "pricing/billing signal" in reason


# ---- B-63: re-pair a shifted evidence list with the values it supports -------------------------
from wi.validate.evidence import realign_list_evidence  # noqa: E402

_INDUSTRIES_PAGE = (
    "Customers\nFinancial Services and Technology\nProduct Design\n"
    "Conversational Relationship Platform\nDry cleaning and laundry\n"
)


def _industries(values, evidence):
    return _claim(field="customers.industries", value=values, evidence=evidence)


def test_b63_shifted_evidence_is_repaired_and_passes():
    claim = _industries(
        ["Financial Services", "Technology", "Product Design"],
        ["Financial Services and Technology", "Product Design", "Product Design"],
    )
    assert check_claim(claim, _INDUSTRIES_PAGE)[0] is False        # the old, positional behaviour
    fixed, moved = realign_list_evidence(claim, _INDUSTRIES_PAGE)
    assert moved == 1
    assert fixed.evidence == ["Financial Services and Technology",
                              "Financial Services and Technology", "Product Design"]
    assert check_claim(fixed, _INDUSTRIES_PAGE)[0] is True


def test_b63_only_quotes_from_the_claims_own_evidence_list_are_used():
    # "Retail" is real page text, but it is not in this claim's evidence list, so it is not used.
    page = _INDUSTRIES_PAGE + "Retail\n"
    claim = _industries(["Financial Services", "Retail"],
                        ["Financial Services and Technology", "Product Design"])
    fixed, moved = realign_list_evidence(claim, page)
    assert moved == 0 and fixed.evidence == claim.evidence


def test_b63_an_item_with_no_supporting_quote_stays_failed():
    claim = _industries(["Technology", "Customer Support"],
                        ["Financial Services and Technology", "Dry cleaning and laundry"])
    fixed, moved = realign_list_evidence(claim, _INDUSTRIES_PAGE)
    assert moved == 0
    assert check_claim_items(fixed, _INDUSTRIES_PAGE)[1][0] is False


def test_b63_a_fabricated_quote_is_never_adopted():
    claim = _industries(["Technology", "Healthcare"],
                        ["Financial Services and Technology", "Healthcare and life sciences"])
    fixed, moved = realign_list_evidence(claim, _INDUSTRIES_PAGE)   # 2nd quote is not on the page
    assert moved == 0


def test_b63_bare_self_repeat_is_not_a_way_around_the_product_name_guard():
    page = "Loom for Sales\nLoom for Support\n"
    claim = _claim(field="products.names", value=["Loom for Sales", "Loom for Support"],
                   evidence=["Loom for Support", "Loom for Sales"])
    fixed, moved = realign_list_evidence(claim, page)
    assert moved == 0


def test_b63_aligned_claims_and_single_values_are_untouched():
    ok = _industries(["Financial Services"], ["Financial Services and Technology"])
    assert realign_list_evidence(ok, _INDUSTRIES_PAGE) == (ok, 0)
    single = _claim()
    assert realign_list_evidence(single, PAGE) == (single, 0)


# ---- B-64: spelled-out numbers, and "; "-joined evidence ---------------------------------------
_SALES_PAGE = "Pricing\nFree\nGet started for free\nEnterprise\nTalk to sales\nSupport hours\n"


def _sales_claim(evidence):
    return _claim(field="pricing.sales_motion", status="inferred", notes="cues",
                  value="Self-serve signup; contact sales for Enterprise", evidence=evidence)


def test_b64_semicolon_joined_real_lines_pass():
    assert check_claim(_sales_claim("Get started for free; Talk to sales"), _SALES_PAGE)[0] is True


def test_b64_semicolon_joined_with_a_fabricated_piece_still_fails():
    ok, _ = check_claim(_sales_claim("Get started for free; Book a private jet"), _SALES_PAGE)
    assert ok is False


def test_b64_a_real_one_line_quote_containing_a_semicolon_is_left_whole():
    page = "Plans start at $10; cancel any time. Contact us for volume pricing."
    claim = _claim(field="pricing.revenue_model", status="inferred", notes="n", value="subscription",
                   evidence="Plans start at $10; cancel any time.")
    assert check_claim(claim, page)[0] is True


def test_b64_semicolon_pieces_work_for_a_list_value_too():
    claim = _claim(field="traction.certifications", value=["SOC 2", "ISO 27001"],
                   evidence="SOC 2; ISO 27001")
    page = "Security\nSOC 2\nCompliance\nISO 27001\n"
    assert check_claim(claim, page)[0] is True
    assert all(ok for ok, _, _ in check_claim_items(claim, page))


def test_b64_spelled_out_number_in_the_quote_supports_a_digit_value():
    claim = _claim(field="pricing.free_trial", value="7-day trial", evidence="Seven-day trial.")
    assert check_claim(claim, "Start today. Seven-day trial. No card.")[0] is True


def test_b64_a_different_number_is_still_rejected():
    claim = _claim(field="pricing.free_trial", value="14-day trial", evidence="Seven-day trial.")
    assert check_claim(claim, "Start today. Seven-day trial. No card.")[0] is False


def test_b67_realign_never_borrows_another_items_bare_label_as_evidence():
    # Live notion.com: "Notion AI" quoted itself (a bare self-repeat, rejected) and B-63 then
    # re-paired it with "Notion Calendar" -- another item's bare label -- because both contain
    # "Notion". That laundered a rejected item into a kept claim citing the wrong product.
    page = "Notion AI\nNotion Calendar\nCustom Agents automate recurring work for your entire team.\n"
    claim = Claim(
        claim_id="n:products.names:3", field="products.names", status="extracted",
        value=["Notion AI", "Custom Agents", "Notion Calendar"],
        source_url="https://www.notion.com/product/ai", retrieved_at="2026-10-06",
        evidence=["Notion AI", "Custom Agents automate recurring work for your entire team.",
                  "Notion Calendar"],
    )
    fixed, moved = realign_list_evidence(claim, page)
    assert moved == 0 and fixed.evidence == claim.evidence


def test_b67_realign_still_uses_a_real_sentence_for_products_names():
    page = "Notion AI\nMeet Notion AI, your assistant inside every page.\nNotion Calendar\n"
    claim = Claim(
        claim_id="n:products.names:3", field="products.names", status="extracted",
        value=["Notion AI", "Notion Calendar"],
        source_url="https://www.notion.com/", retrieved_at="2026-10-06",
        evidence=["Notion AI", "Meet Notion AI, your assistant inside every page."],
    )
    fixed, moved = realign_list_evidence(claim, page)
    assert moved == 1 and fixed.evidence[0] == "Meet Notion AI, your assistant inside every page."



# --- B-81: delivery_model keeps only the bracketed detail its quote mentions --------------------

def test_b81_trims_details_the_quote_never_mentions():
    from wi.validate.evidence import trim_delivery_model_details
    # Loom: the quote names a Chrome extension, desktop app and mobile app, but no web app.
    value, dropped = trim_delivery_model_details(
        "software (web app, desktop app, mobile app)",
        "Record on any device using Loom's Chrome extension, desktop app or mobile app.")
    assert value == "software (desktop app, mobile app)"
    assert dropped == ["web app"]


def test_b81_all_details_unsupported_leaves_the_bare_category():
    from wi.validate.evidence import trim_delivery_model_details
    # Freshworks: "cloud-based" is nowhere in the quote.
    value, dropped = trim_delivery_model_details(
        "software (cloud-based)", "AI-powered customer service software")
    assert value == "software"
    assert dropped == ["cloud-based"]


def test_b81_supported_details_plurals_and_list_evidence_are_kept_unchanged():
    from wi.validate.evidence import trim_delivery_model_details
    assert trim_delivery_model_details(
        "software (desktop app, mobile app)", ["Get the desktop apps", "and our mobile apps"]
    ) == ("software (desktop app, mobile app)", [])
    assert trim_delivery_model_details("software", "Anything at all") == ("software", [])
    assert trim_delivery_model_details("physical (dealer network)", "Visit our dealer network") \
        == ("physical (dealer network)", [])
