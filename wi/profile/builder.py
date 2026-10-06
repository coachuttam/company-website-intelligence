"""Canonical profile assembly (Final PRD, Section 5, OUT-01): turns the flat claim ledger
`wi/extract/pipeline.py` already produces into the second, product-facing output the PRD
requires -- "a canonical profile that references claim IDs. The profile is derived from
validated claims, not from model prose."

No new extraction or validation happens here. This module is pure, deterministic
reorganisation of already-validated claims: it is never given raw model output, never talks to
an LLM, and never invents a value that doesn't already exist as a Claim. That's the whole point
of OUT-01 as a *separate* build step from extraction (see the PRD's Section 5 "Build order":
"extract claim objects, validate them, reconcile conflicts, then derive the profile").

Why this didn't exist until now: wi/extract/pipeline.py's ExtractionRun.claims is already a
complete, schema-valid ledger -- every one of wi/extract/fields.py's 15 fields has exactly one
Claim, whatever its status. But a flat list keyed only by dotted field name is the *ledger*
shape (the audit layer), not the *profile* shape a UI or downstream consumer would want (the
PRD's Section 6 reference page groups fields under headings like "Pricing and commercial
signals", shows only populated facts in the main sections, and pushes every not_found/
conflicting field into a dedicated gaps-and-conflicts panel "not as empty cards"). Several
things were blocked on this gap existing: OUT-01 itself (no second output existed at all,
just the ledger), B-19/CST-03 (a "partial profile ... with limit_reached" needs a profile to
attach that flag to), and Week 4's reference renderer (UI-01/UI-02 read a profile, not a raw
claim list).

Field-to-group mapping: wi/extract/fields.py's FIELDS are named "<prefix>.<short_name>" (e.g.
"pricing.sales_motion"). The prefix maps onto one of the PRD's six Section 4 groups via
GROUP_MAP below -- a straightforward rename (e.g. "pricing" -> "pricing_commercial" to match
the PRD's own group name), not a redesign. Note the PRD's Section 4 groups list more subfields
than our frozen 15-field schema actually implements (e.g. Group B "Products and services" lists
six subfields; fields.py only has two, `products.names` and `products.delivery_model`, per the
Week 1 schema freeze) -- this module reflects whatever fields.py actually has, not the PRD's
full illustrative list, since schema-v1 is what's frozen and testable.

Announcements (B-07/OUT-04, added 2026-09-27): dated company-reported announcements
(wi/extract/pipeline.py's `run.announcements`, see wi/schemas/announcement.py) are placed under
`profile["evidence_traction"]["announcements"]` -- OUT-04's own acceptance criterion is
"a funding-statement fixture appears under `evidence_traction` with a date and quote", and
`evidence_traction` is exactly the group GROUP_MAP already maps the "traction" field prefix
onto. This is deliberately a THIRD kind of entry alongside the group's ordinary populated-field
entries (from `groups[group][short_name]`) and its not_found/conflicting entries (from
`gaps_conflicts`) -- an announcement isn't a value for any of the 15 fields at all (see
wi/schemas/announcement.py's docstring for why it needs its own model rather than reusing Claim),
so it doesn't belong in either of those two existing places. It is always present as a key (an
empty list when a site has none) rather than omitted, so a profile consumer never has to
special-case its absence. Rejected/dropped announcements are not surfaced in the profile at all
(same principle as a rejected Claim, which the profile also never shows directly) -- they exist
only in `run.rejected_announcements`, the audit trail, not the product-facing output.

Populated vs. gaps/conflicts placement (a real design decision, not spelled out verbatim by the
PRD): a field's entry appears under its group in `profile[group]` only when the claim is
`extracted` or `inferred` -- the PRD's Section 6 item 9 is explicit that not_found fields "live
[in the gaps panel], not as empty cards" in the main sections. A `conflicting` claim is placed
in `gaps_conflicts` too, not under its group: EVD-05 says a conflict must "never silently pick
one" value, and showing one arbitrarily chosen value under the main heading would do exactly
that, silently, to anyone who doesn't also inspect the ledger. Putting it in gaps_conflicts
(alongside not_found) surfaces the disagreement itself as the thing to look at, with both
values visible in the claim it references.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from wi.extract.fields import FIELDS
from wi.extract.pipeline import ExtractionRun
from wi.schemas.announcement import Announcement
from wi.schemas.claim import Claim, Status

# wi/extract/fields.py's dotted prefix -> the PRD Section 4 / Section 5 group name.
GROUP_MAP: Dict[str, str] = {
    "company_identity": "company_identity",
    "products": "products_services",
    "customers": "customers_positioning",
    "pricing": "pricing_commercial",
    "traction": "evidence_traction",
    "comparisons": "company_comparisons",
}


def _field_entry(claim: Claim) -> dict:
    entry = {"value": claim.value, "status": claim.status.value, "claim_id": claim.claim_id}
    if claim.confidence is not None:
        entry["confidence"] = claim.confidence
    return entry


def _announcement_entry(announcement: Announcement) -> dict:
    """B-07/OUT-04: the profile-facing shape for one dated company-reported announcement --
    text, category and date up front (what a reader wants to see), the quote and its source
    kept alongside so the entry is checkable exactly like every other profile value resolves to
    a claim (OUT-01)."""
    return {
        "text": announcement.text,
        "category": announcement.category,
        "date": announcement.date,
        "source_url": announcement.source_url,
        "evidence": announcement.evidence,
        "announcement_id": announcement.announcement_id,
    }


def _coverage(
    claims_by_field: Dict[str, Claim],
    pages_scanned: int,
    rejected_count: int,
    retrieved_at: Optional[str],
) -> dict:
    """PRD Section 6 item 2, "Trust and coverage strip": pages scanned, fields populated,
    evidence-support rate, inferences, conflicts, last retrieval date. The PRD doesn't spell
    out evidence_support_rate's exact formula, so this module defines it as: of every claim the
    model backed with evidence and attempted to assert (survived to `extracted`/`inferred`, OR
    was rejected by wi/validate/evidence.py's deterministic check -- see ExtractionRun.rejected),
    what fraction actually survived. A field the model never attempted at all (plain `not_found`,
    no evidence offered) is deliberately excluded from this denominator -- it's an honest gap,
    not a failed verification, and folding it in would make the rate look like an extraction-
    completeness score rather than what it's meant to measure: how trustworthy the model's
    evidenced attempts are once checked. None (not 0 or 1) when nothing was attempted at all,
    so a caller can tell "nothing to measure" apart from "measured, and it's zero"."""
    populated = [c for c in claims_by_field.values() if c.status in (Status.extracted, Status.inferred)]
    inferred = [c for c in populated if c.status == Status.inferred]
    conflicting = [c for c in claims_by_field.values() if c.status == Status.conflicting]
    not_found = [c for c in claims_by_field.values() if c.status == Status.not_found]

    attempted = len(populated) + rejected_count
    evidence_support_rate = (len(populated) / attempted) if attempted else None

    return {
        "pages_scanned": pages_scanned,
        "total_fields": len(FIELDS),
        "fields_populated": len(populated),
        "fields_inferred": len(inferred),
        "fields_conflicting": len(conflicting),
        "fields_not_found": len(not_found),
        "evidence_support_rate": evidence_support_rate,
        "last_retrieved_at": retrieved_at,
    }


def build_profile(
    run: ExtractionRun,
    pages_scanned: int,
    retrieved_at: Optional[str] = None,
    schema_version: str = "schema-v1",
    crawl_budget_exhausted: bool = False,
) -> dict:
    """Builds the PRD Section 5 "Output 2" document: {"profile": {...}, "claims": [...]}, plus
    `schema_version` (OUT-02: "stamp the schema version") and `limit_reached` (CST-03 / B-19).

    `pages_scanned` and `retrieved_at` are the caller's own knowledge (how many pages were
    actually crawled/cleaned, and which run this was) -- this module has no independent way to
    know either, and deliberately doesn't guess. `run.claims` already carries a `retrieved_at`
    per populated claim; `retrieved_at` here is the coverage strip's single "as of" date for the
    whole profile, which the caller (run_site.py) already computes once for the entire run.

    `limit_reached` (B-19: "Given a token or page limit breach, a partial profile is returned
    with limit_reached") is true if EITHER hard limit named in CST-03 was actually hit this
    run: `run.dropped_pages` is non-empty (wi/extract/pipeline.py's input-token-budget guard
    trimmed pages before the LLM call), or the caller reports `crawl_budget_exhausted=True`
    (wi/crawl/fetch.py's CrawlResult.budget_exhausted -- the page/depth crawl caps were hit
    before every discoverable page could be fetched). Both are real, independent ways a run can
    be partial; this module doesn't have crawl_result in scope, so the caller passes the second
    flag through explicitly.

    Every one of FIELDS is expected to have exactly one Claim in `run.claims` -- extract_claims()
    guarantees this (a field the model skips gets an explicit not_found replacement). If a field
    is somehow still missing (defensive, not expected in practice), it's treated as not_found
    with no claim_id rather than raising -- a missing profile entry should never crash profile
    assembly, since a broken profile builder would be strictly worse than an honest gap.
    """
    claims_by_field: Dict[str, Claim] = {c.field: c for c in run.claims}

    groups: Dict[str, dict] = {group: {} for group in set(GROUP_MAP.values())}
    gaps_conflicts: List[dict] = []

    for field_name in FIELDS:
        claim = claims_by_field.get(field_name)
        prefix, _, short_name = field_name.partition(".")
        group_key = GROUP_MAP.get(prefix, prefix)

        if claim is None:
            gaps_conflicts.append({
                "field": field_name, "status": Status.not_found.value, "claim_id": None,
            })
            continue

        entry = _field_entry(claim)
        if claim.status in (Status.extracted, Status.inferred):
            groups.setdefault(group_key, {})[short_name] = entry
        else:  # not_found or conflicting -- see module docstring for why both land here
            gaps_conflicts.append({**entry, "field": field_name})

    profile = dict(groups)
    profile["coverage"] = _coverage(claims_by_field, pages_scanned, len(run.rejected), retrieved_at)
    profile["gaps_conflicts"] = gaps_conflicts
    # B-07/OUT-04: always present (an empty list when none) -- see module docstring.
    profile.setdefault("evidence_traction", {})["announcements"] = [
        _announcement_entry(a) for a in run.announcements
    ]

    return {
        "profile": profile,
        "claims": [c.model_dump(mode="json") for c in run.claims],
        "announcements": [a.model_dump(mode="json") for a in run.announcements],
        "schema_version": schema_version,
        "limit_reached": bool(run.dropped_pages) or crawl_budget_exhausted,
    }
