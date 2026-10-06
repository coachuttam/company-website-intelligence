"""Optional Jev decision layer for pricing.sales_motion (B-62, 2026-10-06).

What this is: a separate step that runs AFTER extraction (wi/extract is untouched, and so is the run
cache). TypeSafe's Jev is not a text model: it answers typed questions (here a "choice" among named
options) and returns a probability for the decision. sales_motion is a good first use because it is
already a closed question -- self-serve, sales-led, or both -- that the language model answered
inconsistently (B-52, B-61).

Safety rules, in the order they are applied:
  1. Controlled by config classifier.provider ("jev" is the default since 2026-10-06; "none" turns it
     off, then nothing here runs and no key is needed). With no JEV_API_KEY it skips itself.
  2. Jev only sees real cleaned page text from pricing-style pages (wi.crawl.sales_cues.is_pricing_page_url).
     No pricing page -> no call.
  3. A decision below classifier.min_probability (default 0.8) or "unclear" is not applied.
  4. A decision becomes a claim only if real evidence backs it: the exact button/link lines found in
     the page's own "Buttons and links on this page:" block. A "hybrid" decision needs BOTH a
     self-serve line and a contact-sales line; "self_serve" needs a self-serve line and no
     contact-sales line anywhere (otherwise the cues contradict it); "sales_led" the mirror image.
     So Jev can pick between answers the page supports; it cannot invent one.
  5. The claim goes through the same evidence gate (check_claim) as any model claim.
  6. Any Jev failure (no key, network, HTTP error, unparseable answer) leaves the extraction result
     exactly as it was and is recorded in the report.

B-68 (2026-10-06): a second decision, pricing.revenue_model, rides in the same Jev call (same pricing
text, one more question, no extra input tokens). It is OFF unless config classifier.revenue_model.enabled
is true, defaults to mode "fill_missing" (it only fills a not_found, so a richer model answer is never
overwritten), and only the "subscription" choice can be applied: it needs a real recurring-price line
(for example "$10 per member / month") on the pricing text, quoted verbatim. Any other choice is
recorded in the report and not applied, because no deterministic evidence rule backs it.

The answer shape of the live API for a choice question has only been seen through the smoke test, so
parse_choice() accepts the plausible shapes and the raw answer is always stored in the report.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from wi.classify.jev import JevClient, JevError
from wi.crawl.clean import CleanPage
from wi.crawl.fetch import normalize_url
from wi.crawl.sales_cues import CUE_BLOCK_HEADER, cues_from_cue_block, is_pricing_page_url, SalesCues
from wi.extract.pipeline import ExtractionRun, _page_text_by_url
from wi.schemas.claim import Claim, Status
from wi.validate.evidence import check_claim

FIELD = "pricing.sales_motion"
QUESTION_ID = "sales_motion"
MAX_STATE_CHARS = 24000
MAX_PAGE_CHARS = 12000
MAX_PAGES = 3

QUESTION = {
    "type": "choice",
    "instructions": (
        "Based only on this company's pricing page text, how does a visitor become a customer?"
    ),
    "criteria": {
        "self_serve": "Only self-serve signup, checkout or free-trial cues; no contact-sales cue.",
        "sales_led": "Only contact-sales, demo or custom-quote cues; no self-serve signup cue.",
        "hybrid": "Both a self-serve signup cue and a contact-sales cue are present.",
        "unclear": "The text does not show how a visitor becomes a customer.",
    },
}

VALUES = {
    "self_serve": "Self-serve signup",
    "sales_led": "Sales-led (contact sales or demo)",
    "hybrid": "Self-serve signup, plus contact sales or demo for larger plans",
}


def parse_choice(answer: Any, options: List[str]) -> Optional[Tuple[str, float]]:
    """(option, probability) from a Jev choice answer, or None when the shape is not understood."""
    if not isinstance(answer, dict):
        return None
    probs = None
    for key in ("probabilities", "probs", "distribution", "scores"):
        if isinstance(answer.get(key), dict):
            probs = answer[key]
            break
    if probs is None and answer and all(k in options for k in answer):
        probs = answer
    if probs:
        try:
            clean = {k: float(v) for k, v in probs.items() if k in options}
        except (TypeError, ValueError):
            return None
        if clean:
            best = max(clean, key=clean.get)
            return best, clean[best]
    for key in ("choice", "answer", "value", "selected", "decision"):
        picked = answer.get(key)
        if isinstance(picked, str) and picked in options:
            for pkey in ("probability", "confidence", "p"):
                if isinstance(answer.get(pkey), (int, float)):
                    return picked, float(answer[pkey])
            return None   # a pick with no probability cannot be thresholded
    return None


def _pricing_pages(pages: List[CleanPage]) -> List[CleanPage]:
    return [p for p in pages if is_pricing_page_url(p.url) and p.text.strip()][:MAX_PAGES]


def _state_for(pages: List[CleanPage]) -> str:
    parts: List[str] = []
    used = 0
    for p in pages:
        chunk = f"Page: {p.url}\n{(p.text or '')[:MAX_PAGE_CHARS]}"
        if used + len(chunk) > MAX_STATE_CHARS:
            break
        parts.append(chunk)
        used += len(chunk)
    return "\n\n".join(parts)


def _evidence_for(choice: str, pages: List[CleanPage]) -> Optional[Tuple[CleanPage, List[str], Optional[str]]]:
    """(page to cite, real cue lines, conflict note) or None when the cues do not back `choice`."""
    per_page = [(p, cues_from_cue_block(p.text)) for p in pages]
    all_self = [l for _, c in per_page for l in c.self_serve]
    all_contact = [l for _, c in per_page for l in c.contact_sales]
    if choice == "hybrid":
        if not (all_self and all_contact):
            return None
        both = [(p, c) for p, c in per_page if c.hybrid]
        if both:
            p, c = both[0]
            return p, c.self_serve[:2] + c.contact_sales[:2], None
        p = next(p for p, c in per_page if c.self_serve)
        return p, all_self[:2] + all_contact[:2], None
    if choice == "self_serve":
        if not all_self or all_contact:
            return None
        p = next(p for p, c in per_page if c.self_serve)
        return p, all_self[:3], None
    if choice == "sales_led":
        if not all_contact or all_self:
            return None
        p = next(p for p, c in per_page if c.contact_sales)
        return p, all_contact[:3], None
    return None


REVENUE_FIELD = "pricing.revenue_model"
REVENUE_QUESTION_ID = "revenue_model"

REVENUE_QUESTION = {
    "type": "choice",
    "instructions": (
        "Based only on this company's pricing page text, how does the company mainly charge "
        "customers for its product?"
    ),
    "criteria": {
        "subscription": "Recurring plan prices per month or year (per plan, seat, user or member).",
        "usage_based": "Charges depend on usage, such as per request, token, message or transaction.",
        "one_time": "A single upfront purchase price with no recurring fee.",
        "unclear": "The text does not show how the company charges.",
    },
}

REVENUE_VALUES = {"subscription": "Subscription"}

_CURRENCY = r"(?:[$\u20ac\u00a3\u20b9]\s?\d|\d[\d,.]*\s?(?:usd|inr|eur|gbp|[$\u20ac\u00a3\u20b9]))"
_PERIOD = (r"(?:/\s?(?:[a-z]+\s?/\s?)?(?:mo|month|yr|year)(?![a-z])"
           r"|per\s+(?:[a-z]+\s?/?\s?)?(?:month|year|mo|yr)(?![a-z])"
           r"|(?<![a-z])(?:monthly|annually|yearly)(?![a-z]))")
_RECURRING_PRICE_RE = re.compile(rf"{_CURRENCY}[^\n]{{0,30}}?{_PERIOD}", re.IGNORECASE)
MAX_REVENUE_LINE_CHARS = 140


def recurring_price_lines(text: str, limit: int = 3) -> List[str]:
    """Real lines of `text` that state a recurring price (a currency amount followed shortly by a
    per-month / per-year period). Whole lines only, in page order, never composed."""
    out: List[str] = []
    for line in text.splitlines():
        line = line.strip()
        m = _RECURRING_PRICE_RE.search(line) if line and len(line) <= MAX_REVENUE_LINE_CHARS else None
        if m:
            num = re.search(r"\d[\d,.]*", m.group(0))
            try:
                free = num is not None and float(num.group(0).replace(",", "")) == 0.0
            except ValueError:
                free = False
            if not free and line not in out:   # a "$0 per month" free-plan line proves nothing
                out.append(line)
        if len(out) >= limit:
            break
    return out


def _revenue_evidence_for(choice: str, pages: List[CleanPage]) -> Optional[Tuple[CleanPage, List[str], Optional[str]]]:
    if choice != "subscription":
        return None
    for p in pages:
        lines = recurring_price_lines(p.text.split(CUE_BLOCK_HEADER, 1)[0])
        if lines:
            return p, lines, None
    return None


def _sales_evidence(choice, pages):
    return _evidence_for(choice, pages)


_SPECS = [
    {"field": FIELD, "qid": QUESTION_ID, "question": QUESTION, "values": VALUES,
     "evidence": _sales_evidence, "default_mode": None, "enabled_key": None,
     "note": "the evidence lines are the page's own button/link labels."},
    {"field": REVENUE_FIELD, "qid": REVENUE_QUESTION_ID, "question": REVENUE_QUESTION,
     "values": REVENUE_VALUES, "evidence": _revenue_evidence_for, "default_mode": "fill_missing",
     "enabled_key": "revenue_model",
     "note": "the evidence lines are the page's own recurring-price lines."},
]


def _spec_settings(spec: Dict[str, Any], cfg: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """(mode, min_probability) for one decision, or None when that decision is switched off."""
    if spec["enabled_key"] is None:
        return {"mode": cfg.get("mode", "override"), "min_p": float(cfg.get("min_probability", 0.8))}
    sub = cfg.get(spec["enabled_key"]) or {}
    if not sub.get("enabled"):
        return None
    return {"mode": sub.get("mode", spec["default_mode"]),
            "min_p": float(sub.get("min_probability", cfg.get("min_probability", 0.8)))}


def _finish_decision(spec, decision, raw, mode, min_p, run, existing, idx, pricing, pages,
                     retrieved_at, result):
    """Turns one raw Jev answer into an applied claim or a recorded reason."""
    decision["raw"] = raw
    parsed = parse_choice(raw, list(spec["question"]["criteria"]))
    if parsed is None:
        decision["reason"] = "answer shape not understood; extraction result unchanged"
        return
    choice, prob = parsed
    decision.update({"choice": choice, "probability": prob})
    if choice == "unclear":
        decision["reason"] = "Jev says the page does not show this"
        return
    if prob < min_p:
        decision["reason"] = f"probability {prob:.2f} below min_probability {min_p:.2f}"
        return
    if choice not in spec["values"]:
        decision["reason"] = f"no deterministic evidence rule for {choice!r}; not applied"
        return
    found = spec["evidence"](choice, pricing)
    if found is None:
        decision["reason"] = (f"the page's own lines do not back {choice!r}; not applied")
        return
    page, lines, _ = found
    field = spec["field"]
    try:
        claim = Claim(
            claim_id=existing.claim_id if existing is not None else f"classifier:{field}",
            field=field,
            value=spec["values"][choice],
            status=Status.inferred,
            confidence=max(0.0, min(1.0, prob)),
            source_url=page.url,
            page_title=page.title,
            evidence="\n".join(lines),
            retrieved_at=retrieved_at,
            notes=(f"Jev ({result.model}) chose '{choice}' with probability {prob:.2f}; "
                   f"{spec['note']}"),
        )
    except ValueError as e:
        decision["reason"] = f"claim rejected by schema: {e}"
        return
    text_by_url = _page_text_by_url(pages)
    ok, why = check_claim(claim, text_by_url.get(normalize_url(page.url), ""),
                          corpus_texts=list(text_by_url.values()))
    if not ok:
        decision["reason"] = f"evidence gate rejected it: {why}"
        return
    if idx is None:
        run.claims.append(claim)
    else:
        run.claims[idx] = claim
    decision["applied"] = True
    decision["previous"] = (None if existing is None else
                            {"status": existing.status.value, "value": existing.value})
    decision["reason"] = "applied"


def apply_classifier(
    run: ExtractionRun,
    pages: List[CleanPage],
    config: Dict[str, Any],
    retrieved_at: str,
    client: Optional[JevClient] = None,
) -> Dict[str, Any]:
    """Runs the optional decision step and edits run.claims in place when a decision is applied.
    Always returns a report dict (written to the run JSON under "classifier"). One Jev call carries
    every decision that is switched on and still needs an answer."""
    cfg = config.get("classifier") or {}
    provider = cfg.get("provider", "none")
    if provider in (None, "none", ""):
        return {"provider": "none", "enabled": False}
    report: Dict[str, Any] = {"provider": provider, "enabled": True, "calls": 0, "decisions": []}
    if provider != "jev":
        report["error"] = f"unknown classifier provider {provider!r}"
        return report

    report.update({"mode": cfg.get("mode", "override"),
                   "min_probability": float(cfg.get("min_probability", 0.8))})

    pricing = _pricing_pages(pages)
    todo = []        # (spec, decision, mode, min_p, existing, idx)
    for spec in _SPECS:
        st = _spec_settings(spec, cfg)
        if st is None:
            continue
        idx = next((i for i, c in enumerate(run.claims) if c.field == spec["field"]), None)
        existing = run.claims[idx] if idx is not None else None
        decision: Dict[str, Any] = {"field": spec["field"], "applied": False}
        report["decisions"].append(decision)
        if (st["mode"] == "fill_missing" and existing is not None
                and existing.status in (Status.extracted, Status.inferred)):
            decision["reason"] = "existing answer kept (mode fill_missing)"
            continue
        if not pricing:
            decision["reason"] = "no pricing-style page was crawled; no call made"
            continue
        todo.append((spec, decision, st["mode"], st["min_p"], existing, idx))
    if not todo:
        return report

    if client is None:
        try:
            client = JevClient.from_env(cfg)
        except JevError as e:
            report["error"] = str(e)
            for _, decision, *_rest in todo:
                decision["reason"] = "classifier unavailable; extraction result unchanged"
            return report

    try:
        result = client.evaluate(_state_for(pricing), {t[0]["qid"]: t[0]["question"] for t in todo})
    except JevError as e:
        report["error"] = str(e)
        for _, decision, *_rest in todo:
            decision["reason"] = "Jev call failed; extraction result unchanged"
        return report

    price = (cfg.get("jev") or {}).get("price_usd_per_1m_input")
    report.update({
        "model": result.model, "calls": 1,
        "input_tokens": result.input_tokens, "output_tokens": result.output_tokens,
        "elapsed_s": round(result.elapsed_s, 3),
        "estimated_cost_usd": (round(result.input_tokens * float(price) / 1e6, 6)
                               if price is not None else None),
    })
    for spec, decision, mode, min_p, existing, idx in todo:
        _finish_decision(spec, decision, result.answers.get(spec["qid"]), mode, min_p, run,
                         existing, idx, pricing, pages, retrieved_at, result)
    return report
