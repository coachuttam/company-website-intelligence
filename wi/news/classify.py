"""Rule-based event type (B-104; PRD Section 8 categories). Keywords on the headline and summary, in a
fixed priority order; no model call. Reported events only: no sentiment or company scoring."""
from __future__ import annotations

import re
from typing import Tuple

RULES: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    ("acquisition", ("acquires", "acquired", "acquisition", "to acquire", "merger", "merges with")),
    ("funding", ("raises", "raised", "funding", "series a", "series b", "series c", "series d", "seed round",
                 "investment round", "valuation")),
    ("legal_regulatory", ("lawsuit", "court", "settlement", "regulator", "regulatory", "license from",
                          "licence from", "approval from", "compliance order", "fined")),
    ("leadership_change", ("appoints", "appointed", "names new", "new ceo", "new cfo", "new cto", "joins as",
                           "steps down", "chief executive")),
    ("hiring_layoffs", ("layoffs", "lays off", "job cuts", "hiring", "headcount")),
    ("partnership", ("partners with", "partnership", "partner with", "teams up", "collaboration with",
                     "strategic alliance")),
    ("customer_contract", ("selects", "chooses", "contract with", "signs deal", "deploys", "customer win")),
    ("expansion", ("expands", "expansion", "opens office", "new office", "enters", "launches in")),
    ("product_launch", ("launches", "launch", "introduces", "introducing", "announces new", "now available",
                        "unveils", "release", "released", "general availability")),
)


def event_type(headline: str, summary: str = "") -> str:
    text = f"{headline} {summary}".casefold()
    for category, words in RULES:
        if any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text) for w in words):
            return category
    return "other"
