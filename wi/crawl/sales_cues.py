"""Rule-based detection of sales-motion cues in a page's CLEANED text (B-61, 2026-10-06).

Why this exists: on the 5 dev sites the model answered pricing.sales_motion with a single cue
("Self-serve signup") every time it answered at all, while the hand labels (and most real
pricing pages) are hybrid: a self-serve entry tier AND a contact-sales enterprise tier. Prompt
rules 14 and 17 already ask for both cues and the evidence gate already accepts several
newline-separated real quotes for a single-string field, so the gap is the model not following
the rule, not a missing mechanism. Finding the cue lines is a mechanical job -- a button or
call-to-action text -- so this module does it deterministically and returns the exact lines it
matched. Every returned line is a real line of the page text, which keeps the claim inside the
evidence rules (nothing is composed or paraphrased).

This module is pure (no network, no model call). Live finding that decided how it is used
(_diagnostic_sales_cues.py on the 5 dev sites, 2026-10-06): the CLEANED pricing-page text had no
contact-sales line on any site and no self-serve line on three of them, because the text cleaner
(trafilatura) drops button and link labels as page furniture -- yet the raw page's buttons showed
BOTH cues on all five. So the model was never shown the call-to-action text that prompt rules 14
and 17 tell it to look for. wi/crawl/clean.py now folds the cue lines back into a pricing page's
cleaned text via cue_block_for_html(), the same way it already folds a dropped <h1> or street
address back in; the model and the evidence gate then both see the same real lines.

Lines longer than MAX_LINE_CHARS are ignored: a button or CTA is short, and a long sentence that
happens to contain "contact us" (a privacy paragraph, say) is not a sales-motion cue.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from bs4 import BeautifulSoup

MAX_LINE_CHARS = 120

# (?<![a-z]) / (?![a-z]) are used instead of word-boundary escapes: same effect, easier to read
# and to keep intact when the file is edited through other tools.
_A = r"(?<![a-z])"
_Z = r"(?![a-z])"
_APOS = "['’]"

_SELF_SERVE = [
    rf"{_A}(start|try)( [a-z0-9+ ]{{1,25}})? (for )?free{_Z}",
    rf"{_A}get [a-z0-9+ ]{{1,25}} free{_Z}",
    rf"{_A}get started( for free| free)?{_Z}",
    rf"{_A}sign up( for free| free| now)?{_Z}",
    rf"{_A}buy now{_Z}",
    rf"{_A}add to cart{_Z}",
    rf"{_A}start (your |a )?(free )?trial{_Z}",
    rf"{_A}try (it )?(for )?free{_Z}",
    rf"{_A}free trial{_Z}",
    rf"{_A}subscribe now{_Z}",
    rf"{_A}create (an |your )?account{_Z}",
    rf"{_A}checkout{_Z}",
]

_CONTACT_SALES = [
    rf"{_A}contact (our )?sales{_Z}",
    rf"{_A}talk to (our )?(sales|us|an? (expert|specialist)|our team){_Z}",
    rf"{_A}speak (to|with) (our )?(sales|an? (expert|specialist)|our team){_Z}",
    rf"{_A}(request|book|schedule|get|watch) (a |an )?(demo|quote|call){_Z}",
    rf"{_A}get in touch{_Z}",
    rf"{_A}custom (pricing|plan|quote){_Z}",
    rf"{_A}let{_APOS}?s talk{_Z}",
    rf"{_A}contact us{_Z}",
    rf"{_A}request pricing{_Z}",
]

_SELF_SERVE_RE = [re.compile(p, re.IGNORECASE) for p in _SELF_SERVE]
_CONTACT_SALES_RE = [re.compile(p, re.IGNORECASE) for p in _CONTACT_SALES]

_PRICING_URL_RE = re.compile(r"(pricing|plans|price|buy|purchase)", re.IGNORECASE)


@dataclass
class SalesCues:
    self_serve: List[str] = field(default_factory=list)
    contact_sales: List[str] = field(default_factory=list)

    @property
    def hybrid(self) -> bool:
        return bool(self.self_serve and self.contact_sales)


def is_pricing_page_url(url: str) -> bool:
    """True for a URL whose path looks like a pricing/plans/buy page."""
    path = re.sub(r"^https?://[^/]+", "", url)
    return bool(_PRICING_URL_RE.search(path))


def find_sales_cues(text: str, max_per_kind: int = 3) -> SalesCues:
    """The first few short lines of `text` that look like a self-serve cue and the first few that
    look like a contact-sales cue, each returned exactly as it appears (stripped), in page order,
    without duplicates. A line that matches both kinds is counted as contact-sales only: a
    "Contact sales to get started" button is a sales-assisted cue, not a self-serve one."""
    cues = SalesCues()
    for raw in text.split("\n"):
        line = raw.strip()
        if not line or len(line) > MAX_LINE_CHARS:
            continue
        if any(r.search(line) for r in _CONTACT_SALES_RE):
            if line not in cues.contact_sales and len(cues.contact_sales) < max_per_kind:
                cues.contact_sales.append(line)
        elif any(r.search(line) for r in _SELF_SERVE_RE):
            if line not in cues.self_serve and len(cues.self_serve) < max_per_kind:
                cues.self_serve.append(line)
    return cues


MAX_CTA_CHARS = 60


def extract_cta_lines(html: str) -> List[str]:
    """The visible labels of a page's buttons and links, one per line, in document order, without
    duplicates. Added because the text cleaner (trafilatura) treats button and link labels as page
    furniture and drops them: on the live Calendly and Notion pricing pages the cleaned text had
    no "Contact sales" or "Get started" line at all, even though those are exactly the call-to-
    action labels that show a page's sales motion. Looks at <a>, <button>, role="button" elements
    and submit/button <input> values; labels longer than MAX_CTA_CHARS are skipped (a link that
    wraps a whole card is not a button label)."""
    soup = BeautifulSoup(html, "lxml")
    out: List[str] = []
    seen = set()
    for el in soup.find_all(["a", "button", "input"]):
        if el.name == "input":
            if (el.get("type") or "").lower() not in ("submit", "button"):
                continue
            label = (el.get("value") or "").strip()
        else:
            label = " ".join(el.get_text(" ", strip=True).split())
        if not label or len(label) > MAX_CTA_CHARS or label in seen:
            continue
        seen.add(label)
        out.append(label)
    return out


CUE_BLOCK_HEADER = "Buttons and links on this page:"


def cue_block_for_html(html: str, max_per_kind: int = 3) -> str:
    """A short text block listing the self-serve and contact-sales button/link labels found in
    `html`, one real label per line under CUE_BLOCK_HEADER, or "" when there are none. The labels
    are copied verbatim from the page, so quoting them as evidence is quoting real page text."""
    cues = find_sales_cues("\n".join(extract_cta_lines(html)), max_per_kind=max_per_kind)
    lines = cues.self_serve + cues.contact_sales
    if not lines:
        return ""
    return CUE_BLOCK_HEADER + "\n" + "\n".join(lines)


def cues_from_cue_block(cleaned_text: str) -> SalesCues:
    """The cue lines in a cleaned page's CUE_BLOCK_HEADER block (see cue_block_for_html), or an
    empty SalesCues when the page has no such block. Only the block is read, not the rest of the
    page: its lines are button/link labels, which are far better evidence than a stray sentence
    such as an FAQ question that happens to contain "free trial"."""
    if CUE_BLOCK_HEADER not in cleaned_text:
        return SalesCues()
    return find_sales_cues(cleaned_text.split(CUE_BLOCK_HEADER, 1)[1])
