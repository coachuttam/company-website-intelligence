"""The strict JSON schema handed to the LLM provider's structured-output mode.

`retrieved_at` and `claim_id` are deliberately NOT in this schema: those are
deterministic facts (today's date, a generated id), so wi/extract/pipeline.py
fills them in code rather than trusting the model to copy a date correctly --
one less thing the model can get wrong.

`value` is a string OR an array of strings OR null (an "anyOf", which is the union form
OpenAI's strict structured-output mode supports) -- see wi/schemas/claim.py for why. The
schema itself doesn't force a particular field to be one shape or the other; the prompt
(wi/extract/prompt.py) is what tells the model which fields to return as a list, and
wi/validate/evidence.py checks either shape.

`evidence` is the same anyOf shape (string / array of strings / null), decided 2026-09-23 for
the same reason `value` was widened: a multi-value claim's items can come from separate parts
of a page (basecamp.com's pricing plans are four separate lines, not one contiguous quote), so
a single evidence string forced the model to fabricate one combined quote to cover them all --
which wi/validate/evidence.py correctly rejected as not appearing on the page. wi/schemas/claim.py
enforces that a list `evidence` is only legal alongside a list `value` of the same length (one
quote per value entry); wi/validate/evidence.py checks each pair independently.

`announcements` (added 2026-09-27, B-07/OUT-04): a second, separate top-level array alongside
`claims`, for dated company-reported announcements (funding, product launches, and similar --
see wi/schemas/announcement.py) that must never be folded into any of the 15 core FIELDS. This
has to be declared here, not just asked for in the prompt: OpenAI's strict structured-output
mode rejects any top-level key the schema doesn't declare (`additionalProperties: False` on
CLAIMS_RESPONSE_SCHEMA below), so without this the model would have no legal way to return
announcements at all even if the prompt asked for them -- they would either be silently dropped
or forced into a `claims` entry that then fails wi/schemas/claim.py's field-enum validation
(`field` must be one of FIELDS). `announcements` is required (can be an empty array) for the
same reason every other top-level key here is required under strict mode: the schema must name
every key the model is allowed to return, and strict mode requires every declared property to
be present in `required`.
"""
from __future__ import annotations

from wi.extract.fields import FIELDS
from wi.schemas.announcement import ANNOUNCEMENT_CATEGORIES
from wi.schemas.claim import Status

CLAIM_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "field": {"type": "string", "enum": FIELDS},
        "status": {"type": "string", "enum": [s.value for s in Status]},
        "value": {
            "anyOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
                {"type": "null"},
            ]
        },
        "confidence": {"type": ["number", "null"]},
        "source_url": {"type": ["string", "null"]},
        "page_title": {"type": ["string", "null"]},
        "evidence": {
            "anyOf": [
                {"type": "string"},
                {"type": "array", "items": {"type": "string"}},
                {"type": "null"},
            ]
        },
        "notes": {"type": ["string", "null"]},
        "coverage": {
            "type": ["object", "null"],
            "properties": {
                "page_types_checked": {"type": "array", "items": {"type": "string"}},
                "pages_checked": {"type": "integer"},
            },
            "required": ["page_types_checked", "pages_checked"],
            "additionalProperties": False,
        },
    },
    "required": ["field", "status", "value", "confidence", "source_url",
                 "page_title", "evidence", "notes", "coverage"],
    "additionalProperties": False,
}

ANNOUNCEMENT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string"},
        "category": {"type": "string", "enum": sorted(ANNOUNCEMENT_CATEGORIES)},
        "date": {"type": "string"},
        "source_url": {"type": ["string", "null"]},
        "page_title": {"type": ["string", "null"]},
        "evidence": {"type": "string"},
    },
    "required": ["text", "category", "date", "source_url", "page_title", "evidence"],
    "additionalProperties": False,
}

CLAIMS_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "claims": {"type": "array", "items": CLAIM_ITEM_SCHEMA},
        "announcements": {"type": "array", "items": ANNOUNCEMENT_ITEM_SCHEMA},
    },
    "required": ["claims", "announcements"],
    "additionalProperties": False,
}
