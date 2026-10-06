"""Tests for wi.extract.prompt -- just the plumbing (right roles, every field
and page actually reaches the prompt text), not the LLM's response to it."""
from __future__ import annotations

from wi.crawl.clean import CleanPage
from wi.extract.fields import FIELDS, MULTI_VALUE_FIELDS
from wi.extract.prompt import build_messages

PAGE = CleanPage(url="https://example.com/pricing", title="Pricing", text="Plans start at $10/mo.")


def test_build_messages_has_system_and_user_roles():
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    assert [m["role"] for m in messages] == ["system", "user"]


def test_every_field_listed_in_the_user_prompt():
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    user_content = messages[1]["content"]
    for f in FIELDS:
        assert f in user_content


def test_page_url_and_text_included_in_the_user_prompt():
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    user_content = messages[1]["content"]
    assert PAGE.url in user_content
    assert "$10/mo" in user_content


def test_inference_whitelist_named_in_the_system_prompt():
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert "pricing.sales_motion" in system_content


def test_multi_value_fields_named_in_the_system_prompt():
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    for f in MULTI_VALUE_FIELDS:
        assert f in system_content


def test_system_prompt_forbids_combining_separate_quotes_into_one():
    # Rule 6 (decided 2026-09-23): the model must use an evidence array for spans that come
    # from different parts of the page, instead of fabricating one combined quote -- the
    # basecamp.com pricing bug this fixes.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert "evidence" in system_content and "array" in system_content
    assert "Never merge separate" in system_content


def test_system_prompt_forbids_paraphrasing_and_forbids_merging_single_string_facts():
    # Rule 7 (decided 2026-09-24): reproduces two real basecamp.com bugs -- the model
    # paraphrasing company_identity.description instead of quoting it, and merging two
    # separate facts (30-day trial, 45-day Unlimited exception) into one invented sentence
    # for pricing.free_trial, a single-string field the rule 6 array fix doesn't cover.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert "Never write your own summary" in system_content
    assert "smaller true claim beats a" in system_content


def test_system_prompt_tells_model_to_infer_not_extract_when_quote_is_indirect():
    # Rule 8 (decided 2026-09-24): reproduces a real basecamp.com bug -- the model marked
    # products.delivery_model "extracted" against a quote that only indirectly supports a
    # SaaS conclusion (multi-platform app availability, never the words "SaaS" itself),
    # which fails the stricter extracted-claim check. This field is on the inference
    # whitelist specifically so "inferred" + notes can be used instead.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert 'use status "inferred"' in system_content
    assert "products.delivery_model" in system_content


def test_system_prompt_specifies_the_paired_array_format_for_conflicting_claims():
    # B-06/EVD-05 (2026-09-27): rule 2's "conflicting" bullet used to say only "value describing
    # both", with no format specified -- now it must tell the model to use a paired array, same
    # shape as rule 6's multi-value evidence arrays, since wi/schemas/claim.py now enforces
    # exactly that shape (see tests/test_claim.py's conflicting-status tests).
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert '"conflicting"' in system_content
    assert "JSON array of the differing raw values" in system_content


def test_system_prompt_points_the_model_at_the_title_line_for_name_fields():
    # Rule 9, take 2 ("title-pointing", 2026-09-27): a second, separately-scoped bounded trial
    # after take 1 (a restated evidence-support requirement) measured no gain and was reverted.
    # This version tells the model directly to check each page's TITLE line -- always present in
    # the user prompt (see build_messages() below) -- for a name-field quote, since a page's own
    # title very often names the company even when the body text talks about it without ever
    # using the name (zerodha's and thoughtbot's exact take-1 failure shape).
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert "check each page's TITLE line first" in system_content
    assert "company_identity.name" in system_content


def test_system_prompt_tells_model_a_single_instance_is_enough_for_a_list_field():
    # Rule 11 (2026-09-27), the list-field extraction bounded prompt-optimisation trial: the
    # crawl-coverage-misses investigation found the model reporting not_found for a
    # MULTI_VALUE_FIELDS field (named customers, partnerships, certifications, segments,
    # industries) on pages it had definitely been given -- the working hypothesis is that these
    # facts usually show up as one scattered mention rather than a complete, curated list, and
    # the model over-generalises rules 3/4/7's "prefer not_found over guessing" caution into
    # skipping the field whenever what it sees doesn't look like a full list. This is only a
    # plumbing check that the instruction reaches the model; it can't itself measure whether the
    # trial produces a real accuracy gain -- see PROGRESS.md for the live before/after.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert "A single genuinely quotable instance is enough" in system_content
    assert "traction.named_customers" in system_content


def test_system_prompt_gives_delivery_model_its_four_category_vocabulary():
    # Rule 12 (2026-09-27): the Final PRD (Section 4, Group B) defines products.delivery_model
    # over exactly four categories -- but nothing before this rule ever gave the model that
    # vocabulary, so it invented its own descriptive categories instead: a real, live bug found
    # while investigating this field's flat 0% baseline accuracy ("manufacturing" for
    # bajajauto.com, "consulting" for thoughtbot.com -- neither is one of the PRD's four words).
    # This is only a plumbing check that the vocabulary and the ban on inventing other categories
    # reach the model; PROGRESS.md has the live diagnosis this rule is based on.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert '"software", "service", "marketplace", or "physical"' in system_content
    assert "products.delivery_model" in system_content
    assert "manufacturing" in system_content  # named as an example of an invalid category


def test_system_prompt_asks_software_delivery_model_to_name_channels_the_page_mentions():
    # B-66 (2026-10-06): 4 of 5 dev labels describe the channels ("web, browser extension, desktop
    # app, mobile app") while the system answered the bare word "software" and scored incorrect.
    # Rule 12 now asks for the channels the pages name, and bans adding a channel no page mentions.
    # Plumbing check only: the live effect is measured by the dev-set rerun.
    messages = build_messages("https://example.com/", [PAGE], "2026-10-06")
    system_content = messages[0]["content"]
    assert "DELIVERY CHANNELS" in system_content
    assert "software (browser extension, desktop app, mobile app)" in system_content
    assert "never add a channel because companies like this usually have one" in system_content
    assert "bare category word" in system_content


def test_system_prompt_says_customer_segments_are_types_not_industries():
    # B-69 (2026-10-06): customers.segments came back as an industries list on snowflake.com
    # (Retail, Healthcare, Manufacturing ...), simplestores.in and calendly.com; the label style is
    # a customer type or size ("Individuals, Small business, Large companies"). Plumbing check only.
    messages = build_messages("https://example.com/", [PAGE], "2026-10-06")
    system_content = messages[0]["content"]
    assert "TYPES or SIZES of customer" in system_content
    assert "belongs to \"customers.industries\"" in system_content
    assert "return not_found for \"customers.segments\"" in system_content
    # B-70: the industries list must be sent to customers.industries, not dropped
    assert "report that same list under" in system_content
    assert "Do not leave both fields not_found" in system_content


def test_system_prompt_forbids_a_list_value_for_customers_segments():
    # Rule 13 (2026-09-27): the Week 4 held-out run scored customers.segments at 0/10 (100%
    # miss); 3 of 10 sites (razorpay.com, thoughtworks.com, nobroker.com) failed because the
    # model returned a JSON array for this field, which wi/schemas/claim.py's validator
    # correctly rejects since the field is not in MULTI_VALUE_FIELDS, silently downgrading a
    # real extraction to not_found. Likely cause: this field sits right next to
    # customers.industries, which IS array-shaped, and both fields' natural answer is often
    # several distinct named groups. This is only a plumbing check that the explicit contrast
    # and worked example reach the model; PROGRESS.md has the live diagnosis this rule is
    # based on.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert "customers.segments" in system_content
    assert "customers.industries" in system_content
    assert 'exploding it into an array here violates that rule' in system_content


def test_system_prompt_gives_sales_motion_its_cue_vocabulary_and_contrasts_revenue_model():
    # Rule 14 (2026-09-27): the Week 4 held-out run scored pricing.sales_motion at a flat 0%
    # across all 10 sites -- the only field with zero credit anywhere. 7/10 sites got not_found
    # despite an obvious, crawled signup- or contact-sales CTA in the given page text (the same
    # over-cautious gap rule 11 fixed for list fields, but this field isn't list-shaped so rule 11
    # never covered it); the other 3/10 answered with a pricing.revenue_model-style concept
    # ("pay-per-use", "direct sales") instead of an actual sales-motion one, since nothing before
    # this rule told the model the two adjacent fields ask different questions. This is only a
    # plumbing check that the cue vocabulary and the revenue_model contrast reach the model;
    # PROGRESS.md has the live diagnosis this rule is based on.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert "pricing.sales_motion" in system_content
    assert "pricing.revenue_model" in system_content
    assert "Contact Sales" in system_content and "Request a Demo" in system_content
    assert "do not reuse revenue-model words" in system_content


def test_system_prompt_tells_model_to_trust_the_pricing_page_and_read_all_of_it_for_sales_motion():
    # Rule 17 / B-52 (2026-09-27): pricing.sales_motion's held-out score fell 20% -> 0%, but
    # rule 14's "report both" instruction was already correct and unchanged -- confirmed live
    # (WebFetch of razorpay.com/pricing, which the run's own crawl.pages list shows WAS crawled)
    # that the model instead used a homepage sentence with no sales-motion signal at all as its
    # evidence, entirely ignoring the crawled pricing page's own explicit self-serve AND
    # contact-sales cues; plaid.com showed a narrower version, citing the right page but stopping
    # after its first tier's cue. Rule 17 tells the model which page to trust (the one marked
    # pricing by URL/TITLE) and to read all of it, not just the first cue, before answering. This
    # is only a plumbing check that the instruction and worked example reach the model;
    # wi/extract/prompt.py's module docstring has the live diagnosis.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert "is where this field's real answer almost always lives" in system_content
    assert "keep reading the rest of that same page for a SECOND, contrasting cue" in system_content
    assert "Enterprise" in system_content and "Get a custom plan" in system_content


def test_system_prompt_tells_the_model_to_search_for_one_real_sentence_before_composing_segments():
    # Rule 15 (2026-09-27): a live fetch of sarvam.ai/about-us during held-out root-causing found
    # the model rejecting its own composed sentence ("We are building for enterprises, governments
    # and developers.") for customers.segments when the real page already had one sentence stating
    # the same segments together, verbatim -- a rule 7 violation even though every fact in the
    # composed version was true. Rule 15 tells the model to search for that real sentence first,
    # and explains the B-42 multi-fragment "evidence" fallback (wi/validate/evidence.py) for when
    # segments genuinely have no single covering sentence. This is only a plumbing check that both
    # the instruction and the worked example reach the model; PROGRESS.md has the live diagnosis.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert "search ALL the given" in system_content
    assert "JSON array of the separate" in system_content
    assert "Never invent a fragment or a joining phrase between them" in system_content


def test_system_prompt_tells_the_model_to_name_specific_items_not_a_vague_category_for_list_fields():
    # Rule 16 / B-50 (2026-09-27): found live on gong.io while confirming B-49 -- the real trust
    # page names 8 specific certifications, each on its own line, but the model's
    # traction.certifications claim gave value ["SOC 2", "ISO standards"] backed by one general
    # summary sentence naming neither -- the array-field version of rule 15's single-string
    # pattern. traction.certifications sat at 20% across all 10 held-out sites with the same
    # shape recurring elsewhere, so this is not a one-off. This is only a plumbing check that the
    # instruction and worked example reach the model; PROGRESS.md has the live diagnosis.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert "never a vague category description" in system_content
    assert "traction.certifications" in system_content
    assert "SOC 2 Type II" in system_content


def test_system_prompt_asks_for_a_separate_announcements_array():
    # Rule 10 / B-07/OUT-04 (2026-09-27): dated company-reported announcements (funding,
    # product launches, and similar) must be asked for in a separate top-level array, never
    # folded into any of the 15 "claims" fields -- see wi/schemas/announcement.py.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    assert '"announcements"' in system_content
    assert "Never fold one of these into any of the 15 fields" in system_content
    assert "leave it out of \"announcements\" entirely" in system_content


# Company names from every dev-set and held-out benchmark site in eval/benchmark_sites.md
# (PRD Appendix A). Kept as a literal list rather than parsing the markdown table, since the
# whole point is to catch the prompt referencing one of these even if the benchmark list
# itself changes later.
BENCHMARK_SITE_NAMES = [
    "Basecamp", "Darwinbox", "Zerodha", "Bajaj Auto", "thoughtbot",
    "Berkshire Hathaway", "Linear", "Urban Company", "Razorpay", "Buffer",
    "Innovaccer", "Sarvam", "Tata Motors", "Thoughtworks", "NoBroker", "Gong", "Plaid",
    # Current dev set (2026-09-27 swap, see eval/baseline.py's DEV_SET comment) -- added
    # 2026-10-02 after rule 18's worked example was found naming "Calendly" unnoticed,
    # which is exactly the gap this list exists to close.
    "Calendly", "Loom", "Typeform", "Notion", "SimpleStores",
]


def test_system_prompt_worked_examples_do_not_name_a_real_benchmark_site():
    # Regression test for a bug found on the first live Day-5 baseline run (2026-09-26):
    # rule 7 and rule 8's worked examples used to quote real basecamp.com text almost
    # verbatim (they were written to reproduce real bugs seen on that exact site). Basecamp
    # is a permanent PRD benchmark site (D1), so every future baseline run against it hands
    # the model its own real page text right next to an in-context example built from that
    # same real text -- and the live run showed the model echoing the example's wording
    # instead of quoting the actual crawled text it was given that time. Worked examples
    # must stay generic and fictional so there is nothing for the model to copy from its own
    # instructions rather than from the page it's supposed to be reading.
    messages = build_messages("https://example.com/", [PAGE], "2026-09-22")
    system_content = messages[0]["content"]
    for name in BENCHMARK_SITE_NAMES:
        assert name.lower() not in system_content.lower(), (
            f"system prompt worked examples must not name a real benchmark site ({name!r} "
            f"found) -- see this test's docstring for why"
        )
