"""Focused second pass for fields the first pass left not_found (B-71, 2026-10-06).

Why: on snowflake.com the cleaned text of /solutions/industries really lists eight industries, yet
customers.industries came back not_found on every full run (40 pages, ~36,000 input tokens), with the
model reporting it had only looked at the home page. Shown that one page alone, the same model and
prompt returned all eight (checked with _diagnostic_focus_field.py). So the fact was lost among too
many pages, not missing and not rejected. Prompt wording cannot fix attention dilution; showing the
model fewer, better-chosen pages can.

What it does, after the normal extraction:
  1. Looks at six fields whose facts live on a recognisable kind of page: industries, certifications,
     named customers, partnerships, named alternatives, headquarters.
  2. For each of them that is still not_found, scores the crawled pages (address pattern + words in the
     cleaned text) and keeps the best few, at most `max_pages` in total.
  3. Runs the SAME extraction (same prompt, same evidence gate, same cache) on only those pages and
     adopts a claim only if it is extracted/inferred -- i.e. it already passed every evidence check --
     for a field that was not_found. A field that was answered is never touched.
Nothing is composed here: every adopted claim is one the normal pipeline produced and verified from
real page text. The cache key covers the chosen pages, so a repeat run costs nothing. Any failure
leaves the first-pass result exactly as it was. Config: focus_retry.enabled (default false in code,
true in config.yaml), focus_retry.max_pages, focus_retry.fields.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from wi.crawl.clean import CleanPage
from wi.extract.pipeline import ExtractionRun, RejectedClaim, _combine_usage, extract_claims
from wi.schemas.claim import Claim, Status

# field -> (address pattern on the URL path, words looked for in the cleaned text)
FIELD_HINTS: Dict[str, Tuple[str, str]] = {
    "customers.industries": (
        r"/industr(?:y|ies)(?:/|$)",
        r"\b(?:industr(?:y|ies)|healthcare|financial services|manufacturing|retail|telecom|"
        r"public sector|insurance|education|hospitality|media)\b",
    ),
    "traction.certifications": (
        r"/(?:security|trust|compliance|certifications?)(?:/|$|-)",
        r"\b(?:soc ?[123]|iso ?/?(?:iec )?\d{4,5}|hipaa|gdpr|ccpa|pci|fedramp|csa star|"
        r"certified|compliance)\b",
    ),
    "traction.named_customers": (
        r"/(?:customers?|case-stud(?:y|ies)|success-stor(?:y|ies)|stories)(?:/|$)",
        r"\b(?:trusted by|our customers|customer stor(?:y|ies)|case stud(?:y|ies)|testimonials?)\b",
    ),
    "traction.partnerships": (
        r"/(?:partners?|integrations?|ecosystem|alliances?)(?:/|$)",
        r"\b(?:partners?|integrat\w+|alliances?)\b",
    ),
    "comparisons.named_alternatives": (
        r"/(?:vs|compare|comparison|alternatives?)(?:/|-|$)",
        r"\b(?:vs\.?|versus|alternatives?|compar\w+|competitors?)\b",
    ),
    "company_identity.headquarters": (
        r"/(?:about|company|contact|careers)(?:/|$|-)",
        r"\b(?:headquarter\w*|based in|head office|our offices?|located in|hq)\b",
    ),
}
DEFAULT_FIELDS = list(FIELD_HINTS)
PER_FIELD_PAGES = 2
MIN_PAGE_CHARS = 150
MAX_PAGE_CHARS = 12000
MIN_CONTENT_HITS = 3


def _depth(url: str) -> int:
    return len([seg for seg in urlsplit(url).path.split("/") if seg])


_STATISTIC = re.compile(r"%|\bfortune\s*\d+\b|\bforbes\s*\d+\b|\bg2000\b|\b\d[\d,.]*\s*\+?\s*(?:customers|companies|brands|teams)\b", re.IGNORECASE)


def _drop_statistics(claim: Claim) -> Optional[Claim]:
    """Named customers are names, not statistics ("95% of the Fortune 500"). Drops such items;
    None when nothing is left (or the value/evidence lists cannot be filtered in step)."""
    if not isinstance(claim.value, list):
        return None if _STATISTIC.search(str(claim.value)) else claim
    keep = [i for i, v in enumerate(claim.value) if not _STATISTIC.search(v)]
    if len(keep) == len(claim.value):
        return claim
    if not keep:
        return None
    if isinstance(claim.evidence, list) and len(claim.evidence) == len(claim.value):
        return claim.model_copy(update={"value": [claim.value[i] for i in keep],
                                        "evidence": [claim.evidence[i] for i in keep]})
    return None


def _score(page: CleanPage, url_re: re.Pattern, text_re: re.Pattern) -> int:
    path = urlsplit(page.url).path
    url_hit = bool(url_re.search(path))
    hits = len(text_re.findall(page.text))
    if hits < MIN_CONTENT_HITS and not (url_hit and hits >= 1):
        return 0
    return (4 if url_hit else 0) + min(hits, 8)


def choose_pages(field: str, pages: List[CleanPage], limit: int = PER_FIELD_PAGES) -> List[CleanPage]:
    """The best-scoring pages for `field`, best first; ties keep crawl order. Empty when no page
    looks like it holds this field."""
    url_pat, text_pat = FIELD_HINTS[field]
    url_re, text_re = re.compile(url_pat, re.IGNORECASE), re.compile(text_pat, re.IGNORECASE)
    scored = [(_score(p, url_re, text_re), -_depth(p.url), -i, p) for i, p in enumerate(pages)
              if len(p.text.strip()) >= MIN_PAGE_CHARS]
    scored = [t for t in scored if t[0] > 0]
    # best score first; on a tie the shallower address wins (the overview page, not a sub-page),
    # then crawl order
    scored.sort(key=lambda t: (t[0], t[1], t[2]), reverse=True)
    return [p for _, _, _, p in scored[:limit]]


def focus_retry(
    run: ExtractionRun,
    pages: List[CleanPage],
    config: Dict[str, Any],
    completer: Any,
    retrieved_at: str,
    cache: Any = None,
    extractor: Callable[..., ExtractionRun] = extract_claims,
) -> Dict[str, Any]:
    """Runs the second pass and edits run.claims in place. Always returns a report dict."""
    cfg = config.get("focus_retry") or {}
    if not cfg.get("enabled", False):
        return {"enabled": False}
    report: Dict[str, Any] = {"enabled": True, "calls": 0, "fields": []}
    wanted = [f for f in cfg.get("fields", DEFAULT_FIELDS) if f in FIELD_HINTS]
    max_pages = int(cfg.get("max_pages", 4))

    idx = {c.field: i for i, c in enumerate(run.claims)}
    missing = [f for f in wanted if f in idx and run.claims[idx[f]].status == Status.not_found]
    if not missing:
        return report

    chosen_by_field: Dict[str, List[CleanPage]] = {}
    for f in missing:
        picks = choose_pages(f, pages)
        if picks:
            chosen_by_field[f] = picks
        else:
            report["fields"].append({"field": f, "adopted": False, "reason": "no page looks like it holds this"})
    if not chosen_by_field:
        return report

    # one page set for the single call: best page of each field first, then second-best, up to max_pages
    selected: List[CleanPage] = []
    for rank in range(PER_FIELD_PAGES):
        for picks in chosen_by_field.values():
            if rank < len(picks) and picks[rank] not in selected and len(selected) < max_pages:
                selected.append(picks[rank])
    selected = [CleanPage(url=p.url, title=p.title, text=p.text[:MAX_PAGE_CHARS],
                          truncated=p.truncated or len(p.text) > MAX_PAGE_CHARS) for p in selected]
    report["pages"] = [p.url for p in selected]

    try:
        second = extractor(run.site_url, selected, config, completer,
                           retrieved_at=retrieved_at, cache=cache)
    except Exception as e:     # any failure leaves the first-pass result untouched
        report["error"] = f"{type(e).__name__}: {e}"
        return report
    report["calls"] = 0 if second.cache_status == "hit" else 1
    report["cache_status"] = second.cache_status
    if second.usage is not None:
        report["prompt_tokens"] = second.usage.prompt_tokens
        report["completion_tokens"] = second.usage.completion_tokens
        if run.usage is not None:
            run.usage = _combine_usage(run.usage, second.usage)
        else:
            run.usage = second.usage

    by_field = {c.field: c for c in second.claims}
    for f in chosen_by_field:
        new = by_field.get(f)
        entry: Dict[str, Any] = {"field": f, "pages": [p.url for p in chosen_by_field[f]], "adopted": False}
        report["fields"].append(entry)
        if new is None or new.status not in (Status.extracted, Status.inferred):
            entry["reason"] = "second pass also found nothing"
            for rej in second.rejected:
                if rej.field == f:
                    entry["reason"] = f"second pass claim failed the evidence check: {rej.reason}"
                    run.rejected.append(RejectedClaim(
                        field=rej.field, reason="[second pass] " + rej.reason,
                        attempted_value=rej.attempted_value, attempted_evidence=rej.attempted_evidence,
                        source_url=rej.source_url))
            continue
        if f == "traction.named_customers":
            filtered = _drop_statistics(new)
            if filtered is None:
                entry["reason"] = "second pass answer was a statistic, not customer names"
                continue
            new = filtered
        note = ("Found on a focused second pass: the model was shown only the pages most likely to "
                "hold this field after the full run left it not_found.")
        new = new.model_copy(update={
            "claim_id": run.claims[idx[f]].claim_id,
            "notes": (new.notes + " " + note) if new.notes else note,
        })
        run.claims[idx[f]] = new
        entry["adopted"] = True
        entry["reason"] = "adopted"
    return report
