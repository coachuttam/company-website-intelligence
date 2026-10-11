"""Upgrade bare products.names quotes to sentence evidence when the sent pages have one (B-102).

WHY. On the 13-site comparison (eval/DEV13_RESULTS.md, diagnosis of the cleaner build) the largest
single bucket of misses was products.names rejected by the bare-label guard: 14 field-scores on 9
sites, e.g. Typeform "Growth Flow" and Notion "Notion AI", where the model quoted only the product's
own name. The guard (wi/validate/evidence.py, _products_name_evidence_is_bare_self_repeat) is right
that a bare name proves nothing about the name being a product. But often the same pages hold a real
sentence that names it, and that sentence is the evidence the guard asks for.

WHAT. For products.names only, before the unchanged evidence gate runs: for each item whose quote
equals its value after normalisation (exactly the case the guard rejects), look for a candidate in
the text of the pages sent to the model, in pipeline page order (the claim's cited page first, then
the others in the order they were sent). Candidates are the page's lines, or, for a line longer than
300 characters, the sentence (split after ". ", "? ", "! ") that contains the name. A candidate must:
  - contain the product name as a case-insensitive whole-word/phrase match;
  - have 6 to 60 words and at most 300 characters;
  - not be a line of the "[logo and image labels]" or "[site navigation]" blocks (B-100);
  - not be menu-like: " | " or " · " appearing more than twice;
  - not equal the name.
The first candidate wins, and it is an exact substring of the page text. The claim then goes through
the unchanged gate with the same thresholds and the same bare-label guard, which now passes because
the quote is a sentence. With no candidate, nothing changes and the guard rejects as before (the Loom
case: a hub page of short "Loom for Sales" cards has no such sentence).
Every upgrade is recorded as {field, value, source_url, quote} (at most 60 per run) and written to
the run JSON's top-level "evidence_upgrades"; the Claim model is unchanged.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from wi.crawl.fetch import normalize_url
from wi.schemas.claim import Claim, Status
from wi.validate.evidence import normalise

FIELD = "products.names"
BLOCK_MARKERS = ("[logo and image labels]", "[site navigation]")
MIN_WORDS, MAX_WORDS, MAX_CHARS = 6, 60, 300
MAX_SEPARATORS = 2
MAX_RECORDS = 60
_SENTENCE_SPLIT = re.compile(r"(?<=[.?!]) ")


def _candidates(page_text: str):
    for line in page_text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith(BLOCK_MARKERS):
            continue
        if len(stripped) <= MAX_CHARS:
            yield stripped
        else:
            for sentence in _SENTENCE_SPLIT.split(stripped):
                if sentence.strip():
                    yield sentence.strip()


def find_upgrade(name: str, page_text: str) -> Optional[str]:
    """The first line or sentence of `page_text` that qualifies as evidence for `name`, or None."""
    pattern = re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)", re.IGNORECASE)
    for cand in _candidates(page_text):
        if normalise(cand) == normalise(name) or not pattern.search(cand):
            continue
        if not MIN_WORDS <= len(cand.split()) <= MAX_WORDS or len(cand) > MAX_CHARS:
            continue
        if cand.count(" | ") + cand.count(" · ") > MAX_SEPARATORS:
            continue
        return cand
    return None


def upgrade_bare_product_quotes(claim: Claim, text_by_url: Dict[str, str]) -> Tuple[Claim, List[dict]]:
    """Returns (claim with upgraded quotes, upgrade records). Anything other than an extracted
    products.names claim with a list of quotes is returned unchanged."""
    if (claim.field != FIELD or claim.status != Status.extracted
            or not isinstance(claim.value, list) or not isinstance(claim.evidence, list)
            or len(claim.value) != len(claim.evidence)):
        return claim, []
    cited = normalize_url(claim.source_url) if claim.source_url else None
    order = ([cited] if cited in text_by_url else []) + [k for k in text_by_url if k != cited]
    evidence = list(claim.evidence)
    records = []
    for i, (value, quote) in enumerate(zip(claim.value, claim.evidence)):
        if not isinstance(value, str) or normalise(value) != normalise(quote or ""):
            continue
        for key in order:
            found = find_upgrade(value, text_by_url[key])
            if found is not None:
                evidence[i] = found
                records.append({"field": FIELD, "value": value, "source_url": key, "quote": found})
                break
    if not records:
        return claim, []
    return claim.model_copy(update={"evidence": evidence}), records
