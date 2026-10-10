"""Optional category-normalised metric (B-99, post-hoc and secondary; rules in docs/SCORING.md).

The dev and held-out v2 labels write products.delivery_model and pricing.revenue_model in different
styles (dev: "Subscription", "Digital software delivered online"; v2: "Software: <description>",
"Subscription tiers plus transaction fees"), while the system emits a bare term ("software (API)",
"subscription"). Strict scoring then marks a right category as incorrect on one set and not the
other. This module compares only the CATEGORY of the two values, so both sets can be read the same
way. It is applied after strict scoring (and after the semantic judge, when that ran), only on demand
(the --normalised flag), and never changes the strict verdicts, headline or report.

Rules, fixed before any number was computed:
  A. Only products.delivery_model and pricing.revenue_model, and only verdicts that are "incorrect".
     Nothing is ever downgraded. Either side without a recognisable category keeps its verdict.
  B. delivery_model: software, service (also "services"), marketplace, physical. The value's own
     leading word when it is one of these; otherwise the earliest of them found as a whole word.
     Equal categories: "correct_normalised".
  C. revenue_model: a value's category SET is every category below with a keyword hit (whole words
     or phrases, casefolded). Equal non-empty sets: "correct_normalised"; overlapping but unequal:
     "correct_partial_normalised"; disjoint or empty: no change.
Both new names count as right calls in the normalised headline only. They are plain strings here,
deliberately not members of wi.eval.scoring.Verdict, so the strict path never sees them.
"""
from __future__ import annotations

import re
from typing import Dict, FrozenSet, List, Optional, Tuple

from wi.eval.scoring import FieldScore, Verdict, is_right_call

NORMALISED_FIELDS = ("products.delivery_model", "pricing.revenue_model")
CORRECT_NORMALISED = "correct_normalised"
CORRECT_PARTIAL_NORMALISED = "correct_partial_normalised"
NORMALISED_VERDICTS = (CORRECT_NORMALISED, CORRECT_PARTIAL_NORMALISED)

DELIVERY_CATEGORIES = ("software", "service", "marketplace", "physical")
_DELIVERY_WORDS = {"software": "software", "service": "service", "services": "service",
                   "marketplace": "marketplace", "physical": "physical"}
_DELIVERY_LEADING = re.compile(r"^\s*(software|services|service|marketplace|physical)(?!\w)")
_DELIVERY_ANY = re.compile(r"(?<!\w)(software|services|service|marketplace|physical)(?!\w)")

REVENUE_KEYWORDS: Dict[str, FrozenSet[str]] = {
    "subscription": frozenset({"subscription", "subscriptions", "per-seat", "per seat", "per-user",
                               "per user", "seat-based", "recurring"}),
    "usage": frozenset({"usage", "usage-based", "pay-as-you-go", "pay as you go", "pay-per-use",
                        "pay per use", "metered", "consumption", "volume-based"}),
    "transaction": frozenset({"transaction", "transaction-based", "transaction fees", "take rate",
                              "commission", "percentage fee", "interchange"}),
    "one_time": frozenset({"one-time", "one time", "perpetual", "lifetime", "license fee"}),
}


def _text(value) -> str:
    if value is None:
        return ""
    return " ".join(value) if isinstance(value, list) else str(value)


def delivery_category(value) -> Optional[str]:
    """Rule B: the leading category word, else the earliest category word in the text, else None."""
    text = _text(value).casefold()
    m = _DELIVERY_LEADING.match(text) or _DELIVERY_ANY.search(text)
    return _DELIVERY_WORDS[m.group(1)] if m else None


def revenue_categories(value) -> FrozenSet[str]:
    """Rule C: every revenue category with at least one whole-word keyword hit."""
    text = _text(value).casefold()
    return frozenset(cat for cat, words in REVENUE_KEYWORDS.items()
                     if any(re.search(r"(?<!\w)" + re.escape(w) + r"(?!\w)", text) for w in words))


def normalised_verdict(score: FieldScore) -> Optional[str]:
    """The new verdict name for one strict FieldScore, or None when it stays as it is (rule A)."""
    if score.field not in NORMALISED_FIELDS or score.verdict != Verdict.incorrect:
        return None
    if score.field == "products.delivery_model":
        label, system = delivery_category(score.label_value), delivery_category(score.system_value)
        return CORRECT_NORMALISED if label is not None and label == system else None
    label_set, system_set = revenue_categories(score.label_value), revenue_categories(score.system_value)
    if not label_set or not system_set:
        return None
    if label_set == system_set:
        return CORRECT_NORMALISED
    return CORRECT_PARTIAL_NORMALISED if label_set & system_set else None


def apply_normalisation(scores: List[FieldScore]) -> List[Tuple[FieldScore, Optional[str]]]:
    """Pairs every strict score with its normalised verdict (None = unchanged). Never mutates."""
    return [(s, normalised_verdict(s)) for s in scores]


def normalised_summary(scores: List[FieldScore]) -> dict:
    """Normalised headline beside the strict one, and upgrades per field."""
    pairs = apply_normalisation(scores)
    total = len(scores)
    strict_right = sum(1 for s in scores if is_right_call(s.verdict))
    upgraded: Dict[str, Dict[str, int]] = {}
    for s, nv in pairs:
        if nv is not None:
            upgraded.setdefault(s.field, {CORRECT_NORMALISED: 0, CORRECT_PARTIAL_NORMALISED: 0})[nv] += 1
    n_up = sum(sum(v.values()) for v in upgraded.values())
    return {
        "total": total,
        "strict_right_calls": strict_right,
        "strict_accuracy": (strict_right / total) if total else None,
        "upgraded_fields": n_up,
        "right_calls": strict_right + n_up,
        "accuracy": ((strict_right + n_up) / total) if total else None,
        "upgraded_by_field": upgraded,
        "rules": "docs/SCORING.md",
    }
