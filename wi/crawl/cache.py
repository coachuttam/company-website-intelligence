"""Run-level cache for the extraction step (PRD CST-01 / B-17): "cache by content
fingerprint plus prompt, schema and model version. Reprocess only changed pages."

Scope decision (2026-09-26): the PRD's own wording imagines PER-PAGE caching -- skip
re-extracting only the pages that changed. The actual extraction call
(wi/extract/pipeline.py's extract_claims) doesn't work page-by-page though: it sends every
selected page to the model in ONE call that synthesises the whole claim set across all of
them at once, because a single field (e.g. a "conflicting" headquarters) can only be judged
by seeing every page together. Splitting that into independent per-page calls would be an
extraction-architecture change, not a caching change, so it's out of scope here.

What this module actually caches instead is the SITE'S extraction result as a whole, keyed
by a fingerprint of every page's cleaned content plus prompt_version, schema_version and
model -- config.yaml's cache.key already names exactly these ingredients. If every page's
content is byte-identical to a previous run under the same prompt/schema/model, the cached
claims are returned and the LLM is never called, which is what CST-01's acceptance criterion
and B-17 actually test ("an unchanged re-run makes 0 model calls"). It also makes B-21
("three runs on unchanged content give identical structure") trivially true, since the
second and third runs return the literal first result rather than a fresh model call that
could vary even at low temperature. If even one page's content changed, the fingerprint
changes and the whole site is re-extracted -- coarser than per-page reprocessing, but
correct, and upgradable to page-level later without changing the cache key format below.

Storage: one JSON file per fingerprint under data/runs/cache/. Expiry: config.yaml's
cache.max_age_days (default 30) -- a cache file past that age is treated as a miss and
overwritten, never trusted, matching the project's "prefer an honest recheck over stale
certainty" stance elsewhere (e.g. not_found over guessing).

EXTRACTION_LOGIC_VERSION (added 2026-09-27, real bug found during the Week 3 field-level
baseline): config.yaml's cache.key documents the fingerprint as "content_hash+prompt_version+
schema_version+model" -- but that's every INPUT to the model, not the deterministic Python code
around it (wi/extract/pipeline.py's claim assembly, wi/validate/evidence.py's quote/value
checks). A bug fix to THAT code -- B-29 (title text included in evidence search), B-30
(source_url normalisation before the evidence-text lookup), or any future one -- changes what
the checker does with the exact same page content, prompt, schema and model, so it does not
change the fingerprint at all. A site cached before such a fix stays cached, unaffected, until
its page content changes, config.yaml's schema/prompt/model version bumps, or 30 days pass --
whichever comes first. Found by exactly this: `data/runs/cache/*.json`'s stored `rejected`
entries for two dev-set sites (thoughtbot.com, bajajauto.com -- both cached 2026-09-26, before
this constant existed) have no `source_url` key at all, meaning they were written by a version
of RejectedClaim that predates B-30's addition of that field -- yet nothing about a routine
re-run of those sites would ever have revealed that the cached result might now be stale under
current code. This constant closes that gap: it is bumped whenever pipeline.py's or evidence.py's
logic changes in a way that could change output for identical input, and is folded into the
fingerprint alongside everything already there, so a logic fix reliably busts every previously-
cached site's result on its very next run rather than silently never taking effect.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Optional

from wi.crawl.clean import CleanPage
from wi.crawl.fetch import content_hash

# Bump whenever wi/extract/pipeline.py's claim-assembly logic or wi/validate/evidence.py's
# quote/value-checking logic changes in a way that could change output for identical
# page content + prompt_version + schema_version + model. See this module's docstring.
# History: 1 (implicit, pre-2026-09-27, every run before this constant existed) -> 2
# (2026-09-27, folded into the fingerprint for the first time -- this bump alone busts every
# site cached before today, which is the point: none of them were ever checked against this
# constant, so treating them all as stale-by-default here is correct, not overcautious) -> 3
# (2026-09-27, B-06/EVD-05: wi/extract/pipeline.py now calls the new check_conflicting_claim()
# for conflicting claims instead of skipping them entirely, and wi/schemas/claim.py now enforces
# a value/evidence shape on them -- a site whose cached "conflicting" claim was never actually
# checked must be re-verified under the new logic rather than trusted as-is) -> 4 (2026-09-27,
# same-day follow-up pass covering B-03/B-10/B-18/B-07: wi/schemas/claim.py now rejects the
# literal string "not_found" as an extracted/inferred value (B-10); wi/extract/pipeline.py now
# retries once on malformed model JSON instead of giving up immediately (B-18); wi/validate/
# evidence.py now guards against an inferred pricing.revenue_model claim asserting subscription
# from contact-sales-only evidence (B-03); and wi/extract/pipeline.py now parses, validates and
# evidence-checks a wholly new "announcements" output (B-07/OUT-04, see wi/schemas/
# announcement.py). All four change what the deterministic code does with the same page
# content/prompt/schema/model -- a site cached before today must be re-verified under this new
# logic, not trusted as-is) -> 5 (2026-09-27, the Basecamp pricing-format false negative:
# wi/validate/evidence.py's check_claim() now splits a multi-line `evidence` STRING paired with a
# list `value` into per-line fragments and matches each value entry against whichever fragment
# supports it, instead of requiring the whole joined string to be one contiguous quote -- see
# that module's docstring. This changes a real, previously-cached result: basecamp.com's
# `pricing.public_plans` claim was evidence-rejected and downgraded to not_found under the old
# logic on identical page content/prompt/schema/model, and must be re-verified -- and, going by
# the diagnosis, should now pass -- rather than served stale from cache) -> 6 (2026-09-27,
# B-36, the "CloseKnit Health" fix: check_claim() now falls back to searching every crawled
# page's text, not just the claim's own cited source_url page, when a quote isn't found there --
# see wi/validate/evidence.py's docstring. A previously-rejected claim whose quote is real but
# was cited under the wrong page (thoughtbot.com's traction.named_customers /
# customers.industries dev-set failures) must be re-verified under this new logic, not served
# stale as a not_found rejection from cache) -> 7 (2026-09-27, B-38: check_claim() now rejects an
# inferred pricing.revenue_model claim whose quote has no term even plausibly related to pricing
# or billing -- see wi/validate/evidence.py's docstring. Previously-cached inferred claims on this
# field (bajajauto.com's "product sales" from a market-cap fact, thoughtbot.com's "project-based"
# from a positioning statement -- both real, live over-inferences with zero evidentiary link to
# revenue) must be re-verified under this new logic, not served stale as accepted claims) -> 8
# (2026-09-27, B-40: a multi-value claim that fails check_claim() is no longer always replaced
# entirely with not_found -- wi/extract/pipeline.py now keeps whichever items independently
# verify via the new check_claim_items(), only falling back to a full not_found when nothing
# survives. A previously-cached full not_found rejection for a claim like temenos.com's
# traction.partnerships (2 of 3 partners were genuinely verifiable) must be re-run under this new
# logic to recover the items it wrongly discarded, not served stale from cache -- see
# wi/validate/evidence.py's docstring) -> 9 (2026-09-27, B-42: check_claim()'s multi-line
# evidence-string mechanism -- previously list-value-only -- now also applies to a plain-string
# value, checking each of its comma-split items against any real quoted line instead of
# requiring one quote to cover the whole compound string. A previously-cached rejection for a
# single-string claim like customers.segments, whose facts genuinely come from separate parts of
# a page, must be re-verified under this new logic rather than served stale as not_found -- see
# wi/validate/evidence.py's docstring) -> 10 (2026-09-27, B-44: two evidence-checking bugs found
# on the very first live confirmation run of B-42/B-43, fixed together -- _split_items() now
# splits a string value on semicolons first (never re-splitting a resulting item by comma) when
# any are present, so a multi-address value with internal commas (e.g. a 4-location headquarters
# joined by semicolons) isn't shredded into meaningless cross-address fragments; and
# value_supported_by_quote() now canonicalises a small, explicit set of renamed Indian
# cities (Bengaluru/Bangalore, Mumbai/Bombay, etc.) so a real synonym doesn't score as a
# hallucination-shaped overlap miss. A previously-cached rejection caused by either bug (seen
# live on innovaccer.com and razorpay.com's company_identity.headquarters) must be re-verified
# under this new logic, not served stale as not_found -- see wi/validate/evidence.py's
# docstring) -> 11 (2026-09-27, B-49: wi/extract/pipeline.py no longer discards a whole
# multi-value claim just because its value/evidence list lengths mismatch -- it truncates to
# the shared prefix and verifies that instead. A previously-cached not_found caused by this
# exact mismatch (confirmed live on gong.io/traction.certifications, razorpay.com/
# products.names, thoughtworks.com/products.names, customers.industries and
# traction.partnerships) must be re-verified under the new logic, not served stale -- see
# wi/extract/pipeline.py's module docstring).
# Bumped 11 -> 12 (2026-10-02): wi/validate/evidence.py's new products.names bare-label
# guard (_products_name_evidence_is_bare_self_repeat) rejects a list item whose evidence is
# just the value repeated back verbatim -- a cached pre-fix run could be serving a claim
# this new check would have rejected, so it must not be trusted as a hit.
# Bumped 12 -> 13 (2026-10-03, B-53): wi/validate/evidence.py's new
# company_identity.headquarters country-name guard can newly ACCEPT a claim the pre-fix
# checker rejected (e.g. razorpay.com's "Bengaluru, Karnataka, India") -- a cached
# not_found/rejected result from before this fix must not be trusted as still correct.
# Bumped 13 -> 14 (2026-10-04, B-56/B-57): quote_in_page() now ignores a joining comma or
# semicolon, and the revenue-model pricing-signal guard now recognises '/mo'-style per-period
# prices -- both can newly ACCEPT a claim the pre-fix checker rejected (e.g. simplestores.in's
# 'Business, 1,499/month', typeform.com's '379USD/mo after 14 days'), so a cached rejected
# result from before this fix must not be trusted as still correct.
# 15 (2026-10-06, B-59): the revenue-model pricing-signal guard now accepts "pricing",
# "consumption", "usage-based" and "metered" -- a previously rejected quote now passes, so a stale
# cached rejection would hide the fix. (B-60's locale skip changes which pages are fetched, and
# so already changes the content hash; no extra bump is needed for it.)
# 16 (2026-10-06, B-61): pricing pages' cleaned text now ends with a "Buttons and links on this
# page:" block of real self-serve / contact-sales labels. The raw HTML (and so the content hash) is
# unchanged but what the model and the gate see is not, so older cached results must not be reused.
# 17 (2026-10-06, B-63): a list claim's evidence quotes are re-paired with the values they support
# before the evidence check, so claims that used to be (partly) rejected for a shifted evidence list
# now pass; a stale cached rejection would hide the fix.
# 18 (2026-10-06, B-64): spelled-out numbers read as digits in the evidence check, and a one-line
# evidence string of several real quotes joined by "; " is checked piece by piece, so claims that
# were rejected for either reason now pass; a stale cached rejection would hide the fix.
# 19 (2026-10-06, B-67): the B-63 evidence re-pairing no longer borrows another item's bare label as
# a products.names quote, so a stale cached claim citing the wrong product would hide the fix.
# 20 (2026-10-07, B-77): a claim whose evidence the B-36 fallback found on another crawled page now
# cites that page instead of the one the model named, so a stale cached claim would keep the wrong
# source_url.
# 21 (2026-10-07, B-79): a not_found field's coverage now records the pages actually sent to the
# model instead of the model's own account, so a stale cached claim would keep the model's numbers.
# 22 (2026-10-07, B-81): products.delivery_model drops any bracketed detail its evidence quote does
# not mention, so a stale cached claim would keep the unsupported detail.
# 23 (2026-10-09, B-92): clean_page folds certification badge-grid labels back into the cleaned text,
# so what the model and the evidence gate see changes; a cached result would miss the new labels.
# 24 (2026-10-09, B-89): the pipeline records each quote's own source page(s) for claims whose quotes
# are spread over several pages, and the cache payload carries them; an older cached payload lacks it.
# 25 (2026-10-09, B-91): when B-81 trims delivery_model details, sentences of the note naming them are
# removed too, so a stale cached claim would keep a note that contradicts its value.
# 26 (2026-10-09, B-94): evidence lines found on no crawled page are removed from accepted multi-line
# evidence (and the removal noted), so a stale cached claim would keep the made-up lines.
EXTRACTION_LOGIC_VERSION = 26


def run_fingerprint(site_url: str, pages: List[CleanPage], config: dict) -> str:
    """content_hash + prompt_version + schema_version + model + EXTRACTION_LOGIC_VERSION.
    Order-independent in the pages (sorted by URL) so re-fetching the same site in a
    different page order still hits the cache."""
    page_fingerprints = sorted(f"{p.url}:{content_hash(p.text)}" for p in pages)
    combined = (
        "|".join(page_fingerprints)
        + f"|prompt={config.get('prompt_version', '')}"
        + f"|schema={config.get('schema_version', '')}"
        + f"|model={config.get('llm', {}).get('small_model', '')}"
        + f"|logic={EXTRACTION_LOGIC_VERSION}"
    )
    return content_hash(f"{site_url}|{combined}")


class RunCache:
    """Reads and writes cached extraction payloads (plain dicts -- wi/extract/pipeline.py
    owns the Claim/ExtractionRun serialisation, this module only persists bytes) under
    `cache_dir`, keyed by the fingerprint from run_fingerprint()."""

    def __init__(self, cache_dir: Path | str = "data/runs/cache", max_age_days: float = 30):
        self._dir = Path(cache_dir)
        self._max_age_s = max_age_days * 86400

    def _path(self, fingerprint: str) -> Path:
        return self._dir / f"{fingerprint}.json"

    def get(self, fingerprint: str) -> Optional[dict]:
        path = self._path(fingerprint)
        if not path.exists():
            return None
        age_s = time.time() - path.stat().st_mtime
        if age_s > self._max_age_s:
            return None  # expired: a miss, not a stale hit
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None  # a corrupt cache file is a miss, never a crash

    def set(self, fingerprint: str, payload: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path(fingerprint).write_text(json.dumps(payload), encoding="utf-8")
