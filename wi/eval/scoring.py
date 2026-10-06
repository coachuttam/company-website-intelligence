"""Field-level accuracy scoring (Final PRD Section 12) against hand-labelled ground truth.

This is Week 3's second workstream (per the user's own priority order: canonical profile
first, this second): "one bounded DSPy or prompt-optimisation trial, only after the baseline
exists" (Section 10) needs a baseline to compare against, and this module is that baseline's
scoring engine. It is pure, deterministic comparison logic -- no I/O, no LLM calls -- so it can
be fully unit-tested; `eval/baseline.py` is the thin script that loads real files and calls it,
mirroring the run_site.py / wi.profile.builder split already established in this codebase.

**The PRD's scoring table (Section 12, verbatim):**

| Case | Counts as |
| --- | --- |
| Value matches the label (after normalising) | Correct |
| Value differs from the label | Incorrect |
| Label is not_found and the system returns not_found | Correct abstention |
| Label has a value and the system returns not_found | Miss |
| Label is not_found and the system returns a value | Unsupported (most serious) |

That table only distinguishes "the system returns not_found" from "the system returns a value" --
it doesn't have a case for the system returning `conflicting` (two disagreeing values, both kept,
per EVD-05 and B-06). None of the 5 dev-set hand-labels currently contain a `conflicting` claim
either way, so this is an edge case, not the common path -- but AC-11 explicitly requires
"conflict handling" to be reported *separately* from extraction/inference accuracy, which is the
evidence that the PRD intends conflicts to be their own bucket, not silently folded into
Correct/Incorrect. So a system `conflicting` claim against a label that has a value gets its own
`Verdict.CONFLICTING` here rather than being forced into Correct or Incorrect (a real, if
unlikely, value inside the conflict's description could coincidentally match the label, and
scoring that as "Correct" would misrepresent what actually happened: the system didn't confidently
assert the right answer, it flagged a disagreement). A `conflicting` claim against a `not_found`
label is still `Unsupported` -- the system asserted *something* the site's ground truth says isn't
there at all, which is exactly what Unsupported means regardless of how many values it asserted.

**Normalisation ("after normalising"):** the PRD doesn't spell out what normalising means, so this
module takes the literal, conservative reading: casefold, strip, and collapse internal whitespace
for a string; for a list, normalise every item the same way and compare as an order-independent
set (a named-entity list like `traction.certifications` has no meaningful order). This is NOT
semantic or paraphrase-aware matching -- "Basecamp is project management without all the nonsense"
and a differently-worded but equally correct paraphrase will NOT match. That's a deliberate
choice, not an oversight: silently accepting paraphrases risks hiding a genuine factual error
behind "close enough" wording, and the PRD's own phrase is "normalising", not "matching the
meaning of". The consequence is that free-text fields (company_identity.description,
products.delivery_model, customers.segments, and the prose-heavy pricing fields) will likely score
lower than list-of-named-things fields even when the model's answer is substantively right --
`eval/baseline.py` prints full label-vs-system detail for every non-Correct verdict specifically
so a human can spot-check these rather than trust one blended number (also satisfies AC-08:
reproducible, and AC-09: reported per field, not blended).

**Scoring methodology revisited (B-45, 2026-09-27):** after the Week 4 held-out run held flat at
29-30% across several rounds of genuine bug fixes, the per-field breakdown showed the remaining
gap concentrated in two shapes that are arguably scoring-strictness artifacts rather than
extraction defects: (1) MULTI_VALUE_FIELDS (products.names, traction.named_customers/
certifications/partnerships, customers.industries -- 39 of the 105 remaining points across the
10 held-out sites) where the system and the label both name real, evidence-backed things but pick
different subsets of a long list (e.g. plaid.com genuinely has 15+ named products; any 3-5 real
ones the model finds will never exactly equal the label's own pick); (2) the two free-text fields
this docstring already calls out above (19 points) where the system's answer is substantively
right but worded differently than the label. Given both, ranked by size, and told plainly that (1)
stays fully deterministic while (2) requires an LLM call and gives up this module's no-I/O
guarantee, Uttam chose: for (1), overlap credit -- `Verdict.correct_partial`, any real shared item
between the two lists (see `_has_list_overlap()`), counted as a "right call" for AC-02's headline
exactly like `correct`, but kept in ITS OWN bucket in the counts breakdown rather than silently
merged into `correct` -- a genuinely disjoint list (the label and the system name completely
different things) still scores `incorrect`. For (2), an LLM-as-judge check -- `Verdict.
correct_semantic`, via the new `apply_semantic_judging()` function below, called by
eval/baseline.py's and eval/held_out.py's `--semantic-judge` flag. That flag is OFF by default:
this module's own scoring core (`score_field`/`score_run`/`summarize`/`extraction_vs_inference`
above) makes no LLM or network call under any circumstance, exactly as before B-45 -- the judging
step is a separate, explicit, opt-in pass a caller runs afterward on the already-scored results,
so a plain `python eval/held_out.py` run stays fully deterministic and free, and only adds the
paraphrase-credit LLM call when Uttam explicitly asks for it.

**B-46 (2026-09-27), widening the judge:** the first live `--semantic-judge` run (150 fields, 10
held-out sites) showed `correct_partial` working exactly as designed (11 real awards) but
`correct_semantic` firing only once out of roughly 15 eligible `incorrect` free-text verdicts, and
zero times on products.delivery_model specifically despite 9 candidate verdicts there. Inspecting
those 9 pairs by hand: most are genuine substance disagreements (thoughtworks' label "service" vs
the system's "software", nobroker's "marketplace" vs "service", sarvamai's label naming an on-prem
deployment option the system's bare "software" gives no hint of) -- the judge rejecting those is
correct, not a bug. But a few (plaid: label "software (API/developer platform)" vs system
"software"; gong: label "software (cloud-based SaaS Revenue AI platform)" vs system "software")
read as the same core claim with a same-category elaboration, which the judge's own prompt already
says should count as the same substance ("a vaguer or more general phrasing... still counts"). The
judge said no anyway on every one of the 9. Two changes, both scoped to what this run's numbers
actually showed rather than a broader rewrite: (1) `OpenAIJudgeCompleter`'s prompt (wi/extract/
llm.py) now spells out the elaboration-vs-material-fact distinction with a worked example on each
side, instead of leaving "material fact" for the model to interpret unaided -- a prompt-only
change, unverified from this sandbox since this module's own no-LLM/no-network guarantee means the
judge is never actually called here; it needs a live `--semantic-judge` re-run to confirm it moves
the number. (2) FREE_TEXT_JUDGED_FIELDS below now also includes customers.segments and
pricing.sales_motion -- both entirely free-text single-string fields the previous run showed flat
at 0% because neither B-45 mechanism could ever reach them (overlap credit needs a list-shaped
field; the judge wasn't scoped to them yet) -- same rationale as the original two fields, not a new
kind of exception. company_identity.headquarters was deliberately NOT added: its mismatches look
like exact-formatting differences (a normalisation question, not a semantic-judge one) or genuinely
different addresses (which should stay incorrect), and this round's numbers didn't point at it.

**B-54 (2026-10-03), reversing the B-46 headquarters exclusion:** B-53 (wi/validate/evidence.py)
fixed a real evidence-check bug where a company_identity.headquarters claim was wrongly discarded
to not_found whenever its value named a country not literally spelled out in the quoted address
block. Confirmed live on razorpay.com immediately after that fix: the claim now survives as a
genuine `extracted` value, "Bengaluru, Karnataka, India" -- but the held-out label is the fuller
street address, "1st Floor, SJR Cyber, 22, Laskar Hosur Road, Adugodi, Bangalore, Karnataka -
560030", so the strict scorer still marked it `incorrect`. That is the SAME "same core fact,
different level of elaboration" shape already recognised for products.delivery_model and
company_identity.description -- not the "exact-formatting difference" or "genuinely different
address" shape B-46 excluded this field for. B-46's exclusion was reasonable given what that
round's data showed; this round's data points the other way for this specific mismatch pattern.
FREE_TEXT_JUDGED_FIELDS below now includes company_identity.headquarters. Unverified against the
real model -- this sandbox has no network/API key to call the judge -- needs a live
`--semantic-judge` re-run to confirm it actually upgrades cases like razorpay's.

**B-58 (2026-10-04), `pricing.public_plans` is scored by plan name plus price:** the PRD defines
this field as "public plans and amounts", and Uttam chose "name plus price" as the label
convention (each item = plan name, then its price). The system writes an item as "Standard,
$10/seat/mo" while a hand label may write "Standard — $10/seat/mo", and the page itself may say
"$10 /seat/mo" or "₹1,499/month + GST": exact string equality made every such pair `incorrect`
even when the plan and its amount were identical. So for this one field an item is reduced to a
key -- the plan name (text before the first comma, colon or dash separator; a trailing " plan"
dropped) plus the numbers in its price (thousands commas removed) plus a currency if one is
written ($, USD, INR, ...). Two items are the same plan when the keys are equal; an item with no
price (a free or custom-priced plan) matches on name alone. All keys equal -> `correct`; some in
common -> `correct_partial` (already the rule for this list field); none -> `incorrect`. A WRONG
amount still gives a different key, so "Standard, $10" vs "Standard, $12" never matches, and a
names-only label cannot match a priced system item: labels have to carry the prices. No other
field's scoring changes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Dict, List, Optional, Union

from wi.extract.fields import FIELDS, MULTI_VALUE_FIELDS
from wi.schemas.claim import Claim, Status

Value = Optional[Union[str, List[str]]]


class Verdict(str, Enum):
    correct = "correct"
    incorrect = "incorrect"
    correct_abstention = "correct_abstention"
    miss = "miss"
    unsupported = "unsupported"
    # Not one of the PRD's five -- see module docstring for why a `conflicting` system claim
    # against a valued label gets its own bucket instead of being forced into correct/incorrect.
    conflicting = "conflicting"
    # B-45 (2026-09-27), Uttam's explicit choice -- see module docstring's "Scoring methodology
    # revisited" section. Deliberately their OWN buckets rather than silently folded into
    # `correct`: a reader of the counts breakdown can always see how many "right calls" came from
    # an exact match versus one of these two more lenient rules.
    correct_partial = "correct_partial"     # multi-value field, real overlap, not an exact set match
    correct_semantic = "correct_semantic"   # free-text field, LLM-judged as the same substance


# Verdicts PRD Section 12 calls a "right call": either a genuinely correct value, or an honest
# abstention when the label agrees nothing is there. Used for the single headline accuracy number
# alongside (never instead of) the full per-verdict breakdown -- see FieldScore/summarize below.
# correct_partial and correct_semantic (B-45) are included here because Uttam's explicit choice
# was for both to count toward AC-02's headline number, not just be reported as a side metric.
_RIGHT_CALL = {Verdict.correct, Verdict.correct_abstention, Verdict.correct_partial, Verdict.correct_semantic}

# B-45/B-46/B-54: fields the LLM semantic judge is allowed to touch. Deliberately a fixed, small,
# explicit set (like every other narrow guard in this codebase) rather than "any field the strict
# matcher rejects" -- each of these five was individually seen, on a live run, scoring `incorrect`
# for wording/elaboration rather than substance: company_identity.description and
# products.delivery_model (B-45), customers.segments and pricing.sales_motion (B-46, added once
# the live run showed them flat at 0% with neither B-45 mechanism able to reach them), then
# company_identity.headquarters (B-54, added once a live run showed a real
# full-address-vs-city/state/country mismatch -- the same elaboration shape as the other four, not
# the exact-formatting/genuinely-different-address shape B-46 originally excluded this field for;
# see this module's docstring). Extending this to every field would risk quietly forgiving a
# genuinely wrong extracted value on some field never audited for this; company_identity.name
# stays deliberately excluded -- a short exact-match identifier where "vaguer phrasing" isn't a
# meaningful concept.
FREE_TEXT_JUDGED_FIELDS = {
    "company_identity.description", "products.delivery_model",
    "customers.segments", "pricing.sales_motion", "company_identity.headquarters",
}


def normalize(value: Value) -> Optional[Union[str, frozenset]]:
    """Casefold/strip/collapse-whitespace a string; normalise-and-set a list. None stays None.

    A bare string is treated as a single-item set when compared against a list-shaped value (see
    _values_match) so a shape mismatch alone -- which shouldn't happen given the schema's
    MULTI_VALUE_FIELDS enforcement, but this module doesn't assume the caller never has a bug --
    doesn't produce a spurious Incorrect.
    """
    if value is None:
        return None
    if isinstance(value, list):
        return frozenset(_normalize_str(v) for v in value)
    return _normalize_str(value)


_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
    "thirteen": "13", "fourteen": "14", "fifteen": "15", "twenty": "20", "thirty": "30",
    "forty": "40", "sixty": "60", "ninety": "90",
}
_NUMBER_WORD_RE = re.compile(r"\b(" + "|".join(_NUMBER_WORDS) + r")\b")


def _normalize_str(s: str) -> str:
    """Casefold, collapse whitespace, and read a spelled-out number as its digits (B-63,
    2026-10-06): "Seven-day trial" and "7-day trial" are the same answer; on the 5 dev sites the
    strict comparison scored simplestores' free_trial incorrect for exactly that. Applied to both
    the label and the system answer, so it only ever makes two spellings of one number equal."""
    folded = " ".join(s.casefold().strip().split())
    return _NUMBER_WORD_RE.sub(lambda m: _NUMBER_WORDS[m.group(1)], folded)


def _values_match(label_value: Value, system_value: Value) -> bool:
    label_norm = normalize(label_value)
    system_norm = normalize(system_value)
    # Defensive shape reconciliation: if one side normalised to a frozenset and the other to a
    # plain string, wrap the string side as a single-item set before comparing.
    if isinstance(label_norm, frozenset) and isinstance(system_norm, str):
        system_norm = frozenset({system_norm})
    elif isinstance(system_norm, frozenset) and isinstance(label_norm, str):
        label_norm = frozenset({label_norm})
    return label_norm == system_norm


def _has_list_overlap(label_value: Value, system_value: Value) -> bool:
    """B-45: true when both sides are genuinely list-shaped (after normalising) and share at
    least one real item. Only meaningful for a true list on BOTH sides -- unlike _values_match(),
    this deliberately does NOT coerce a bare string into a single-item set first, so it can never
    fire by accident on a single-string field via that defensive reconciliation path."""
    label_norm = normalize(label_value)
    system_norm = normalize(system_value)
    if not isinstance(label_norm, frozenset) or not isinstance(system_norm, frozenset):
        return False
    return bool(label_norm & system_norm)


PLAN_FIELD = "pricing.public_plans"
_PLAN_SEPARATOR = re.compile(r"\s+[-\u2013\u2014]\s+|\s*[,:]\s+")
_PLAN_CURRENCY = {"$": "$", "usd": "$", "\u20b9": "\u20b9", "inr": "\u20b9", "rs": "\u20b9",
                  "\u20ac": "\u20ac", "eur": "\u20ac", "\u00a3": "\u00a3", "gbp": "\u00a3"}
_PLAN_AMOUNT = re.compile(
    r"(?:[$\u20b9\u20ac\u00a3]|usd|inr|eur|gbp|rs\.?)\s?(\d+(?:\.\d+)?k?)"
    r"|(\d+(?:\.\d+)?k?)\s?(?:usd|inr|eur|gbp)"
)
_PLAN_CURRENCY_TOKEN = re.compile(r"[$\u20b9\u20ac\u00a3]|usd|inr|eur|gbp|rs")


def _plan_key(item: str) -> tuple:
    """B-58: (plan name, price numbers, currencies) for one public_plans item."""
    text = " ".join(str(item).casefold().split())
    parts = _PLAN_SEPARATOR.split(text, maxsplit=1)
    name = parts[0].strip()
    if name.endswith(" plan"):
        name = name[: -len(" plan")].strip()
    rest = parts[1] if len(parts) > 1 else ""
    flat = rest.replace(",", "")
    # Prefer the amounts written next to a currency ("$10", "379USD") so a trial length such as
    # "after 14 days" is never mistaken for the price; with no currency, use every number.
    priced = [a or b for a, b in _PLAN_AMOUNT.findall(flat)]
    numbers = tuple(sorted(priced or re.findall(r"\d+(?:\.\d+)?k?", flat)))
    currencies = tuple(sorted({_PLAN_CURRENCY[c] for c in _PLAN_CURRENCY_TOKEN.findall(rest)}))
    return (name, numbers, currencies)


def _plan_keys(value: Value) -> frozenset:
    if value is None:
        return frozenset()
    items = value if isinstance(value, list) else [value]
    return frozenset(_plan_key(v) for v in items if str(v).strip())


@dataclass
class FieldScore:
    field: str
    verdict: Verdict
    label_status: str
    label_value: Value
    system_status: Optional[str]
    system_value: Value
    system_claim_id: Optional[str]


def score_field(field: str, label_entry: dict, claim: Optional[Claim]) -> FieldScore:
    """Score one field for one site. `claim` is None only defensively (extract_claims()
    guarantees one claim per field, same defensive stance as wi/profile/builder.py) -- treated
    as if the system had said not_found, since a missing claim asserts nothing either way.
    """
    label_status = label_entry["status"]
    label_value = label_entry.get("value")

    system_status = claim.status.value if claim is not None else Status.not_found.value
    system_value = claim.value if claim is not None else None
    system_claim_id = claim.claim_id if claim is not None else None

    if label_status == Status.not_found.value:
        if system_status == Status.not_found.value:
            verdict = Verdict.correct_abstention
        else:
            # Includes `conflicting` -- the site's own ground truth says nothing is there, so any
            # asserted value (single, list, or a conflict between two) is unsupported by it.
            verdict = Verdict.unsupported
    else:
        if system_status == Status.not_found.value:
            verdict = Verdict.miss
        elif system_status == Status.conflicting.value:
            verdict = Verdict.conflicting
        elif field == PLAN_FIELD and _plan_keys(label_value) and _plan_keys(system_value):
            # B-58: plan name plus price, not raw string equality -- see module docstring.
            label_keys, system_keys = _plan_keys(label_value), _plan_keys(system_value)
            if label_keys == system_keys:
                verdict = Verdict.correct
            elif label_keys & system_keys:
                verdict = Verdict.correct_partial
            else:
                verdict = Verdict.incorrect
        elif _values_match(label_value, system_value):
            verdict = Verdict.correct
        elif field in MULTI_VALUE_FIELDS and _has_list_overlap(label_value, system_value):
            # B-45: real overlap on a genuinely list-shaped field counts as a right call, not an
            # automatic exact-set-match failure -- see module docstring.
            verdict = Verdict.correct_partial
        else:
            verdict = Verdict.incorrect

    return FieldScore(
        field=field, verdict=verdict, label_status=label_status, label_value=label_value,
        system_status=system_status, system_value=system_value, system_claim_id=system_claim_id,
    )


def score_run(label_doc: dict, claims: List[Claim]) -> List[FieldScore]:
    """Scores every field in FIELDS (not just whatever the label file happens to list, and not
    just whatever the run happens to contain) so a field missing from either side is still
    accounted for defensively rather than silently skipped.
    """
    claims_by_field: Dict[str, Claim] = {c.field: c for c in claims}
    label_fields = label_doc["fields"]
    return [
        score_field(field, label_fields[field], claims_by_field.get(field))
        for field in FIELDS
    ]


def is_right_call(verdict: Verdict) -> bool:
    """Public accessor for _RIGHT_CALL -- callers outside this module (eval/baseline.py's and
    eval/held_out.py's "worth a human spot-check" listing) should never need to duplicate or
    reach into the private membership set directly."""
    return verdict in _RIGHT_CALL


def summarize(scores: List[FieldScore]) -> dict:
    """Per-verdict counts plus a headline accuracy = right-calls / total (see _RIGHT_CALL).
    Reported ALONGSIDE the raw counts, never instead of them -- AC-09 requires per-field
    reporting, not one blended score, and a single accuracy number hides exactly the
    Miss-vs-Unsupported distinction Section 12 asks to keep visible.
    """
    counts = {v.value: 0 for v in Verdict}
    for s in scores:
        counts[s.verdict.value] += 1
    total = len(scores)
    right_calls = sum(counts[v.value] for v in _RIGHT_CALL)
    return {
        "counts": counts,
        "total": total,
        "accuracy": (right_calls / total) if total else None,
    }


# B-45: correct_partial/correct_semantic count as "correct" everywhere a plain `correct` did
# before -- both AC-11's per-status accuracy split and the headline number (_RIGHT_CALL above).
_CORRECT_LIKE = {Verdict.correct, Verdict.correct_partial, Verdict.correct_semantic}


def _accuracy_for_status(scores: List[FieldScore], system_status: str) -> Optional[float]:
    eligible = [s for s in scores if s.system_status == system_status
                and (s.verdict in _CORRECT_LIKE or s.verdict == Verdict.incorrect)]
    if not eligible:
        return None
    return sum(1 for s in eligible if s.verdict in _CORRECT_LIKE) / len(eligible)


def extraction_vs_inference(scores: List[FieldScore]) -> dict:
    """AC-11: "Reported separately: ... extraction accuracy, inference accuracy, conflict
    handling ...". Extraction accuracy = correct / (correct + incorrect) restricted to claims
    the system actually marked `extracted`; inference accuracy is the same restricted to
    `inferred`. Both exclude Miss/Unsupported/Correct-abstention entries -- those never had a
    system_status of extracted or inferred to begin with, so they can't inform either number.
    `conflicting_count` is the same conflict-handling figure AC-11 asks to keep separate from
    both accuracy numbers, not blended into either one.
    """
    return {
        "extraction_accuracy": _accuracy_for_status(scores, Status.extracted.value),
        "inference_accuracy": _accuracy_for_status(scores, Status.inferred.value),
        "conflicting_count": sum(1 for s in scores if s.verdict == Verdict.conflicting),
    }


def apply_semantic_judging(scores: List[FieldScore], judge, model: str) -> List[FieldScore]:
    """B-45 (2026-09-27), Uttam's explicit choice -- see module docstring's "Scoring methodology
    revisited" section. Upgrades an `incorrect` verdict on one of FREE_TEXT_JUDGED_FIELDS to
    `correct_semantic` when `judge` (a wi.extract.llm.JudgeCompleter) decides the system's answer
    states the same substantive facts as the label, just worded differently.

    Deliberately kept OUT of score_field()/score_run() above, which stay exactly as pure and
    network-free as this module always was (no I/O, no LLM calls -- see the top-of-file docstring
    and AC-08's reproducibility requirement). This is a separate, explicitly opt-in post-processing
    step a caller runs afterward, only when it wants to trade a slice of that determinism for
    paraphrase credit on these two fields specifically -- see eval/baseline.py's and
    eval/held_out.py's `--semantic-judge` flag, which is off by default. A caller that never
    passes a real judge here gets byte-for-byte the same scores as before B-45 existed.

    Never touches any verdict other than `incorrect`, never touches any field outside
    FREE_TEXT_JUDGED_FIELDS, and never touches a pair where either side isn't a genuine non-empty
    string (a list-shaped field's already-covered by the deterministic overlap-credit rule above,
    and a `not_found`/`None` side has nothing for a judge to compare)."""
    upgraded = []
    for s in scores:
        if (s.verdict == Verdict.incorrect and s.field in FREE_TEXT_JUDGED_FIELDS
                and isinstance(s.label_value, str) and s.label_value.strip()
                and isinstance(s.system_value, str) and s.system_value.strip()
                and judge.judge(s.label_value, s.system_value, s.field, model)):
            s = replace(s, verdict=Verdict.correct_semantic)
        upgraded.append(s)
    return upgraded
