"""Ties one LLM call to the deterministic evidence check (EVD-02): the model
proposes claims, wi/validate/evidence.py disposes. A claim that fails the
evidence check is never silently kept and never silently dropped either --
it is downgraded to not_found (with coverage) and the original is kept in
`rejected` so a human can see exactly what the model tried to claim and why
it didn't survive the check. That audit trail is the point: EVD-02 existing
only matters if a failure is visible somewhere.

Caching (Week 2, decided 2026-09-26, closes CST-01 / B-17): extract_claims() takes an
optional `cache` (a wi.crawl.cache.RunCache). When given one and every page's content
matches a previous run's fingerprint (same cleaned text, prompt_version, schema_version and
model -- see that module's docstring for why this is a whole-site cache, not per-page), the
cached claims are returned and `completer.complete()` is never called: `run.cache_status`
becomes "hit" and `run.usage` reports 0 tokens, which is the literally correct cost for a
call that didn't happen. Passing no `cache` (the default) reproduces the exact old behaviour,
so every existing caller and test is unaffected.

Input-budget guard (decided 2026-09-26): config.yaml has declared llm.max_input_tokens_per_run
since the project's very first config, but nothing ever enforced it. A real bajajauto.com run
(fixed alongside this in wi/crawl/fetch.py's content-type gate) still hit this even after that
fix was on the table -- 25 real HTML pages, several of them long "80 years of history"-style
company pages, added up to more than gpt-4o-mini's 128,000-token context window, and the
whole run crashed with an unhandled openai.BadRequestError and no output file at all. Before
calling the LLM, extract_claims() now trims pages (from the lowest-priority end -- `pages`
already arrives in crawl_site's priority order, so this keeps the pages most likely to carry
the fields this project cares about) until the estimated size fits llm.max_input_tokens_per_run,
using a deliberately conservative chars-per-token estimate rather than a real tokenizer
dependency. This is NOT B-19/CST-03 (a token/page limit breach producing a partial *profile*
with a `limit_reached` flag needs wi/profile/, Week 3 scope, still not built) -- it is a
narrower guarantee that a real site's content volume alone can no longer crash a run that
would otherwise produce a perfectly good partial extraction from the pages that do fit.

Corrective retry on malformed JSON (B-18, 2026-09-27): before this, a single unparseable model
response (a truncated completion, stray prose around the JSON, a wrong top-level key) fell back
immediately to an all-not_found run with no second attempt -- correct in that it never crashed
and never fabricated claims, but wasteful: a single bad completion threw away everything that
page fetch and prompt-building work for a failure mode that a well-known fix (show the model its
own bad output plus a specific correction, ask again) resolves often enough to be worth one extra
call. extract_claims() now makes exactly one additional completer.complete() call when the first
response fails to parse, with the retry messages built as [original messages..., the bad
assistant response, a corrective user message spelling out the exact required shape]. If the
retry ALSO fails to parse, the behaviour is unchanged from before this fix: log both failures in
schema_errors and fall back to all-not_found. run.usage reports the SUM of both calls' tokens and
elapsed time when a retry happens, since both calls are real cost incurred for this one run, not
just the last one that happened to succeed or fail.

Conflicting-claim evidence check (B-06/EVD-05, 2026-09-27): `conflicting` claims used to reach
`run.claims` with zero verification -- the loop below only ever called check_claim() for
extracted/inferred, and check_claim() itself short-circuits `conflicting` to True (see its
docstring). A hallucinated "these two pages disagree" claim would have sailed through untouched.
Fixed by routing conflicting claims through the new check_conflicting_claim() instead, which
verifies each of the claim's (now schema-required, see wi/schemas/claim.py) paired value/evidence
entries against the whole crawled corpus rather than one fixed source_url, since a conflict's two
values legitimately come from two different pages.

Dated company-reported announcements (B-07/OUT-04, 2026-09-27): a second, separate output
alongside `claims` -- see wi/schemas/announcement.py's docstring for why this is a distinct
model rather than a stretched Claim. The model's response now carries an optional top-level
"announcements" array (wi/extract/schema.py declares it; wi/extract/prompt.py's rule 10 asks
for it); extract_claims() parses it the same permissive way it already treats a missing field
list -- `parsed.get("announcements", [])` rather than a hard KeyError -- so a cached payload or
a completer stubbed before this feature existed (every pre-existing pipeline test) still works
unchanged with zero announcements, never a crash. Each raw announcement is schema-validated
(Announcement(**data), with `announcement_id`/`retrieved_at` code-assigned exactly like a Claim's
are) and then evidence-checked with the SAME quote_in_page() function claims use, against the
same `text_by_url` the claims loop already built -- an announcement's quote has to be real page
text just as much as a claim's does. A claim that fails validation or its evidence check is
downgraded to a safe not_found replacement (there is always exactly one Claim per field to
replace); an announcement that fails either check is simply DROPPED instead (logged to
`run.rejected_announcements` for the audit trail, same principle as RejectedClaim) -- there is no
"not_found announcement" to downgrade to, since announcements are a variable-length list with no
fixed slot (see wi/schemas/announcement.py's docstring).

Partial credit for a multi-value claim (B-40, 2026-09-27): a claim whose evidence check failed
used to be replaced ENTIRELY with not_found, even for a multi-value field where only one item out
of several failed -- found live on the Week 4 held-out run, where temenos.com's
traction.partnerships lost 2 correctly-verified partners because a 3rd's evidence didn't check
out. Uttam's explicit decision (see wi/validate/evidence.py's module docstring for the full
tradeoff writeup): keep the items that independently verify instead of discarding the whole
claim. When check_claim() rejects a claim, wi.validate.evidence.check_claim_items() is now tried
first -- it returns a per-item verdict for a multi-value claim (None for any shape this doesn't
apply to), and `_filter_claim_to_verified_items()` below rebuilds a smaller, fully-verified Claim
from just the survivors. Only falls back to the ordinary not_found replacement when nothing
survives (or the claim's shape doesn't support per-item filtering at all, e.g. a single-string
value) -- identical behaviour to before this fix in both of those cases. The full original attempt
is still recorded in `run.rejected` exactly as before, so the audit trail is unaffected; its
`reason` just now notes when a partial claim was kept instead of a full downgrade.

Paired-length mismatch no longer discards a whole multi-value claim (B-49, 2026-09-27): found
while root-causing why the B-48 held-out confirmation run's headline fell to 37% instead of
recovering -- wi/schemas/claim.py's Claim validator has always hard-rejected a multi-value claim
whose `evidence` list length differs from its `value` list length (raising ValueError before a
Claim object even exists), and the ONLY handling for that ValidationError was to throw the whole
claim away as not_found -- B-40 above never got a chance to run its per-item partial-credit logic,
because there was no Claim object yet to run it on. Grepping every held-out run's schema_errors
for this exact message found it firing 5 times across 3 different sites in one run alone: gong's
traction.certifications (4 values, 3 evidence quotes -- all 4 discarded), razorpay's
products.names (10 values, 9 quotes -- all 10 discarded), and three of thoughtworks' fields
including traction.partnerships (6 values, 1 quote -- all 6 discarded, directly causing that
field's "miss" verdict in the report). This bug predates B-47/B-48; it simply bit harder once a
bigger crawl gave the model more items to try to list and pair. Fixed by truncating BOTH lists to
their shared prefix (`min(len(value), len(evidence))` items, in the model's own order) BEFORE
constructing the Claim -- not by relaxing the schema rule, which still fires and still protects
against any OTHER shape mismatch. The truncated claim then goes through the exact same
check_claim()/check_claim_items() verification as any other claim, so an item that only
LOOKS paired but doesn't actually have a supporting quote on the page still fails and is
filtered out same as always -- this fix stops discarding items that WERE genuinely quoted just
because a later item in the same list wasn't, it does not let an unquoted item through. When the
mismatch means value or evidence is fully empty after truncation, Claim construction still fails
its normal "missing value" check and falls back to not_found exactly as before -- there is no new
uncovered failure mode, only a narrower one.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Dict, List, Optional, Union
from urllib.parse import urlsplit

from pydantic import ValidationError

from wi.crawl.cache import RunCache, run_fingerprint
from wi.crawl.clean import CleanPage
from wi.crawl.fetch import normalize_url
from wi.extract.fields import FIELDS
from wi.extract.llm import ChatCompleter, LLMResult
from wi.extract.prompt import build_messages
from wi.schemas.announcement import Announcement
from wi.schemas.claim import Claim, Status
from wi.validate.evidence import (
    check_claim, check_claim_items, check_conflicting_claim, evidence_home, quote_in_page,
    quote_sources, realign_list_evidence, trim_delivery_model_details, trim_note_details,
)


@dataclass
class RejectedClaim:
    field: str
    reason: str
    attempted_value: Union[str, List[str], None]     # Claim.value can be either shape now
    attempted_evidence: Union[str, List[str], None]  # Claim.evidence can be either shape too
    source_url: Optional[str] = None  # added 2026-09-26: without this, a "quote not found"
                                       # rejection gives no way to tell a genuinely fabricated
                                       # quote apart from the model citing a URL that doesn't
                                       # match any crawled page at all (see _page_text_by_url's
                                       # docstring) -- this is the diagnostic that would confirm
                                       # or rule that out from a real run's output


@dataclass
class RejectedAnnouncement:
    """B-07 (2026-09-27): the announcement equivalent of RejectedClaim -- an announcement that
    failed schema validation or its evidence check is dropped from `run.announcements` (there is
    no not_found slot to downgrade it to, see wi/schemas/announcement.py), but the attempt is
    still kept here so a human can see exactly what the model tried to claim and why it didn't
    survive, the same audit-trail principle RejectedClaim already exists for."""
    reason: str
    attempted_text: Optional[str]
    attempted_evidence: Optional[str]
    source_url: Optional[str] = None


@dataclass
class ExtractionRun:
    site_url: str
    claims: List[Claim] = field(default_factory=list)
    rejected: List[RejectedClaim] = field(default_factory=list)
    announcements: List[Announcement] = field(default_factory=list)          # B-07/OUT-04
    rejected_announcements: List[RejectedAnnouncement] = field(default_factory=list)  # B-07
    schema_errors: List[str] = field(default_factory=list)
    usage: LLMResult | None = None
    cache_status: str = "miss"  # "hit" | "miss" -- CST-02 asks this to be logged per run
    dropped_pages: List[str] = field(default_factory=list)  # URLs trimmed by the input-budget
                                                              # guard below, never sent to the LLM
    # B-89: claim_id -> [{"quote", "urls"}] for accepted claims whose quotes are not all on the one
    # page their source_url names (quotes spread over several pages, or found elsewhere).
    evidence_sources: Dict[str, List[dict]] = field(default_factory=dict)


def _slug(site_url: str) -> str:
    host = (urlsplit(site_url).hostname or "site").lower()
    return host[4:] if host.startswith("www.") else host


def _page_text_by_url(pages: List[CleanPage]) -> Dict[str, str]:
    """Text the evidence check is allowed to treat as "real page text" for a given URL.

    Includes the page's <title> alongside its body text (decided 2026-09-26, after a pattern
    across live runs: company_identity.name -- arguably the single easiest field -- was
    evidence-rejected on 2 of 4 successful dev-set runs so far (zerodha.com, thoughtbot.com),
    each time with the model's evidence quote nowhere in the body text. wi/extract/prompt.py's
    build_messages() shows the model both the page's TITLE and its TEXT as two clearly labelled
    parts of the same page block -- the title is genuinely real page content the model was
    shown, not something it invented -- but check_claim() only ever searched body text, so any
    legitimate quote drawn from a page's <title> (almost always exactly where a company's own
    name appears, e.g. "thoughtbot" or "Zerodha - Online stock trading...") was unfindable by
    construction and got rejected as if it were fabricated. This isn't confirmed as the exact
    cause of those two specific rejections (this session can't reach the live sites to check
    their actual page text), but it's a real, testable gap either way -- the title is content
    the model was given, so it belongs in what the checker searches.

    Keyed by normalize_url() (decided 2026-09-26, after the title fix above still didn't stop
    company_identity.name failing evidence on the very next live run -- bajajauto.com, value
    and evidence BOTH the literal string "Bajaj Auto", still "quote not found in page text". An
    exact-string match failing rules out a near-verbatim-matching or title-vs-body explanation;
    the only thing that reliably produces that symptom is check_claim() being handed an EMPTY
    page_text, which happens when `claim.source_url` doesn't match any key in this dict at all
    -- e.g. the model reproduces a URL with a trailing slash difference from what crawl_site
    actually fetched. Not confirmed from live data yet (RejectedClaim now records source_url,
    see below, specifically so the next real run can confirm or rule this out) but normalising
    both sides of the lookup with crawl_site's own normalize_url() can only help: it's a no-op
    when the URLs already matched exactly, and fixes exactly this class of mismatch when they
    didn't.
    """
    return {normalize_url(p.url): f"{p.title or ''}\n{p.text}" for p in pages}


def _payload_from_run(run: ExtractionRun) -> dict:
    """What actually gets cached: the claims, the audit trail and the schema errors. Never
    the LLMResult -- a cache hit's usage is regenerated fresh in _run_from_cached_payload so
    it honestly reports 0 tokens, not the original call's numbers.

    `announcements`/`rejected_announcements` added 2026-09-27 (B-07) -- a cache hit must return
    the same announcements a fresh run would have found for identical page content, not silently
    drop them (that would make a cached run's output a strict subset of a fresh run's, which is
    exactly the kind of cache-correctness gap EXTRACTION_LOGIC_VERSION exists to prevent)."""
    return {
        "claims": [c.model_dump(mode="json") for c in run.claims],
        "rejected": [asdict(r) for r in run.rejected],
        "announcements": [a.model_dump(mode="json") for a in run.announcements],
        "rejected_announcements": [asdict(r) for r in run.rejected_announcements],
        "schema_errors": run.schema_errors,
        "evidence_sources": run.evidence_sources,   # B-89
    }


def diagnostics_from_run(run: ExtractionRun) -> dict:
    """Why the claims ledger looks the way it does, reshaped for persisting into the run's
    output JSON alongside wi/crawl/fetch.py's crawl_diagnostics().

    Added 2026-09-27 (crawl-coverage-misses investigation, see PROGRESS.md): `run.rejected` and
    `run.schema_errors` already existed and were already the full, correct audit trail --
    _payload_from_run() above has cached exactly this since B-07 -- but run_site.py never wrote
    either one to data/runs/<slug>.json, only printed them to the console once. That silently
    discarded the one piece of information that distinguishes "the model tried and got rejected
    by the evidence check" or "the model's output failed schema validation" from "the model (or
    the crawl before it) never surfaced this field at all" -- every one of those three currently
    looks identical to eval/baseline.py: a bare not_found claim with a `replacement:<field>`
    claim_id. Excludes claims/announcements themselves, which the caller already serializes."""
    return {
        "rejected": [asdict(r) for r in run.rejected],
        "schema_errors": run.schema_errors,
        "rejected_announcements": [asdict(r) for r in run.rejected_announcements],
        "evidence_sources": run.evidence_sources,   # B-89: each quote's own page(s)
    }


def _run_from_cached_payload(site_url: str, payload: dict, model: str) -> ExtractionRun:
    run = ExtractionRun(site_url=site_url, cache_status="hit")
    run.claims = [Claim(**c) for c in payload.get("claims", [])]
    run.rejected = [RejectedClaim(**r) for r in payload.get("rejected", [])]
    run.announcements = [Announcement(**a) for a in payload.get("announcements", [])]
    run.rejected_announcements = [
        RejectedAnnouncement(**r) for r in payload.get("rejected_announcements", [])
    ]
    run.schema_errors = list(payload.get("schema_errors", []))
    run.evidence_sources = dict(payload.get("evidence_sources", {}))   # B-89
    run.usage = LLMResult(content="", model=model, prompt_tokens=0, completion_tokens=0,
                           total_tokens=0, elapsed_s=0.0)
    return run


def _fit_pages_to_input_budget(
    pages: List[CleanPage], max_input_tokens: int, chars_per_token: int = 4
) -> tuple[List[CleanPage], List[str]]:
    """Keeps pages, in the order given (already priority-ordered by crawl_site), until their
    combined size would exceed max_input_tokens_per_run; drops the rest. Always keeps at
    least one page, even if it alone exceeds the budget -- a partial extraction beats none.
    chars_per_token=4 is a deliberately conservative rough estimate (no tokenizer dependency
    yet), meant to stay well clear of a hard provider context limit, not to be exact. See this
    module's docstring for why this exists.
    """
    budget_chars = max_input_tokens * chars_per_token
    kept: List[CleanPage] = []
    dropped: List[str] = []
    used = 0
    for page in pages:
        page_chars = len(page.text)
        if kept and used + page_chars > budget_chars:
            dropped.append(page.url)
            continue
        kept.append(page)
        used += page_chars
    return kept, dropped


CORRECTIVE_RETRY_MESSAGE = (
    'Your previous response could not be parsed as a JSON object of the exact shape '
    '{"claims": [...]}. Respond again with ONLY that JSON object -- one claim per field, in '
    "the field order given earlier in this conversation. No markdown code fences, no "
    "explanation, no text before or after the JSON object."
)


def _parse_claims_payload(content: str) -> tuple:
    """Raises (json.JSONDecodeError, KeyError, TypeError) exactly as the inline try/except this
    replaced did -- pulled out to a function so extract_claims() can call it twice (the original
    attempt and the B-18 corrective retry) without duplicating the parse logic.

    Returns (raw_claims, raw_announcements). `announcements` (B-07, added 2026-09-27) is read
    with `.get(..., [])` rather than `["announcements"]` -- unlike "claims", a missing
    "announcements" key must NOT be treated as malformed output: every pipeline test written
    before B-07 existed (and any real cached payload from before this feature shipped) has no
    such key at all, and the honest, common case for a real site is simply "no announcements
    found", not an error."""
    parsed = json.loads(content)
    return parsed["claims"], parsed.get("announcements", [])


def _combine_usage(first: LLMResult, second: LLMResult) -> LLMResult:
    """B-18: when a corrective retry happens, both calls were real cost -- report their sum,
    not just whichever one happened to succeed or fail. `content` and `model` come from the
    retry (the response actually used from here on)."""
    return LLMResult(
        content=second.content,
        model=second.model,
        prompt_tokens=first.prompt_tokens + second.prompt_tokens,
        completion_tokens=first.completion_tokens + second.completion_tokens,
        total_tokens=first.total_tokens + second.total_tokens,
        elapsed_s=first.elapsed_s + second.elapsed_s,
    )


def _truncate_mismatched_value_evidence(data: dict) -> Optional[str]:
    """B-49 (2026-09-27): mutates `data` in place, truncating a mismatched value/evidence pair
    to their shared prefix so Claim's strict length-match validator (wi/schemas/claim.py) no
    longer discards items that WERE genuinely paired just because a later item in the same list
    wasn't -- see this module's docstring for the full root-cause writeup. Returns a note for
    run.schema_errors when it truncated something, None when there was nothing to do (not a
    list/list mismatch, or the lengths already agree)."""
    if data.get("status") not in (Status.extracted.value, Status.inferred.value):
        return None
    value, evidence = data.get("value"), data.get("evidence")
    if not (isinstance(value, list) and isinstance(evidence, list)):
        return None
    if len(value) == len(evidence):
        return None
    n = min(len(value), len(evidence))
    note = (
        f"B-49: value had {len(value)} item(s), evidence had {len(evidence)} -- kept the "
        f"first {n} paired item(s) instead of discarding the whole claim"
    )
    data["value"] = value[:n]
    data["evidence"] = evidence[:n]
    return note


def _sent_coverage(pages_checked: int) -> dict:
    """B-79: coverage for a not_found field, from what the pipeline actually sent to the model
    (after the input-budget guard), never from the model's own account of what it read. On
    freshworks.com the model reported "home, about, 2 pages checked" for four fields after being
    sent 40 pages, which understated the search and could not be checked."""
    return {"page_types_checked": ["all pages sent to the model"], "pages_checked": pages_checked}


def _not_found_replacement(field_name: str, pages_checked: int) -> Claim:
    return Claim(
        claim_id=f"replacement:{field_name}",
        field=field_name,
        status=Status.not_found,
        coverage=_sent_coverage(pages_checked),
    )


def _filter_claim_to_verified_items(
    claim: Claim, item_results: List[tuple]
) -> Optional[Claim]:
    """B-40 (2026-09-27): rebuilds a multi-value claim from only the items whose evidence
    independently verified, instead of discarding good items along with a bad one -- see
    wi/validate/evidence.py's check_claim_items() docstring for the real bug this fixes (temenos's
    traction.partnerships losing 2 real partners because a 3rd's evidence didn't check out).
    `item_results` is check_claim_items()'s per-item (ok, reason, evidence_to_keep) output, in the
    same order as claim.value. Returns None if nothing survived, so the caller falls back to the
    ordinary not_found replacement exactly as before this fix."""
    kept_values = [claim.value[i] for i, (ok, _, _) in enumerate(item_results) if ok]
    kept_evidence = [ev for (ok, _, ev) in item_results if ok]
    if not kept_values:
        return None
    data = claim.model_dump()
    data["value"] = kept_values
    data["evidence"] = kept_evidence
    return Claim(**data)


def extract_claims(
    site_url: str,
    pages: List[CleanPage],
    config: dict,
    completer: ChatCompleter,
    retrieved_at: str | None = None,
    cache: Optional[RunCache] = None,
) -> ExtractionRun:
    retrieved_at = retrieved_at or date.today().isoformat()
    run = ExtractionRun(site_url=site_url)

    if not pages:
        # Nothing crawled at all: every field is honestly not_found, no LLM call needed.
        for f in FIELDS:
            run.claims.append(_not_found_replacement(f, pages_checked=0))
        return run

    model = config["llm"]["small_model"]
    fingerprint = None
    if cache is not None:
        # Fingerprint the full crawl output, not the input-budget-trimmed set below -- a
        # cache hit means "we've already processed exactly this crawl before"; how much of
        # it fit in one LLM call is this function's own implementation detail, not part of
        # what changed on disk.
        fingerprint = run_fingerprint(site_url, pages, config)
        cached_payload = cache.get(fingerprint)
        if cached_payload is not None:
            return _run_from_cached_payload(site_url, cached_payload, model)

    max_input_tokens = config.get("llm", {}).get("max_input_tokens_per_run")
    llm_pages = pages
    if max_input_tokens:
        llm_pages, run.dropped_pages = _fit_pages_to_input_budget(pages, max_input_tokens)

    messages = build_messages(site_url, llm_pages, retrieved_at)
    result = completer.complete(messages, model=model)
    run.usage = result

    try:
        raw_claims, raw_announcements = _parse_claims_payload(result.content)
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        run.schema_errors.append(f"could not parse model output as {{'claims': [...]}}: {e}")

        # B-18 (2026-09-27): one corrective retry before giving up -- see module docstring.
        retry_messages = messages + [
            {"role": "assistant", "content": result.content},
            {"role": "user", "content": CORRECTIVE_RETRY_MESSAGE},
        ]
        retry_result = completer.complete(retry_messages, model=model)
        run.usage = _combine_usage(result, retry_result)

        try:
            raw_claims, raw_announcements = _parse_claims_payload(retry_result.content)
        except (json.JSONDecodeError, KeyError, TypeError) as e2:
            run.schema_errors.append(
                f"corrective retry also failed to parse as {{'claims': [...]}}: {e2}"
            )
            for f in FIELDS:
                run.claims.append(_not_found_replacement(f, pages_checked=len(llm_pages)))
            return run

    # Built from llm_pages, not the full crawl -- a claim's source_url can only be checked
    # against text the model was actually shown. Using the full `pages` set here would let a
    # claim's evidence check pass against a page trimmed out of this call, which is exactly
    # the kind of unverifiable claim EVD-02 exists to catch.
    text_by_url = _page_text_by_url(llm_pages)
    page_by_key = {normalize_url(p.url): p for p in llm_pages}  # B-77: re-pointing citations
    slug = _slug(site_url)
    seen_fields = set()

    for i, raw in enumerate(raw_claims):
        field_name = raw.get("field", f"unknown-{i}")
        seen_fields.add(field_name)

        data = dict(raw)
        data["claim_id"] = f"{slug}:{field_name}:{i}"
        if data.get("status") in (Status.extracted.value, Status.inferred.value):
            data["retrieved_at"] = retrieved_at  # deterministic, never trust the model's date

        truncation_note = _truncate_mismatched_value_evidence(data)

        try:
            claim = Claim(**data)
        except ValidationError as e:
            run.schema_errors.append(f"claim #{i} ({field_name}): {e.errors()[0]['msg']}")
            run.claims.append(_not_found_replacement(field_name, pages_checked=len(llm_pages)))
            continue

        if truncation_note:
            run.schema_errors.append(f"claim #{i} ({field_name}): {truncation_note}")

        if claim.status == Status.not_found:
            # B-79: the model's own coverage is replaced by what was really sent to it.
            data = claim.model_dump()
            data["coverage"] = _sent_coverage(len(llm_pages))
            claim = Claim(**data)

        if claim.status in (Status.extracted, Status.inferred):
            # Normalised on both sides (see _page_text_by_url's docstring): a claim whose
            # source_url differs from the crawled page only by, say, a trailing slash must
            # still find that page's text, not silently fall through to "" and fail every
            # quote check regardless of whether the quote is real.
            page_text = text_by_url.get(normalize_url(claim.source_url), "") if claim.source_url else ""
            # corpus_texts (B-36, 2026-09-27): a fallback for a real quote cited under the WRONG
            # page among several correctly crawled ones -- see wi/validate/evidence.py's
            # module docstring ("CloseKnit Health"). check_claim() only reaches into this list
            # when the claim's own cited page_text misses; it never replaces the primary check.
            # B-63 (2026-10-06): a list claim whose evidence list is shifted against its value
            # list gets each value re-paired with the quote that supports it (a quote from its OWN
            # evidence list only) before the check below. See realign_list_evidence().
            claim, moved = realign_list_evidence(
                claim, page_text, corpus_texts=list(text_by_url.values())
            )
            if moved:
                run.schema_errors.append(
                    f"claim #{i} ({field_name}): B-63: re-paired {moved} evidence quote(s) with "
                    f"the value each one supports"
                )
            ok, reason = check_claim(claim, page_text, corpus_texts=list(text_by_url.values()))
            if not ok:
                # B-40 (2026-09-27): before discarding the whole claim, see if it's a multi-value
                # claim where only SOME items failed -- if so, keep the verified subset instead of
                # losing every item to one bad one. check_claim_items() returns None for any shape
                # this doesn't apply to (a single-string value, or a single-line evidence string
                # on a list value), in which case this is exactly the pre-B-40 all-or-nothing
                # behaviour.
                item_results = check_claim_items(
                    claim, page_text, corpus_texts=list(text_by_url.values())
                )
                partial_claim = (
                    _filter_claim_to_verified_items(claim, item_results)
                    if item_results is not None else None
                )
                rejection_reason = reason
                if partial_claim is not None:
                    rejection_reason = (
                        f"{reason} (partial: kept {len(partial_claim.value)}/"
                        f"{len(claim.value)} item(s) that independently verified)"
                    )
                run.rejected.append(RejectedClaim(
                    field=field_name, reason=rejection_reason,
                    attempted_value=claim.value or "", attempted_evidence=claim.evidence or "",
                    source_url=claim.source_url,
                ))
                claim = partial_claim if partial_claim is not None else _not_found_replacement(
                    field_name, pages_checked=len(llm_pages)
                )
            if (claim.status in (Status.extracted, Status.inferred)
                    and claim.field == "products.delivery_model" and isinstance(claim.value, str)):
                # B-81: keep the category, drop any bracketed detail the quote does not mention.
                trimmed, dropped = trim_delivery_model_details(claim.value, claim.evidence)
                if dropped:
                    data = claim.model_dump()
                    data["value"] = trimmed
                    # B-91: the note must not keep stating the details just removed.
                    data["notes"] = trim_note_details(claim.notes, dropped, trimmed)
                    claim = Claim(**data)
                    run.schema_errors.append(
                        f"claim #{i} ({field_name}): B-81: dropped detail(s) not in the evidence "
                        f"quote: {', '.join(dropped)} (value now {trimmed!r})"
                    )
            if claim.status in (Status.extracted, Status.inferred):
                # B-77: the evidence check may have found a quote on another crawled page (B-36
                # fallback); cite the page the evidence is actually on. Acceptance is unchanged.
                cited_key = normalize_url(claim.source_url)
                home, note = evidence_home(claim, cited_key, text_by_url)
                if home is not None:
                    target = page_by_key[home]
                    data = claim.model_dump()
                    data["source_url"] = target.url
                    if claim.page_title is not None:
                        data["page_title"] = target.title
                    claim = Claim(**data)
                    run.schema_errors.append(
                        f"claim #{i} ({field_name}): B-77: evidence is on {target.url}, not on the "
                        f"cited {cited_key}; source_url re-pointed"
                    )
                elif note:
                    run.schema_errors.append(f"claim #{i} ({field_name}): {note}")

        elif claim.status == Status.conflicting:
            # B-06/EVD-05 (2026-09-27): conflicting claims used to reach here completely
            # unchecked -- see check_conflicting_claim()'s docstring. Its two values legitimately
            # come from two different pages, so it's verified against the whole crawled corpus
            # rather than one fixed source_url the way check_claim() works above.
            ok, reason = check_conflicting_claim(claim, list(text_by_url.values()))
            if not ok:
                run.rejected.append(RejectedClaim(
                    field=field_name, reason=reason,
                    attempted_value=claim.value or "", attempted_evidence=claim.evidence or "",
                    source_url=claim.source_url,
                ))
                claim = _not_found_replacement(field_name, pages_checked=len(llm_pages))

        if claim.status in (Status.extracted, Status.inferred, Status.conflicting):
            # B-89: record each quote's own page when they are not all on the one page source_url
            # names, so the ledger and the rendered page can show every source. Records only: the
            # claim was already accepted above, by the unchanged evidence check.
            cited = normalize_url(claim.source_url) if claim.source_url else ""
            located = quote_sources(claim, cited, text_by_url)
            if any(entry["pages"] != [cited] for entry in located):
                run.evidence_sources[claim.claim_id] = [
                    {"quote": e["quote"], "urls": [page_by_key[k].url for k in e["pages"]]}
                    for e in located
                ]

        run.claims.append(claim)

    # A field the model skipped entirely is still an honest gap, not a silent omission.
    for f in FIELDS:
        if f not in seen_fields:
            run.schema_errors.append(f"model did not return a claim for '{f}'")
            run.claims.append(_not_found_replacement(f, pages_checked=len(llm_pages)))

    # B-07/OUT-04 (2026-09-27): dated company-reported announcements, entirely separate from the
    # 15 fields above -- see module docstring and wi/schemas/announcement.py. No not_found
    # backfill here: unlike FIELDS, there is no fixed slot an announcement corresponds to, so a
    # site with genuinely zero announcements simply produces an empty list, and an invalid or
    # unverifiable one is dropped (logged to rejected_announcements) rather than replaced.
    for i, raw in enumerate(raw_announcements):
        data = dict(raw)
        data["announcement_id"] = f"{slug}:announcement:{i}"
        data["retrieved_at"] = retrieved_at  # deterministic, never trust the model's date

        try:
            announcement = Announcement(**data)
        except ValidationError as e:
            run.schema_errors.append(f"announcement #{i}: {e.errors()[0]['msg']}")
            run.rejected_announcements.append(RejectedAnnouncement(
                reason=f"schema validation failed: {e.errors()[0]['msg']}",
                attempted_text=raw.get("text"), attempted_evidence=raw.get("evidence"),
                source_url=raw.get("source_url"),
            ))
            continue

        page_text = (
            text_by_url.get(normalize_url(announcement.source_url), "")
            if announcement.source_url else ""
        )
        if not quote_in_page(announcement.evidence, page_text):
            run.rejected_announcements.append(RejectedAnnouncement(
                reason="quote not found in page text",
                attempted_text=announcement.text, attempted_evidence=announcement.evidence,
                source_url=announcement.source_url,
            ))
            continue

        run.announcements.append(announcement)

    if cache is not None and fingerprint is not None:
        cache.set(fingerprint, _payload_from_run(run))

    return run
