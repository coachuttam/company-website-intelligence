"""The claim object: the only unit of fact in the system (Final PRD, Section 5).

Rules enforced here:
- Exactly four statuses.
- `extracted` and `inferred` claims MUST carry value, source_url, evidence, retrieved_at (EVD-01).
- `not_found` MUST carry a coverage record (EVD-04).
- `inferred` is allowed only for whitelisted fields, and needs a note (EVD-03).
- Confidence, if present, is between 0 and 1.
- If `evidence` is a list, `value` must be a list of the exact same length (one quote per
  value entry) -- see below.
- `value` can only be a list when `field` is in MULTI_VALUE_FIELDS -- see below.
- An `extracted`/`inferred` claim's value can never be the literal string "not_found"/
  "not found" (B-10, added 2026-09-27) -- see below.

`value` accepts a plain string OR a list of strings (decided 2026-09-22, in place of the
original string-only design). Multi-item fields -- named customers, certifications,
partnerships, industries, comparisons -- were being hand-labelled as JSON lists anyway
(see eval/labels/*.json), so a run's own output and the hand-label answer key were in two
different shapes with no agreed way to compare them. A list is also the more honest
representation: joining "Yatra, Mahindra Logistics" into one string loses the fact that
these are two distinct entities, and forced wi/validate/evidence.py to guess where one item
ends and the next begins by splitting on commas -- fragile for a value like "small to
medium-sized businesses" that contains no genuine item boundary. wi/extract/fields.py's
MULTI_VALUE_FIELDS says which fields the model is asked to return as a list.

`evidence` accepts a plain string OR a list of strings (decided 2026-09-23). Real bug that
motivated this: on basecamp.com's pricing page, the four plans appear as four separate lines
("Freelancer, $25/mo", "Studio, $59/mo", "Pro, $99/mo", "Unlimited, $299/mo") -- there is no
single contiguous span of page text that reads as one quote covering all four. The model still
had to give ONE `evidence` string, so it silently concatenated the plans into a sentence that
never actually appears on the page, and wi/validate/evidence.py correctly (if unhelpfully)
rejected that fabricated quote, downgrading a perfectly real claim to not_found. The fix is
NOT to loosen what counts as a valid quote -- that would let real fabrications back in. It's
to let a multi-value claim carry one quote per value entry instead of forcing them into one.
When `evidence` is a list, it must be exactly as long as `value` (which must also be a list):
`evidence[i]` is the quote that has to independently exist on the page AND independently
support `value[i]`, checked pairwise by wi/validate/evidence.py. A single-string `evidence` on
a single-string `value` still works exactly as before -- this is additive, not a relaxation.

`value` may only be a list when `field` is one of wi/extract/fields.py's MULTI_VALUE_FIELDS
(decided 2026-09-24). Real gap this closes: nothing previously stopped a claim from returning a
list `value` for a field the prompt never authorised as list-shaped -- on a live basecamp.com
run the model invented a `customers.segments` list (a field that's supposed to stay a single
descriptive string) three different times, each with different made-up contents, and it was
only ever caught because the *contents* didn't match the quote, not because the *shape* was
wrong to begin with. This closes that gap structurally: a claim whose field/value-shape
disagree with MULTI_VALUE_FIELDS fails validation and gets safely replaced with a `not_found`
claim by wi/extract/pipeline.py's existing backfill path, the same way a malformed claim
already was. This is a general rule, so it protects every single-string field, not just the
one that surfaced it.

The literal string "not_found" (or "not found") is rejected as a `value` on an `extracted`/
`inferred` claim (B-10, decided 2026-09-27, part of "mixed forms" behaviour testing). Real gap
this closes: two of B-10's three "mixed forms" sub-cases -- a claim with no `status` field at
all, and a `null` value on an extracted/inferred claim -- were already correctly rejected by
existing Pydantic/required-field logic before this change (a bare/missing `status` fails
Pydantic's own required-field check on the enum; a `null` value fails the existing "missing
'value'" check a few lines up, since `not getattr(self, name)` is already true for `None`).
The third sub-case was not: nothing stopped the model from writing `status="extracted"` (or
"inferred") with `value="not_found"` -- a status/value combination that is self-contradictory
(claiming to have found something while stating the value IS "not found") but was previously
schema-valid, since "not_found" is just an ordinary non-empty string as far as the earlier
checks are concerned. This closes that gap structurally, checked case-insensitively and against
every item when `value` is a list, so a claim can't launder an abstention through the wrong
status just by choosing that one string.

`conflicting` claims now require the same paired-list shape as a multi-value field's evidence
array, regardless of whether `field` is actually in MULTI_VALUE_FIELDS (decided 2026-09-27,
B-06/EVD-05). Real gap this closes: before this, `status="conflicting"` required nothing at all
-- not even a value or evidence -- and wi/extract/pipeline.py never ran any check against it
either, so a hallucinated "the two pages disagree" claim would sail through completely
unverified (see wi/validate/evidence.py's check_conflicting_claim for the other half of this
fix). `value` must now be a list of at least 2 differing raw values (one per disagreeing page)
and `evidence` a matching list of one real quote per entry. This deliberately reuses the
existing array mechanism rather than accepting rule 2's original "value describing both in one
sentence" wording literally -- a single composed sentence merging two pages' facts would itself
risk being an invented string that never appears verbatim anywhere, exactly the failure mode
rule 7 exists to prevent.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field, model_validator

from wi.extract.fields import MULTI_VALUE_FIELDS

# Fields where a controlled inference is allowed (proposed in Week 1, approved with the schema freeze).
INFERENCE_WHITELIST = {
    "pricing.sales_motion",
    "pricing.revenue_model",
    "products.delivery_model",
}


class Status(str, Enum):
    extracted = "extracted"
    inferred = "inferred"
    not_found = "not_found"
    conflicting = "conflicting"


class Coverage(BaseModel):
    """Recorded for `not_found`: what was searched before giving up."""

    page_types_checked: List[str]
    pages_checked: int = Field(ge=0)


class Claim(BaseModel):
    claim_id: str
    field: str                          # e.g. "pricing.sales_motion"
    value: Optional[Union[str, List[str]]] = None
    status: Status
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    source_url: Optional[str] = None
    page_title: Optional[str] = None
    evidence: Optional[Union[str, List[str]]] = None  # quote(s) from the page; see docstring
    retrieved_at: Optional[str] = None  # ISO date, e.g. "2026-09-21"
    notes: Optional[str] = None
    coverage: Optional[Coverage] = None

    @model_validator(mode="after")
    def _evidence_rules(self) -> "Claim":
        # `conflicting` is exempted below (2026-09-27, B-06/EVD-05): it inherently needs two
        # values even on a field that is normally single-string (e.g. company_identity.headquarters
        # disagreeing across two pages) -- see the conflicting-status block further down for why.
        if (isinstance(self.value, list) and self.field not in MULTI_VALUE_FIELDS
                and self.status != Status.conflicting):
            raise ValueError(
                f"field '{self.field}' is not in MULTI_VALUE_FIELDS -- its value must be a "
                "single string, not a list"
            )

        if self.status in (Status.extracted, Status.inferred):
            for name in ("value", "source_url", "evidence", "retrieved_at"):
                if not getattr(self, name):
                    raise ValueError(f"{self.status.value} claim is missing '{name}'")

            # B-10 (2026-09-27): the literal string "not_found"/"not found" is not a real value
            # -- see the module docstring for why this is the one "mixed forms" sub-case that
            # wasn't already caught above.
            value_items = self.value if isinstance(self.value, list) else [self.value]
            for item in value_items:
                if isinstance(item, str) and item.strip().lower().replace("_", " ") == "not found":
                    raise ValueError(
                        f"{self.status.value} claim's value is the literal string {item!r} -- "
                        "use status='not_found' (with a coverage record) instead of asserting "
                        "an abstention as a value"
                    )

            if isinstance(self.evidence, list):
                if isinstance(self.value, list):
                    if len(self.evidence) != len(self.value):
                        raise ValueError(
                            f"evidence has {len(self.evidence)} item(s) but value has "
                            f"{len(self.value)} -- each value entry needs its own paired "
                            "evidence quote"
                        )
                else:
                    raise ValueError(
                        "evidence can only be a list when value is also a list "
                        "(one quote per value entry)"
                    )

        if self.status == Status.inferred:
            if self.field not in INFERENCE_WHITELIST:
                raise ValueError(f"inference is not allowed for field '{self.field}'")
            if not self.notes:
                raise ValueError("inferred claim needs a 'notes' explanation")

        if self.status == Status.not_found and self.coverage is None:
            raise ValueError("not_found claim needs a coverage record")

        if self.status == Status.conflicting:
            # B-06 / EVD-05 ("preserve conflicting values with evidence, never silently pick
            # one") -- added 2026-09-27 after discovering `conflicting` had NO requirements at
            # all: a claim could set status="conflicting" with value=None and evidence=None and
            # pass validation untouched, and wi/extract/pipeline.py never ran any evidence check
            # against it either (see wi/validate/evidence.py's check_conflicting_claim). Fixed by
            # requiring the same paired list-of-values/list-of-evidence shape rule 6 already uses
            # for multi-value fields (decided 2026-09-23), reused here rather than inventing a
            # new "one sentence describing both" format -- which would also risk violating rule 7
            # (never compose a sentence that doesn't itself appear on a page). Each value[i] is
            # one page's raw, literal claimed value; evidence[i] is the real quote it came from,
            # checked pairwise against the WHOLE crawled corpus (not one fixed source_url) since
            # the two values legitimately come from two different pages.
            if not isinstance(self.value, list) or len(self.value) < 2:
                raise ValueError(
                    "conflicting claim needs 'value' as a list of at least 2 differing "
                    "values, one per disagreeing page"
                )
            if not isinstance(self.evidence, list) or len(self.evidence) != len(self.value):
                raise ValueError(
                    "conflicting claim needs 'evidence' as a list matching 'value's length, "
                    "one real quote per conflicting value"
                )

        return self
