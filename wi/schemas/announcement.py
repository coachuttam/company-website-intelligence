"""Dated, company-reported announcements (Final PRD OUT-04 / Section 4 Group E), a distinct
output from the 15 frozen FIELDS/Claims (Final PRD line 67: "Funding, financial, legal,
regulatory, competitor and acquisition fields are not core fields. If the company states one on
its own site, it may be captured only as a dated company-reported announcement with evidence.
It is never presented as verified intelligence.").

Why a separate model instead of reusing Claim (B-07, added 2026-09-27): Claim's 15 fields
(wi/extract/fields.py) are a FIXED, exactly-one-per-run set -- every run produces exactly 15
Claims, one per field, whatever their status. An announcement is the opposite shape: a
variable-length list (zero, one, or several may genuinely exist on a real site) of items that
don't belong to any of the 15 fields at all -- a funding announcement isn't a mis-filed
"traction.partnerships" entry or a stretched "traction.certifications" one, it's a genuinely
different kind of fact the core schema was never meant to hold (OUT-04's own wording: "never as
core fields"). Forcing it into Claim's shape would also make Claim's status/coverage/inference
machinery mean the wrong thing here -- an announcement is neither "extracted" evidence for a
fixed field nor an abstention needing a coverage record; it's a captured, dated, self-reported
statement with its own narrower verification (a real quote; nothing to infer, nothing to be
"not_found" about). Hence a purpose-built model instead of stretching Claim to cover it.

No "not_found" placeholder is produced for announcements, unlike Claim: the field-freeze's
"every field gets exactly one claim" guarantee is specific to the 15 fixed fields, and there is
no equivalent fixed slot here to explicitly abstain from. Zero announcements found on a site is
simply an empty list -- an honest, ordinary outcome for most sites, not a gap needing a coverage
record the way a missing core field would be.

`category` is a small closed set (Final PRD Group E: "dated first-party announcements and
product launches", plus line 67's own funding/financial/legal/regulatory/competitor/acquisition
examples) so a profile consumer can group or filter announcements without parsing free text.
"""
from __future__ import annotations

from pydantic import BaseModel, model_validator
from typing import Optional

ANNOUNCEMENT_CATEGORIES = {
    "funding",
    "product_launch",
    "partnership",
    "expansion",
    "leadership_change",
    "acquisition",
    "other",
}


class Announcement(BaseModel):
    announcement_id: str
    text: str                      # short factual restatement, e.g. "$5M Series A funding round"
    category: str                  # one of ANNOUNCEMENT_CATEGORIES
    date: str                      # the date the announcement itself states, exactly as given
                                    # on the page -- NOT retrieved_at, which is when we crawled it
    source_url: str
    page_title: Optional[str] = None
    evidence: str                  # exact (or near-exact) quote from the page
    retrieved_at: str              # deterministic, code-assigned -- see wi/extract/pipeline.py

    @model_validator(mode="after")
    def _rules(self) -> "Announcement":
        for name in ("text", "category", "date", "source_url", "evidence", "retrieved_at"):
            if not getattr(self, name):
                raise ValueError(f"announcement is missing '{name}'")
        if self.category not in ANNOUNCEMENT_CATEGORIES:
            raise ValueError(
                f"announcement category {self.category!r} is not one of "
                f"{sorted(ANNOUNCEMENT_CATEGORIES)}"
            )
        return self
