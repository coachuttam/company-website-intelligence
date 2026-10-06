"""Deterministic evidence checks (EVD-02). This is the anti-hallucination layer. No LLM involved.

Two checks:
1. quote_in_page: the quote is verbatim or near-verbatim text from the cleaned page.
2. value_supported_by_quote: the quote actually supports the value (key terms present).

A quote can exist on a page and still not support the claimed value, so both are required.

value_supported_by_quote has two layers, checked per item:
- a numeric check: every number in the item must appear in the quote. This alone catches a
  wrong price or a wrong count.
- a non-numeric check: the item's significant words must mostly (>=60%) appear in the quote.
  This exists because the numeric check alone is blind to non-numeric hallucination -- on a
  real run against basecamp.com the model attached a fabricated, specific industries list
  ("Engineering, marketing, manufacturing, design, ...") to a genuine page quote that names no
  specific industries at all ("...across every industry imaginable."). No numbers were
  involved, so the old numbers-only check passed it straight through. The word-overlap check
  catches that: none of the fabricated industry names actually appear in the quote.

`value` can be a plain string or a list of strings (Claim.value accepts either -- decided
2026-09-22, see wi/schemas/claim.py). A list value is checked item by item directly. A string
value is still split into items with the comma-splitting heuristic below, for fields the model
returns as a single string and for whatever a model returns despite the prompt's instructions.

`evidence` can also be a plain string or a list of strings (decided 2026-09-23). Real bug this
fixes: on basecamp.com's pricing page, the four plans sit on four separate lines -- there is no
one contiguous quote that covers all of them. Forced into a single `evidence` string, the model
fabricated a combined sentence that didn't literally appear on the page, and this checker
correctly rejected it, downgrading a real claim to not_found. The fix is NOT to relax what
counts as a valid quote -- a single fabricated span must still fail exactly as before. Instead,
a list-valued claim may now carry a list of evidence spans, one per value entry, checked
PAIRWISE: evidence[i] must itself be real page text (same quote_in_page check as always) AND
must itself support value[i] (same value_supported_by_quote logic, applied to that one pair).
Every span is checked independently, so a claim with three real spans and one fabricated one
still fails -- there is no way for a fabricated span to hide behind real ones. A single-string
`value`/`evidence` pair is checked exactly as before; this is additive, never a relaxation.

Multi-value claim with a single, multi-LINE `evidence` string (added 2026-09-27, the "Basecamp
pricing-format false negative"): rule 6 in wi/extract/prompt.py already tells the model to give
"evidence" as a JSON array matching "value" whenever "value" is a list -- see the paragraph
above. But nothing stops the model from ignoring that and joining the per-item quotes into one
newline-separated string instead. Reproduced twice on live basecamp.com runs: the model's
`pricing.public_plans` value (`["Free", "Freelancer, $25/mo", "Studio, $59/mo", "Pro, $99/mo",
"Unlimited, $299/mo"]`) is correct and each individual plan/price is real, verbatim page text --
but the four plans sit on separate, non-adjacent parts of the pricing page (see the paragraph
above), so the single joined `evidence` string is not itself a contiguous span of the page and
fails quote_in_page()'s fuzzy match as a whole, even though nothing in it was fabricated. That
is the exact failure mode the evidence-as-list fix above exists to prevent -- it just isn't
reached here because the model represented it as a string, not a list. check_claim() below
handles this by splitting a multi-line `evidence` string on "\n" and matching each `value` entry
against whichever line actually supports it (same quote_in_page + value_supported_by_quote pair
used everywhere else), instead of requiring the whole block to be one quote. This is not a
relaxation: every line used to support a value entry must still independently be real page text
and must still independently support that entry -- a fabricated line still fails exactly as
before, there is just no requirement that the fabricated line be squeezed in between two real
ones for the claim to be caught. A single-line `evidence` string for a list `value` is untouched
by this and still goes through the plain single-quote path below, exactly as before.

`pricing.revenue_model` pricing-signal guard (B-38, added 2026-09-27): the B-03 guard above only
catches ONE specific contradiction (contact-sales evidence paired with a subscription/recurring
conclusion). Found while root-causing this field's low baseline accuracy (0.2, with 2 of 5
dev-set sites scoring the PRD's most serious verdict, `unsupported`): the model was inferring a
revenue model from evidence that has NOTHING to do with how the company charges for its product at
all. Real, live examples: bajajauto.com's evidence "Bajaj Auto is the first two-wheeler and
three-wheeler company in the world to have reached a market capitalisation of INR one trillion."
(a market-cap/scale fact) was used to infer `"product sales"`; thoughtbot.com's evidence "We
specialize in building and modernizing software where reliability, compliance, and long-term
maintainability matter as much as speed." (a positioning/quality statement) was used to infer
`"project-based"`. Neither quote mentions pricing, billing, fees, contracts, or anything else
about how money changes hands -- these are not indirect inferences in rule 8's sense (a real,
if implicit, topical connection between quote and conclusion, like `products.delivery_model`'s
legitimate "install-free multi-device access implies SaaS" inference); they are free-associated
guesses with no evidentiary link at all, exactly what rule 4 ("prefer not_found over guessing")
exists to prevent. `check_claim()` deliberately skips `value_supported_by_quote()` for every
inferred claim (see that function's own docstring) because a legitimate inference's value
routinely shares no WORDS with its quote -- but this new guard checks something weaker and
narrower than word-overlap: does the quote contain ANY term that is even topically about pricing,
billing, or how revenue is generated at all (`_REVENUE_SIGNAL_TERMS` below)? A quote about company
scale, product philosophy, or anything else that never touches money/billing/pricing cannot
legitimately support ANY revenue-model conclusion, however indirect the reasoning is allowed to
be. Scoped to `pricing.revenue_model` only, same as B-03 -- this does not touch the general
inferred-claim exemption for any other field (including `products.delivery_model`'s own
legitimate indirect-inference pattern, rule 8's whole reason for existing).

B-59 (added 2026-10-06, found live on snowflake.com, a site in neither the dev nor the held-out
set): `_REVENUE_SIGNAL_TERMS` listed "price" but not "pricing" -- "pricing" does not contain the
substring "price" -- and had nothing for usage-billed models. So the quote "We keep pricing
simple with a consumption-based pricing model." was rejected as having no pricing/billing signal,
when it is exactly the evidence an inferred pricing.revenue_model needs. The list now also
matches pricing, consumption, usage-based/usage based and metered. It stays a "does this quote
touch money at all" guard: a quote about scale, culture or product philosophy still fails.

Corpus-wide quote fallback, the "CloseKnit Health" fix (B-36, added 2026-09-27): check_claim()
used to search ONLY the one page named by claim.source_url (wi/extract/pipeline.py's
_page_text_by_url() is a single-URL-keyed lookup). Real bug this fixes, found live on 2 of 4
independent thoughtbot.com dev-set reps: the model correctly extracted "CloseKnit Health" (a
real client name) for traction.named_customers and customers.industries, but cited
`source_url: "https://thoughtbot.com/case-studies"` (the case-studies INDEX page) -- which
displays that client only as the stylised brand "CloseKnit", with "Health" never appearing as
adjacent visible text, only inferable from the URL slug. The full string "CloseKnit Health"
appears verbatim, multiple times, on `https://thoughtbot.com/case-studies/closeknit-health` (that
client's own dedicated subpage) -- also crawled in the same run, just not the page the model
happened to name. The fact was real and genuinely quotable; the model just cited the wrong page
among several it was correctly given. Confirmed live via two direct fetches of both real pages
(see PROGRESS.md) before deciding on a fix.

Uttam's explicit decision (2026-09-27), given three options with their tradeoffs against the
PRD's evidence-traceability design (a claim's source_url is meant to say exactly where a fact
came from): broaden the search to the whole crawled corpus, the same way check_conflicting_claim()
already does for conflicting claims below -- rather than (b) correcting claim.source_url to
whichever page the quote is actually found on, or (c) leaving pass/fail untouched and only adding
a diagnostic. This is a deliberate loosening of WHERE a quote may be found, never of WHETHER it's
real: every quote must still be exact/near-exact text on SOME crawled page (quote_in_page) and
must still independently support its paired value (value_supported_by_quote) -- a genuinely
fabricated quote still fails exactly as before, corpus-wide search or not (see
test_corpus_fallback_still_rejects_a_quote_fabricated_on_every_page in tests/test_evidence.py).
The accepted cost: claim.source_url is left exactly as the model wrote it, so an accepted claim's
source_url can now be imprecise about which specific page the quote lives on -- the same
traceability tradeoff check_conflicting_claim() already makes for conflicting claims, just applied
here as a fallback rather than the normal path. `check_claim()`'s new `corpus_texts` parameter
defaults to None, so every pre-existing single-page call and test is completely unaffected;
wi/extract/pipeline.py is the only real caller, and now passes every crawled page's text
alongside the claim's own cited page.

`pricing.revenue_model` contact-sales guard (B-03, added 2026-09-27): check_claim() deliberately
skips value_supported_by_quote() for `inferred` claims -- see that function's own docstring --
because a real, legitimate inference's value routinely shares NO significant words with its
quote at all (rule 8's own worked example in wi/extract/prompt.py infers "software as a
service" from "Sign in from your laptop, tablet, or phone", zero word overlap, and that is
correct behaviour, not a bug). Applying the general word-overlap check to every inferred claim
would break exactly the mechanism inference exists for. But this created a real, previously
undiagnosed gap for one specific, testable pattern (Final PRD / B-03): a page whose only
pricing-adjacent text is a "contact sales"-style call to action (no self-serve checkout, no
recurring-billing language at all) gives the model a REAL quote to cite -- quote_in_page passes
-- while the model separately concludes "subscription" for pricing.revenue_model, a conclusion
that quote does not support in either direction: "contact sales" is evidence about *how you buy*
(a sales motion), not about *what you're buying* (one-time vs. recurring). Live evidence this is
a real failure mode, not a hypothetical: pricing.revenue_model over-inference was observed on
darwinbox.com, bajajauto.com and thoughtbot.com dev-set runs earlier this week (see
PROGRESS.md's 2026-09-27 sections). This is fixed with one narrowly-scoped check --
`_revenue_model_inference_contradicts_evidence()` below -- rather than loosening the general
inferred-claim exemption: it fires ONLY when field == "pricing.revenue_model", status ==
inferred, the quote matches a small, explicit list of contact-sales/custom-quote phrases, AND
the value asserts a subscription/recurring model. Every other inferred claim on every other
field (including pricing.sales_motion's own "sales-led" inference from the same "Contact sales"
quote, which B-02 explicitly wants to keep working) is completely unaffected.

Partial credit for a multi-value claim, B-40 (added 2026-09-27): check_claim() above is
deliberately all-or-nothing -- the moment ANY one value/evidence pair in a list claim fails,
wi/extract/pipeline.py has always discarded the WHOLE claim to not_found, including every other
item that verified just fine. Found live on the Week 4 held-out run: temenos.com's
traction.partnerships correctly named three real partners (Accenture, BCT, Capgemini) with three
individually real quotes, but BCT's specific quote didn't word-support the value closely enough --
one bad pair sank two good ones. The same shape hit thoughtworks.com and plaid.com's
customers.industries, where the model gave far more values (11, 4) than evidence entries (2 each) --
a schema-level version of the same problem, caught by wi/schemas/claim.py's length-match validator
before check_claim() even runs, with the same all-or-nothing result.

Uttam's explicit decision, given the tradeoff against the PRD's "a wrong claim is worse than an
honest not_found" caution (rule 4): keep the verified items and drop only the failing ones, rather
than leaving the current conservative behaviour in place or asking the model to retry the whole
field. This does not loosen what counts as verified -- every SURVIVING item still independently
passes the exact same quote_in_page + value_supported_by_quote checks check_claim() already runs,
one item at a time; nothing new is trusted, only more of what was already trusted is kept.
`check_claim_items()` below is the per-item counterpart to check_claim(): where check_claim()
collapses to one True/False for the whole claim, check_claim_items() returns one (ok, reason,
evidence_to_keep) per value entry so wi/extract/pipeline.py can rebuild a smaller, fully-verified
Claim instead of discarding it whole. It returns None (nothing to partially filter) for a
single-string value, and for the one remaining all-or-nothing edge case this doesn't reach: a
single-line `evidence` string paired with a list `value` (no per-item boundary exists in one
undifferentiated quote to split credit across, so this shape is intentionally left to
check_claim()'s existing whole-claim behaviour, same as always). Does not touch the
schema-level length-mismatch case above (thoughtworks/plaid) -- that claim never becomes a valid
Claim object at all, so there is nothing for check_claim_items() to run against; flagged as a
separate, not-yet-decided follow-up, not covered by this fix.

Multi-fragment evidence for a single-STRING value, B-42 (added 2026-09-27): the multi-line
`evidence` string mechanism above (the "Basecamp pricing-format false negative") only ever
applied when `claim.value` is a list -- a single-string value with a multi-line `evidence`
string fell through to the plain path below, which requires the WHOLE multi-line block
(embedded newlines and all) to be one literal quote in the page text. That can essentially never
match, so a single-string field had no legal way to be backed by more than one real quoted
fragment at all. Confirmed live on sarvam.ai/about-us while root-causing `customers.segments`'
held-out failures: the real page states "...applications that can be put to work by
enterprises, governments and developers" in one sentence, but the model's rejected evidence was
"We are building for enterprises, governments and developers." -- a plausible-sounding
PARAPHRASE it composed instead of quoting the real sentence, exactly the rule 7 violation this
whole evidence-integrity design exists to catch (and this specific case, being a genuine
fabrication rather than a scattered-facts problem, is separately addressed by prompt rule 15's
paraphrase-avoidance guidance, not by this mechanism change). But the ORIGINAL diagnosis this
field was flagged for is a different, genuine shape: several segments named in truly separate
parts of a page (a "for startups" mention here, a "for enterprises" mention there), where no
single sentence covers them together -- the same page-layout reality rule 6's array-evidence
mechanism already exists to handle for list-valued fields, just never extended to single-string
ones. Fixed by dropping the `isinstance(claim.value, list)` restriction on the multi-line-string
branch: it now runs whenever `claim.evidence` is a string with more than one line, regardless of
whether `claim.value` is a list or a plain string, and checks each of `_items_from_value(value)`'s
comma-split items (already the exact heuristic `value_supported_by_quote()` uses to interpret a
compound string) against ANY of the real quoted lines, rather than requiring one quote to
cover the item. This is not a relaxation of what counts as evidence -- every line used to
support an item must still independently be real page text (via the same `_quote_found()` used
everywhere) and must still independently support that item; a fabricated line, or a real line
that doesn't actually support the item it's paired against, still fails exactly as before. A
single-line `evidence` string, for either value shape, is completely unaffected and still goes
through the plain single-quote path. `EXTRACTION_LOGIC_VERSION` bumped 8 -> 9 (deterministic
checking logic changed).

Two more bugs (B-44, 2026-09-27), both found on the very first live held-out confirmation run of
B-42/B-43 -- the address text those fixes newly surface reached this checker for the first time
and immediately exposed gaps that had no way to show up before. (1) `_split_items()`'s
comma-only split shredded innovaccer.com's real, four-location headquarters value (four whole
addresses joined by semicolons, each with its own internal commas) into meaningless
cross-address fragments like "CA 94105; Tower 3" that matched no real evidence line, wrongly
rejecting a fully genuine claim. Fixed by splitting on a semicolon first, when one is present,
and never re-splitting the resulting item by comma. (2) `value_supported_by_quote()`'s per-item
word-overlap check rejected razorpay.com's real, verbatim-quoted address because the model's
value said "Bengaluru" (the city's current official name) while the page's own address block
still says "Bangalore" (the pre-2014 name) -- a real, common renaming, not a hallucination.
Fixed with a small, explicit alias table (`_PLACE_NAME_ALIASES`) for India's own most common
colonial-era renamings, applied to both the value's significant words and the quote text so
either spelling on either side compares equal -- deliberately narrow, like B-38's
currency-symbol list, rather than a general fuzzy place-name heuristic that could paper over a
genuinely wrong city. Neither fix is a relaxation of what counts as evidence: a fabricated
address, or a genuinely different (non-aliased) city, still fails exactly as before.
`EXTRACTION_LOGIC_VERSION` bumped 9 -> 10.

products.names bare-label guard (added 2026-10-02): check_claim()/check_claim_items() above
already run value_supported_by_quote() against every list item, but that check is itself
satisfied trivially when a model quotes the value right back as its own evidence -- "Loom
for Sales" supports "Loom for Sales" by definition, 100% word overlap, with nothing shown
about whether the page actually presents it as a genuine product rather than a card/menu
label. Found live on loom.com: 3 of 4 independent --no-cache reps (2026-10-02) returned
products.names = ["Loom for Enterprise", "Loom for Sales", "Loom for Engineering", "Loom for
Support", "Loom for Design"] with evidence identical to value for every item, source_url the
/use-case hub page listing all five as cards linking to their own sub-pages.
wi/extract/prompt.py's rule 18 (plus a second worked example added the same day, modelling
this exact hub-page pattern) was written specifically to stop this via prompt-text
classification, but across both attempts and 4 independent reps the model's behaviour never
changed -- this fix moves the check to the deterministic layer instead, the same way this
project has already resolved every other "a model keeps citing a technically-real but
evidentially-empty quote" pattern (B-03, B-38 above).
`_products_name_evidence_is_bare_self_repeat()` below rejects a products.names list item
whose evidence is nothing but the value string repeated back verbatim (case/whitespace-
insensitive); check_claim() fails the whole claim on any such item, and check_claim_items()
gives the same per-item verdict so B-40's partial-credit mechanism keeps only genuinely-
evidenced items instead of discarding good ones alongside bad. Scoped to products.names only
-- every other list field keeps its existing behaviour, since a bare repeated label is
specifically common (and specifically insufficient) for this one field's "menu/card title
vs. genuine product" distinction; a real sentence of evidence, even a short one, still
passes exactly as before. `EXTRACTION_LOGIC_VERSION` bumped 11 -> 12.

company_identity.headquarters country-name guard, B-53 (added 2026-10-03): flagged as an open
gap at least twice before this fix -- B-44's own docstring names it live on razorpay.com, and
B-47's entry in tests/BEHAVIOURS.md explicitly lists "the B-44-disclosed country-name gap
(confirmed still live on razorpay.com's headquarters field)" as a known, not-yet-fixed issue.
Distinct from the question B-43 already settled (tests/BEHAVIOURS.md's B-43 entry): there, the
model was recalling an entire address from outside knowledge because NO real address text
existed on the page at all (trafilatura had stripped it) -- rejecting that was correct, exactly
as rule 4 intends, since nothing on the page supported any of it. By the time a claim reaches
here today, B-43 (page cleaning) and B-44 (the Bangalore/Bengaluru alias) have already done their
job: the real address block IS on the page and IS correctly quoted, with city/state/postal-code
all genuinely matching. The one remaining mismatch is the country name itself ("India"), which
an Indian company's own address block almost never spells out on its own site -- not a
hallucinated fact, but a near-certain, almost mechanical inference from an unambiguous
city/state/postal-code combination (the same way "USA" is implied by "Austin, TX 78701").
`_HEADQUARTERS_COUNTRY_NAMES` is a small, explicit, bounded set (countries are a closed list,
unlike a general fuzzy-place heuristic) used only for `company_identity.headquarters`.
Deliberately made fail-SAFE rather than a blanket exemption: a claimed country is accepted as
"supported although unquoted" only when the quote asserts no OTHER recognised country --
`_quote_asserts_a_different_country()` -- so a value that genuinely gets the country wrong (a
real hallucination, not an omission) still fails exactly as before. Bare "us"/"u.s." are
deliberately excluded from the set (too easily a false match inside ordinary prose, e.g. the
pronoun "us" or "focus"); "usa"/"united states"/"uk"/"united kingdom"/"uae"/"united arab
emirates" are unambiguous enough to keep. `EXTRACTION_LOGIC_VERSION` bumped 12 -> 13.

Two pricing-quote fixes found on the labelled dev set, B-56 and B-57 (added 2026-10-04):

B-56 -- quote_in_page() ignores a joining comma or semicolon. Found live on simplestores.in: the
real pricing text reads "Business" and "From 1,499 / month" on separate lines, and the model
joined them as "Business, 1,499/month". That differs from the page only by the comma the model
added, yet was rejected as "quote not found in page text" (the model's cited page was a thin
stub, so the corpus-wide fallback's stricter 0.97 threshold applied and 0.95 missed). The new
check compares both sides with a separator comma or semicolon removed. A comma BETWEEN digits
(1,499) is never touched, so "14,99" can never be made to match "1,499"; every word and number
must still appear, in order and adjacent, on a real page.

B-57 -- the revenue-model "has a pricing signal" guard now recognises per-period price forms
("/mo", "/month", "/yr", "/year", "/seat", "/user"). Found live on typeform.com, where the real
quote "379USD/mo after 14 days" was rejected as having no pricing signal, because the guard
deliberately ignores bare currency CODES (B-38: a market-cap fact such as "INR one trillion"
must not count) and "/mo" was not in its list. A per-period suffix is a billing term whatever
the currency is written as, and never occurs in a valuation fact. `EXTRACTION_LOGIC_VERSION`
bumped 13 -> 14.
"""
from __future__ import annotations

import re
import unicodedata
from typing import List, Optional, Tuple, Union

from rapidfuzz import fuzz

from wi.schemas.claim import Claim, Status

FUZZY_THRESHOLD = 0.90
ITEM_OVERLAP_THRESHOLD = 0.6

# Stricter than FUZZY_THRESHOLD, used ONLY for the corpus-wide fallback in _quote_found() below
# (B-36). Found live while writing this fix's own test suite: an existing test
# (test_rejected_claim_records_the_source_url_the_model_claimed) started failing once the
# fallback searched real crawled page text -- "Example Co" scored fuzz.partial_ratio == 90.0
# against unrelated text ("Example\nNothing relevant here.", from that page's own title/body),
# a pure coincidence of two short strings both starting with "example ". That is exactly
# FUZZY_THRESHOLD's cutoff: fine for the single page the model actually cited (a near-miss there
# is almost always genuine OCR/whitespace noise around a real quote), but broadening the search
# to every crawled page multiplies how much unrelated text a short quote gets fuzz-matched
# against, and with it the odds of a coincidental hit like this one. Every real match this fix
# needs to find (the live "CloseKnit Health" case, and every corpus-fallback test in
# tests/test_evidence.py) scores 100 -- an exact or near-exact substring -- so this stricter
# threshold costs nothing on genuine matches while closing off the coincidental ones the wider
# search surfaces.
CORPUS_FALLBACK_FUZZY_THRESHOLD = 0.97

_STOPWORDS = {"the", "a", "an", "of", "for", "and", "or", "to", "in", "on", "with"}


_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "thirteen": "13", "fourteen": "14", "fifteen": "15", "twenty": "20", "thirty": "30",
    "forty": "40", "sixty": "60", "ninety": "90",
}
_NUMBER_WORD_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b")


def normalise(text: str) -> str:
    """Lowercase, unify quotes and dashes, collapse whitespace, and read a spelled-out number as
    its digits (B-64, 2026-10-06: "Seven-day trial" on the page and "7-day trial" in the claim are
    the same fact; the numbers check below rejected simplestores.in's real 7-day trial because only
    one side was spelled in digits). It is applied to both sides of every comparison, so it can only
    ever make two spellings of one number equal."""
    text = unicodedata.normalize("NFKC", text)
    text = (text.replace("’", "'").replace("‘", "'")
                .replace("“", '"').replace("”", '"')
                .replace("–", "-").replace("—", "-"))
    text = re.sub(r"\s+", " ", text).strip().lower()
    return _NUMBER_WORD_RE.sub(lambda m: _NUMBER_WORDS[m.group(1)], text)


# B-56: a comma that is not followed by a digit (so never the one inside 1,499), or a semicolon.
_JOINING_SEPARATOR = re.compile(r",(?!\d)|;")


def _without_joining_separators(text: str) -> str:
    return re.sub(r"\s+", " ", _JOINING_SEPARATOR.sub(" ", text)).strip()


def quote_in_page(quote: str, page_text: str, threshold: float = FUZZY_THRESHOLD) -> bool:
    q, page = normalise(quote), normalise(page_text)
    if not q or not page:
        return False
    if q in page:
        return True
    # B-56: same words and numbers, in order and adjacent, apart from a joining comma/semicolon.
    if _without_joining_separators(q) in _without_joining_separators(page):
        return True
    return fuzz.partial_ratio(q, page) / 100.0 >= threshold


def _key_terms(value: str) -> list:
    """Numbers (with currency symbols stripped) are the terms most likely to be hallucinated."""
    v = normalise(value).replace(",", "")
    return re.findall(r"\d+(?:\.\d+)?", v)


def _split_items(value: str) -> list:
    """Split a value like "Yatra, Mahindra Logistics and TVS Motor" into
    ["Yatra", "Mahindra Logistics", "TVS Motor"]. Splits only on a comma that is followed by a
    letter (after optional whitespace) -- never inside a number -- so "Growth INR 1,499/month"
    stays one item instead of breaking into "Growth INR 1" and "499/month".

    Semicolon fix (2026-09-27, B-44): a semicolon means the author already needed a delimiter
    ABOVE comma, because each item has its OWN internal commas -- the common case is several
    full postal addresses joined together (e.g. "Suite 2900, San Francisco, CA 94105; Tower 3,
    Candor Techspace Sector 62, 201309, India"). Found live on innovaccer.com's
    company_identity.headquarters: B-42's multi-fragment evidence mechanism correctly gave four
    real, newline-separated addresses as evidence, but this function's comma-only split shredded
    the semicolon-joined VALUE at every comma regardless of which address it belonged to,
    producing meaningless cross-address fragments like "CA 94105; Tower 3" that match no real
    evidence line -- rejecting a fully genuine four-location claim. When a semicolon is present,
    split on it instead and never re-split each item by comma; a value with no semicolon is
    unaffected and keeps the original comma-splitting behaviour exactly as before."""
    if ";" in value:
        return [item.strip() for item in value.split(";") if item.strip()]
    v = re.sub(r",?\s+and\s+", ", ", value, flags=re.IGNORECASE)
    items = re.split(r",\s*(?=[A-Za-z])", v)
    return [item.strip() for item in items if item.strip()]


# B-44 (2026-09-27): a small, explicit set of places with two real, still-current names --
# found live on razorpay.com, where the model's value said "Bengaluru" (the city's official
# name since 2014) while the page's own address block, quoted verbatim as evidence, still says
# "Bangalore" (the pre-2014 name, still in wide real-world use). value_supported_by_quote()'s
# word-overlap check has no notion that these name the same place, so "bengaluru" scores 0/1
# overlap against a quote that only contains "bangalore" and the whole claim is wrongly
# rejected, even though the quote genuinely supports the value. Deliberately narrow and
# explicit -- like B-38's currency-symbol list or rule 14's cue vocabulary -- rather than a
# general fuzzy-place-name heuristic, which risks papering over a genuinely wrong city. Limited
# to India's own most common colonial-era renamings, the ones actually likely to appear on a
# real company site.
# Keyed by current name, valued by the older name it replaced -- but canonicalisation below
# treats both directions equally (a value or a quote could plausibly use either form), so
# _PLACE_NAME_TO_MODERN (built from this) is what actually gets applied.
_PLACE_NAME_ALIASES = {
    "bengaluru": "bangalore",
    "mumbai": "bombay",
    "chennai": "madras",
    "kolkata": "calcutta",
    "pune": "poona",
    "thiruvananthapuram": "trivandrum",
    "kochi": "cochin",
    "mysuru": "mysore",
    "vadodara": "baroda",
}
# Maps the OLD name to the modern one; a word already in its modern form is simply not a key
# here and passes through _canonicalise_places() unchanged -- either spelling ends up as the
# same canonical (modern) token.
_PLACE_NAME_TO_MODERN = {old: modern for modern, old in _PLACE_NAME_ALIASES.items()}
_PLACE_NAME_PATTERN = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in set(_PLACE_NAME_ALIASES) | set(_PLACE_NAME_TO_MODERN)) + r")\b"
)


def _canonicalise_places(word: str) -> str:
    """Maps either name of a renamed place -- current or colonial-era -- to the same single
    canonical (modern) form, so a value using one and a quote using the other compare equal
    instead of scoring a false overlap miss. See _PLACE_NAME_ALIASES above."""
    return _PLACE_NAME_TO_MODERN.get(word, word)


def _canonicalise_places_text(text: str) -> str:
    """Same canonicalisation as _canonicalise_places(), applied to whole-word occurrences inside
    a larger string (the quote) rather than one already-split word (the value's significant
    words) -- so whichever name the QUOTE happens to use also normalises to the same form.
    Word-boundary matched, so this never touches an unrelated word merely containing one of
    these place names as a substring."""
    return _PLACE_NAME_PATTERN.sub(lambda m: _canonicalise_places(m.group(0)), text)


# B-53 (2026-10-03): see the module docstring's own B-53 section for the full rationale --
# scoped to company_identity.headquarters only. A deliberately bounded, explicit set (common
# English country names plus a few unambiguous abbreviations) rather than an open-ended
# heuristic; bare "us"/"u.s." are left out on purpose (see docstring) because they collide with
# ordinary English words/pronouns too easily for a safe substring/word match.
_HEADQUARTERS_COUNTRY_NAMES = {
    "afghanistan", "albania", "algeria", "andorra", "angola", "antigua and barbuda",
    "argentina", "armenia", "australia", "austria", "azerbaijan", "bahamas", "bahrain",
    "bangladesh", "barbados", "belarus", "belgium", "belize", "benin", "bhutan", "bolivia",
    "bosnia", "botswana", "brazil", "brunei", "bulgaria", "burkina faso", "burundi",
    "cambodia", "cameroon", "canada", "cape verde", "central african republic", "chad",
    "chile", "china", "colombia", "comoros", "congo", "costa rica", "croatia", "cuba",
    "cyprus", "czechia", "czech republic", "denmark", "djibouti", "dominica",
    "dominican republic", "ecuador", "egypt", "el salvador", "equatorial guinea", "eritrea",
    "estonia", "eswatini", "ethiopia", "fiji", "finland", "france", "gabon", "gambia",
    "georgia", "germany", "ghana", "greece", "grenada", "guatemala", "guinea", "guyana",
    "haiti", "honduras", "hong kong", "hungary", "iceland", "india", "indonesia", "iran",
    "iraq", "ireland", "israel", "italy", "ivory coast", "jamaica", "japan", "jordan",
    "kazakhstan", "kenya", "kiribati", "kuwait", "kyrgyzstan", "laos", "latvia", "lebanon",
    "lesotho", "liberia", "libya", "liechtenstein", "lithuania", "luxembourg", "macau",
    "madagascar", "malawi", "malaysia", "maldives", "mali", "malta", "marshall islands",
    "mauritania", "mauritius", "mexico", "moldova", "monaco", "mongolia", "montenegro",
    "morocco", "mozambique", "myanmar", "namibia", "nauru", "nepal", "netherlands",
    "new zealand", "nicaragua", "niger", "nigeria", "north korea", "norway", "oman",
    "pakistan", "palau", "panama", "papua new guinea", "paraguay", "peru", "philippines",
    "poland", "portugal", "puerto rico", "qatar", "romania", "russia", "rwanda",
    "saint kitts and nevis", "saint lucia", "saint vincent and the grenadines", "samoa",
    "saudi arabia", "senegal", "serbia", "seychelles", "sierra leone", "singapore",
    "slovakia", "slovenia", "solomon islands", "somalia", "south africa", "south korea",
    "spain", "sri lanka", "sudan", "suriname", "sweden", "switzerland", "syria", "taiwan",
    "tajikistan", "tanzania", "thailand", "togo", "tonga", "trinidad and tobago", "tunisia",
    "turkey", "turkmenistan", "tuvalu", "uae", "uganda", "uk", "ukraine",
    "united arab emirates", "united kingdom", "united states", "united states of america",
    "uruguay", "usa", "uzbekistan", "vanuatu", "venezuela", "vietnam", "yemen", "zambia",
    "zimbabwe",
}


def _quote_asserts_a_different_country(claimed: str, quote_norm: str) -> bool:
    """True when `quote_norm` names some OTHER recognised country than `claimed` -- a genuine
    contradiction (a real, if rare, hallucinated country), not a mere omission. Word-boundary
    matched for the same reason _canonicalise_places_text() is: a short name must not match
    inside an unrelated longer word. See the module docstring's B-53 section."""
    for name in _HEADQUARTERS_COUNTRY_NAMES:
        if name == claimed:
            continue
        if re.search(rf"\b{re.escape(name)}\b", quote_norm):
            return True
    return False


def _significant_words(text: str) -> list:
    """Words worth checking for overlap: drop stopwords and very short tokens (e.g. "PR", "to")
    that would make the overlap check either trivial or unfairly strict. Renamed places are
    canonicalised (B-44) so a real synonym doesn't score as a hallucination-shaped miss."""
    words = re.findall(r"[a-z0-9]+", normalise(text))
    return [_canonicalise_places(w) for w in words if w not in _STOPWORDS and len(w) > 2]


def _items_from_value(value: Union[str, List[str], None]) -> list:
    """A list value is already split into items -- no guessing needed. A string value falls
    back to the comma-splitting heuristic (still useful for single-value fields, and for a
    model that returns a comma list as a string despite being asked for an array)."""
    if isinstance(value, list):
        return [item.strip() for item in value if item and item.strip()]
    return _split_items(value or "")


def value_supported_by_quote(
    value: Union[str, List[str], None], quote: str, field: Optional[str] = None
) -> bool:
    q_nospace_commas = normalise(quote).replace(",", "")
    # B-44: canonicalise renamed-place spellings in the quote too, so it matches a value's
    # significant words (also canonicalised, in _significant_words) regardless of which of the
    # two real names either side happens to use.
    quote_norm = _canonicalise_places_text(normalise(quote))

    for item in _items_from_value(value):
        if not all(term in q_nospace_commas for term in _key_terms(item)):
            return False

        # B-53: a company_identity.headquarters item that's a recognised country name, not
        # itself quoted, but not CONTRADICTED by some other country the quote does name, is an
        # omission (near-certain inference from city/state/postal-code) rather than a
        # hallucination -- see the module docstring's B-53 section.
        item_norm = normalise(item)
        if (field == "company_identity.headquarters"
                and item_norm in _HEADQUARTERS_COUNTRY_NAMES
                and not re.search(rf"\b{re.escape(item_norm)}\b", quote_norm)
                and not _quote_asserts_a_different_country(item_norm, quote_norm)):
            continue

        sig = _significant_words(item)
        if not sig:
            continue  # nothing non-numeric to check (e.g. a bare number, or "Yes")
        hits = sum(1 for w in sig if w in quote_norm)
        if hits / len(sig) < ITEM_OVERLAP_THRESHOLD:
            return False
    return True


# B-03 (2026-09-27): phrases that indicate a "talk to us to buy" sales motion with no self-serve
# checkout described -- real signal about HOW a sale happens, never about whether the resulting
# pricing is one-time, usage-based, or recurring. Deliberately small and explicit (matched
# against `normalise()`d text, so case/punctuation-insensitive) rather than a broad heuristic --
# a false positive here would wrongly block a genuine subscription inference that happens to
# also mention a sales contact somewhere, so this only fires on phrases that are themselves
# strong, unambiguous "contact us" calls to action.
_CONTACT_SALES_SIGNALS = (
    "contact sales", "contact us for pricing", "contact our sales", "talk to sales",
    "talk to our sales team", "speak to our sales team", "speak with sales",
    "request a quote", "request a demo", "get a quote", "get a custom quote",
    "book a demo", "schedule a demo", "get in touch for pricing",
)

_SUBSCRIPTION_TERMS = re.compile(r"subscription|recurring")


def _revenue_model_inference_contradicts_evidence(value: Optional[str], quote: str) -> bool:
    """True when an inferred pricing.revenue_model value asserts a subscription/recurring model
    but the quote it's paired with is only a contact-sales/custom-quote call to action -- see
    the module docstring's B-03 section for why this needs its own narrow check rather than
    running the general value_supported_by_quote() word-overlap check on inferred claims."""
    quote_norm = normalise(quote)
    if not any(signal in quote_norm for signal in _CONTACT_SALES_SIGNALS):
        return False
    return bool(_SUBSCRIPTION_TERMS.search(normalise(value or "")))


# B-38 (2026-09-27): terms that plausibly relate to how a company charges for its product --
# currency symbols (never bare currency CODES like "INR"/"USD", which also show up in unrelated
# valuation/market-cap facts, e.g. bajajauto.com's real "market capitalisation of INR one
# trillion" -- exactly the kind of fact this guard exists to keep from passing) plus words about
# pricing, billing, contracts, and sale/purchase transactions. Deliberately generous rather than
# exhaustive: a false positive here (the guard finds a "signal" in an unrelated sentence) only
# means an inference is allowed to proceed to its normal check, same as any other inferred claim
# -- the risk this guard is scoped to catch is quotes with NO connection to revenue at all.
_REVENUE_SIGNAL_TERMS = re.compile(
    r"[$₹€£]|pric(?:e|ing)|fee|cost|invoice|bill|charge|plan|purchase|buy|sale|sold|"
    r"consumption|usage[- ]based|metered|"
    r"revenue|contract|licen[cs]e|pay|recurring|one-time|per month|per user|per order|"
    r"per transaction|commission|royalty|rent|lease|discount|trial|freemium|quote|checkout|"
    r"subscription|/ ?(?:mo|month|yr|year|seat|user)(?![a-z])"
)


def _revenue_model_inference_lacks_pricing_signal(quote: str) -> bool:
    """True when an inferred pricing.revenue_model claim's quote contains no term that even
    plausibly relates to pricing, billing, or how the company charges for its product -- see the
    module docstring's B-38 section. Distinct from _revenue_model_inference_contradicts_evidence
    above (which catches one specific WRONG conclusion from a specific evidence shape); this
    catches ANY conclusion, of any kind, drawn from evidence that never touches revenue at all."""
    return not _REVENUE_SIGNAL_TERMS.search(normalise(quote))


def _products_name_evidence_is_bare_self_repeat(value_item: str, quote: str) -> bool:
    """products.names bare-label guard (added 2026-10-02): a quote that is nothing but the
    value repeated back verbatim never demonstrates the candidate is a genuine named product
    rather than a menu/card label -- it only proves the string exists on the page, which
    quote_in_page() already checks separately. See the module docstring for the live
    loom.com evidence this fixes. Scoped to products.names only -- other list fields keep
    their existing behaviour (checked by the field guard at each call site, not here)."""
    return normalise(value_item) == normalise(quote)


def _quote_found(quote: str, page_text: str, corpus_texts: Optional[List[str]]) -> bool:
    """The claim's own cited page first, at the normal FUZZY_THRESHOLD; only if that misses, and
    a corpus was given, fall back to every other crawled page at the stricter
    CORPUS_FALLBACK_FUZZY_THRESHOLD -- see the module docstring's "CloseKnit Health" section and
    that constant's own docstring for why the fallback needs a higher bar. A quote found nowhere
    at all, cited page or corpus, is exactly as fabricated as before."""
    if quote_in_page(quote, page_text):
        return True
    if corpus_texts:
        return any(
            quote_in_page(quote, text, threshold=CORPUS_FALLBACK_FUZZY_THRESHOLD)
            for text in corpus_texts
        )
    return False


def _evidence_fragments(
    evidence: str, page_text: str, corpus_texts: Optional[List[str]]
) -> List[str]:
    """The separate quotes inside a single evidence string: its non-empty lines, or -- when it is
    one line holding several real quotes joined by "; " that is NOT itself a real quote -- those
    pieces (B-64, 2026-10-06). The model often joins cues with a semicolon instead of a newline,
    e.g. 'Get started for free; Talk to sales' for two separate buttons; strict whole-string
    matching rejected Calendly's sales_motion and revenue_model for that alone in a live run. A
    one-line string that really appears on the page is left whole, so a genuine quote that happens
    to contain a semicolon is unaffected, and every piece must be real page text -- one made-up piece sends the whole string back to
    the strict whole-string check, which fails it."""
    lines = [line.strip() for line in evidence.split("\n") if line.strip()]
    if len(lines) == 1 and ";" in lines[0] and not _quote_found(lines[0], page_text, corpus_texts):
        pieces = [p.strip() for p in lines[0].split(";") if p.strip()]
        # Every piece must be real: the whole string stays in the ledger as the claim's evidence,
        # so a made-up piece next to a real one must not slip through.
        if len(pieces) > 1 and all(_quote_found(p, page_text, corpus_texts) for p in pieces):
            return pieces
    return lines


def check_claim(
    claim: Claim, page_text: str, corpus_texts: Optional[List[str]] = None
) -> Tuple[bool, str]:
    """Returns (ok, reason). Only extracted claims need the value-support check;
    inferred claims are interpretations, so only the quote check applies.

    When `claim.evidence` is a list (decided 2026-09-23), it's checked pairwise against
    `claim.value` instead of as one combined quote -- see the module docstring for the
    basecamp.com pricing bug this exists to fix. Claim's own validator already guarantees
    `len(evidence) == len(value)` whenever evidence is a list, so the zip below is safe.

    `conflicting` is exempted below because it isn't checkable against a single fixed
    `page_text` -- its two values legitimately come from two different pages. It is not left
    unchecked, though: see check_conflicting_claim() below, which wi/extract/pipeline.py calls
    for conflicting claims instead of this function.

    `corpus_texts` (B-36, added 2026-09-27): optional list of every crawled page's text, used
    ONLY as a fallback when a quote isn't found on the claim's own cited `page_text` -- see the
    module docstring's "CloseKnit Health" section. Every quote_in_page() call below goes through
    `_quote_found()` so this fallback applies uniformly to the pairwise-list, multi-line-string
    and plain single-quote shapes alike. Defaults to None, which reproduces the old single-page-
    only behaviour exactly (every pre-existing call site and test)."""
    if claim.status in (Status.not_found, Status.conflicting):
        return True, "no quote check needed"

    if isinstance(claim.evidence, list):
        for value_item, quote in zip(claim.value, claim.evidence):
            if not _quote_found(quote, page_text, corpus_texts):
                return False, f"quote not found in page text for {value_item!r}: {quote!r}"
            if claim.status == Status.extracted and not value_supported_by_quote(value_item, quote, field=claim.field):
                return False, f"quote does not support the value {value_item!r}: {quote!r}"
            if (claim.status == Status.extracted and claim.field == "products.names"
                    and _products_name_evidence_is_bare_self_repeat(value_item, quote)):
                return False, (
                    f"evidence for {value_item!r} is nothing but the value repeated back "
                    f"verbatim -- it does not show this is a genuine named product rather "
                    f"than a menu/card label: {quote!r}"
                )
            if (claim.status == Status.inferred and claim.field == "pricing.revenue_model"
                    and _revenue_model_inference_contradicts_evidence(value_item, quote)):
                return False, (
                    f"'contact sales'-style evidence does not support inferring a "
                    f"subscription/recurring revenue model: {quote!r}"
                )
            if (claim.status == Status.inferred and claim.field == "pricing.revenue_model"
                    and _revenue_model_inference_lacks_pricing_signal(quote)):
                return False, (
                    f"quote has no pricing/billing signal to support inferring any revenue "
                    f"model: {quote!r}"
                )
        return True, "ok"

    # Basecamp pricing-format false negative (2026-09-27) -- see the module docstring's
    # "multi-LINE evidence string" section -- generalised to single-string values too by B-42
    # (2026-09-27, see the module docstring's own section): only engages when there's more than
    # one line to search across; a genuinely single-line evidence string falls through to the
    # plain path below unchanged, for either value shape.
    if isinstance(claim.evidence, str):
        fragments = _evidence_fragments(claim.evidence, page_text, corpus_texts)
        if len(fragments) > 1:
            for value_item in _items_from_value(claim.value):
                supported = any(
                    _quote_found(fragment, page_text, corpus_texts)
                    and (claim.status != Status.extracted
                         or value_supported_by_quote(value_item, fragment, field=claim.field))
                    for fragment in fragments
                )
                if not supported:
                    return False, (
                        f"no single line of the evidence is a real, supporting quote for "
                        f"{value_item!r} (evidence: {claim.evidence!r})"
                    )
            return True, "ok"

    if not _quote_found(claim.evidence or "", page_text, corpus_texts):
        return False, "quote not found in page text"

    if claim.status == Status.extracted and not value_supported_by_quote(claim.value or "", claim.evidence or "", field=claim.field):
        return False, "quote does not support the value"

    if (claim.status == Status.inferred and claim.field == "pricing.revenue_model"
            and _revenue_model_inference_contradicts_evidence(claim.value, claim.evidence or "")):
        return False, (
            "'contact sales'-style evidence does not support inferring a subscription/recurring "
            "revenue model"
        )

    if (claim.status == Status.inferred and claim.field == "pricing.revenue_model"
            and _revenue_model_inference_lacks_pricing_signal(claim.evidence or "")):
        return False, (
            "quote has no pricing/billing signal to support inferring any revenue model"
        )

    return True, "ok"


def _item_passes(claim: Claim, value_item: str, quote: str,
                 page_text: str, corpus_texts: Optional[List[str]]) -> bool:
    """True when `quote` is real page text, supports `value_item`, and (for products.names) is not
    the value merely repeated back -- the same three per-item tests check_claim() applies to an
    evidence list, in one place so realign_list_evidence() below cannot drift from them."""
    if not _quote_found(quote, page_text, corpus_texts):
        return False
    if not value_supported_by_quote(value_item, quote, field=claim.field):
        return False
    if (claim.field == "products.names"
            and _products_name_evidence_is_bare_self_repeat(value_item, quote)):
        return False
    return True


def realign_list_evidence(
    claim: Claim, page_text: str, corpus_texts: Optional[List[str]] = None
) -> Tuple[Claim, int]:
    """B-63 (2026-10-06): re-pairs an extracted list claim's evidence quotes with the values they
    actually support. Returns (claim, number_of_quotes_moved); the claim is returned unchanged when
    nothing needed moving.

    Why: found by probing real rejections on the 5 dev sites. On loom.com's customers.industries the
    model answered values ["Financial Services", "Technology", "Product Design", "Customer
    Support"] with evidence ["Financial Services and Technology", "Product Design", ...] -- the
    right quotes, but the list is shifted one place after the model merged two values into one
    quote. check_claim() pairs strictly by position, so "Technology" was tested against "Product
    Design" and rejected although a real quote for it was sitting one slot earlier.

    Rule: an item whose own positional quote fails is given another quote FROM THE SAME evidence
    list, but only if that quote passes every per-item test (real page text, supports the value,
    not a bare self-repeat). No quote is invented, no new text is accepted, nothing outside this
    claim's own evidence list is consulted, and an item with no passing quote anywhere stays failed.
    Only extracted claims with a value list and an equal-length evidence list are touched."""
    if (claim.status != Status.extracted
            or not isinstance(claim.value, list) or not isinstance(claim.evidence, list)
            or len(claim.value) != len(claim.evidence)):
        return claim, 0
    new_evidence = list(claim.evidence)
    moved = 0
    # B-67 (2026-10-06): for products.names, a quote that is just ANOTHER item's name repeated back
    # (a menu/card label) is not evidence for this item either. Found on notion.com: "Notion AI"
    # (whose own quote was a bare self-repeat) was re-paired with the bare label "Notion Calendar"
    # because the two share the word "Notion", so a kept claim cited the wrong product as proof.
    bare_labels = ({normalise(v) for v in claim.value}
                   if claim.field == "products.names" else set())
    for i, value_item in enumerate(claim.value):
        if _item_passes(claim, value_item, claim.evidence[i], page_text, corpus_texts):
            continue
        alt = next(
            (q for j, q in enumerate(claim.evidence)
             if j != i and normalise(q) not in bare_labels
             and _item_passes(claim, value_item, q, page_text, corpus_texts)),
            None,
        )
        if alt is not None:
            new_evidence[i] = alt
            moved += 1
    if not moved:
        return claim, 0
    return claim.model_copy(update={"evidence": new_evidence}), moved


def check_claim_items(
    claim: Claim, page_text: str, corpus_texts: Optional[List[str]] = None
) -> Optional[List[Tuple[bool, str, Optional[str]]]]:
    """B-40 (2026-09-27): the per-item counterpart to check_claim() above -- see the module
    docstring's B-40 section for the real temenos.com/thoughtworks.com/plaid.com bugs this exists
    to fix. Returns one (ok, reason, evidence_to_keep) tuple per entry in claim.value, in the same
    order, so a caller (wi/extract/pipeline.py) can rebuild a claim from only the verified items
    instead of discarding every item because one of them failed. `evidence_to_keep` is the exact
    real quote to use for a surviving item (the paired evidence[i], or whichever fragment of a
    multi-line evidence string matched it) -- None when the item failed.

    Returns None -- "nothing to partially filter, use check_claim()'s whole-claim result as-is" --
    for every claim shape this doesn't apply to: a single-string value (nothing to split credit
    across), and a single-LINE evidence string paired with a list value (no per-item boundary
    exists inside one undifferentiated quote; see the module docstring)."""
    if not isinstance(claim.value, list):
        return None

    if isinstance(claim.evidence, list):
        results: List[Tuple[bool, str, Optional[str]]] = []
        for value_item, quote in zip(claim.value, claim.evidence):
            if not _quote_found(quote, page_text, corpus_texts):
                results.append(
                    (False, f"quote not found in page text for {value_item!r}: {quote!r}", None)
                )
            elif claim.status == Status.extracted and not value_supported_by_quote(value_item, quote, field=claim.field):
                results.append(
                    (False, f"quote does not support the value {value_item!r}: {quote!r}", None)
                )
            elif (claim.status == Status.extracted and claim.field == "products.names"
                    and _products_name_evidence_is_bare_self_repeat(value_item, quote)):
                results.append((
                    False,
                    f"evidence for {value_item!r} is nothing but the value repeated back "
                    f"verbatim: {quote!r}",
                    None,
                ))
            else:
                results.append((True, "ok", quote))
        return results

    if isinstance(claim.evidence, str):
        fragments = _evidence_fragments(claim.evidence, page_text, corpus_texts)
        if len(fragments) <= 1:
            return None
        results = []
        for value_item in claim.value:
            match = next(
                (
                    fragment for fragment in fragments
                    if _quote_found(fragment, page_text, corpus_texts)
                    and (claim.status != Status.extracted
                         or value_supported_by_quote(value_item, fragment, field=claim.field))
                ),
                None,
            )
            if match is not None:
                results.append((True, "ok", match))
            else:
                results.append((
                    False,
                    f"no single line of the evidence is a real, supporting quote for {value_item!r}",
                    None,
                ))
        return results

    return None


def check_conflicting_claim(claim: Claim, corpus_texts: List[str]) -> Tuple[bool, str]:
    """Verifies a `conflicting` claim's paired value/evidence lists (B-06/EVD-05, added
    2026-09-27 -- see wi/schemas/claim.py's docstring for why conflicting claims are shaped this
    way). Before this function existed, a conflicting claim was never checked against real page
    text at all: check_claim() explicitly short-circuits for Status.conflicting (see its
    docstring), and wi/extract/pipeline.py never called anything else for it either -- a claim
    marked "conflicting" with entirely fabricated value/evidence would sail through as-is.

    This closes that gap the same way check_claim() closes it for extracted claims: each
    evidence[i] must be real text (quote_in_page) AND must actually support value[i]
    (value_supported_by_quote), checked pairwise, exactly as for a multi-value extracted claim.
    The one real difference from check_claim(): each evidence entry is searched across every
    crawled page in `corpus_texts`, not one fixed `claim.source_url`'s text, because the whole
    point of a conflict is that its two values come from two different pages, and Claim carries
    only a single source_url field. Claim's own validator already guarantees `value` and
    `evidence` are equal-length lists of at least 2 for a conflicting claim, so the zip below is
    safe."""
    for value_item, quote in zip(claim.value, claim.evidence):
        if not any(quote_in_page(quote, text) for text in corpus_texts):
            return False, f"quote not found on any crawled page for {value_item!r}: {quote!r}"
        if not value_supported_by_quote(value_item, quote, field=claim.field):
            return False, f"quote does not support the value {value_item!r}: {quote!r}"
    return True, "ok"
