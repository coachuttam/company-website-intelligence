# Progress log

Three lines at the end of every day: done, blocked, next.

## Week 1 checklist (gate on Day 5: one URL gives schema-valid output, every populated value has evidence)

- [x] Day 1  Repo skeleton, requirements, config.yaml
- [x] Day 1  Confirm LLM provider, key and Playwright permission with Abhishek -- provider/key resolved 2026-09-26: Uttam confirmed an `OPENAI_API_KEY` in `.env`, so `config.yaml`'s `llm.provider`/`llm.small_model` are now set (`openai` / `gpt-4o-mini`). Playwright permission (for the JS fallback) is still unconfirmed with Abhishek, but that feature stays off by default (`js_fallback_enabled: false`) so it isn't blocking anything.
- [ ] Day 1  Verify benchmark sites (eval/benchmark_sites.md) and commit the list -- verification done (see eval/benchmark_sites.md, checked 2026-09-26), but 2 items are still open before it can be locked: H5 Tata Motors needs swapping (robots.txt blocks the "about" page type, no pricing/customer content), and H10 is still "(you choose)" -- one candidate (romsportsacademy.com) was unreachable. Needs Uttam/Abhishek to pick replacements.
- [x] Day 2  Claim schema frozen in code (tag `schema-v1` once approved) -- gap found and fixed 2026-09-26: `pricing.revenue_model` was whitelisted for inference in claim.py but missing from fields.py's FIELDS entirely (PRD Section 4, Group D requires it as its own field). Now 15 fields, not 14. Tag `schema-v1` still not created -- do that once Abhishek re-confirms the freeze with this fix included.
- [x] Day 3  Hand-label companies 1 and 2 (eval/labels/) -- Basecamp and Darwinbox drafted 2026-09-26
- [x] Day 4  Hand-label companies 3 to 5 -- Zerodha, Bajaj Auto, thoughtbot drafted 2026-09-26. **All 5 labels are Claude-drafted, not independently researched** -- the PRD wants ground truth researched independently of the pipeline, and Claude is also building the pipeline. Each file's `review_notes` field flags this and any specific caveats found while researching (JS-rendering gaps on darwinbox.com, non-verbatim digit rendering on bajajauto.com, a mislabel I caught and corrected on bajajauto.com's certifications field). **Independent re-check completed 2026-09-27** (see the dated section below) using WebFetch/WebSearch against live pages -- a process genuinely separate from both the original drafting and the extraction pipeline's OpenAI calls. 4 real corrections found and applied; still recommend Uttam/Abhishek do a final human spot-check per the PRD's own independence requirement, since this re-check was still done by Claude, not a human.
- [x] Day 4  Behaviour list reviewed (tests/BEHAVIOURS.md) -- confirmed against the real PRD Appendix B text 2026-09-26: all 25 PRD behaviours (B-01 to B-25) match exactly. One extra, B-26, was added for the crawl-priority-ordering fix (CRL-01) that predates the PRD's own list -- documented as an addition, not a PRD requirement.
- [x] Day 5  Baseline on one static site, then `python eval/check_gate.py <run.json>` -- run 2026-09-26 by Uttam against basecamp.com (D1) on his own machine (this session's sandboxed network can't reach api.openai.com or live sites, so the run itself has to happen outside it): `python -m eval/check_gate.py` reported **15 claims, 15 schema-valid, 8/8 populated claims have evidence -- PASS**. 36,173 tokens (34,911 prompt + 1,262 completion), 12.9s, `gpt-4o-mini`. See the "Day 5 baseline findings" note below the checklist for what the run surfaced and the one prompt fix it led to.

### Day 5 baseline findings (2026-09-26, basecamp.com, gate: PASS)

The gate passed, but 3 of the 15 fields were downgraded to `not_found` by the pipeline's own
safety nets rather than the model's own `not_found` judgment -- worth recording since it's the
first real signal from a live run, not synthetic test data:

- `products.delivery_model` -- the model's `evidence` didn't match anything in the actual
  crawled page text, so the evidence check correctly rejected it. Root cause found and fixed:
  `wi/extract/prompt.py`'s own worked example for this exact field used real basecamp.com text
  almost verbatim (it had been written earlier to reproduce a real bug on this same site), and
  the model appears to have echoed that example instead of quoting the page it was actually
  given this run. Since basecamp.com is a permanent benchmark site, this exact field+company
  pairing would keep recurring. Fixed by rewriting the rule 7 and rule 8 worked examples to use
  a generic, fictional product instead -- same teaching point, nothing real for the model to
  copy from its own instructions. Added `test_system_prompt_worked_examples_do_not_name_a_real_benchmark_site`
  (tests/test_prompt.py) so a future prompt edit can't reintroduce this.
- `customers.industries` -- evidence check correctly rejected a list of specific industries
  ("engineering, marketing, manufacturing, ...") whose only quoted support was "used in over
  100 countries ... across every industry imaginable" -- a real over-claim the model made, not
  a bug in the checker.
- `customers.segments` -- the model returned a JSON array for this field even though it's
  single-string in `fields.py` (not in `MULTI_VALUE_FIELDS`) and the prompt says so explicitly
  (rule 5). The schema validator caught it and the pipeline safely replaced it with `not_found`
  rather than crashing or silently keeping a malformed claim -- the defense-in-depth working as
  designed. This looks like occasional model non-compliance rather than an ambiguous field
  definition (all 5 hand-labelled dev-set companies already model `customers.segments` as one
  descriptive sentence, matching the current design). Worth watching across more runs in Week 3
  tuning; no code change made for this one.

Net: the gate's bar (schema-valid, evidence on every populated claim) is a floor, not a
ceiling -- it doesn't require this run's 7 `not_found` fields (headquarters, delivery_model,
segments, industries, named_customers, certifications, partnerships -- 8/15 populated) to be
few, only that whatever *is* populated is honestly evidenced. That's real signal that Week 3's
prompt/field tuning has material headroom, not a reason to doubt the PASS.

### Multi-site baseline runs (2026-09-26, all by Uttam on his own machine)

With a working key, Uttam ran the same baseline against the rest of the dev set to get more
than one data point before Week 3 tuning. Status of each:

- **Darwinbox** -- gate technically PASSED (15 schema-valid, 1/1 populated claim evidenced),
  but only `company_identity.name` came back populated; everything else `not_found`. This is
  exactly what `eval/benchmark_sites.md` predicted for this site (JS-heavy, raw fetch returns
  mostly nav/metadata) -- confirmed live: only 3 pages were even discoverable via static
  fetch (a React SPA shell has almost no crawlable links in its raw HTML), each under 250
  chars of real text. This is the real-world case `js_fallback_enabled` (B-16) exists for.
  Decided with Uttam: finish the rest of the dev-set baseline first, then come back and test
  the JS fallback specifically on this site (needs `pip install playwright && playwright
  install chromium` plus flipping the config flag) as a dedicated follow-up.
- **Zerodha** -- gate PASSED: **15 schema-valid, 6/6 populated claims evidenced** (18,986
  tokens, 12.3s). Two things from the run worth noting even though it passed: a schema issue
  on `products.names` (8 evidence quotes paired with only 4 values -- the array-pairing rule
  violated, caught and safely downgraded), and `company_identity.name` itself rejected
  (claimed "Zerodha" backed by an unrelated quote about discount broking). See the
  `company_identity.name` pattern noted under thoughtbot below -- this was the first instance
  of it.
- **thoughtbot** -- gate PASSED but weak: **15 schema-valid, only 2/15 populated claims
  evidenced** (15,442 tokens, 11.3s) -- 6 claims failed the evidence check. Two are the safety
  nets doing exactly their job (a `products.names` item paired with an unsupporting quote; an
  `customers.industries` value ("healthcare") not actually named in its quote). But
  `company_identity.name` failed again here too -- claimed "thoughtbot" against a completely
  unrelated "purpose and values" quote -- the same field that also failed on zerodha.com. That
  makes it 2 of 4 successful runs where arguably the single easiest field on the whole schema
  got rejected. Investigated and found a real, testable gap regardless of whether it's the
  exact cause here: `wi/extract/prompt.py` shows the model both a page's `<title>` and its
  body TEXT for every page, but `wi/extract/pipeline.py`'s evidence check only ever searched
  body text -- a legitimate quote drawn from a page's title (almost always exactly where a
  company's own name appears) was unfindable by construction and got rejected as if
  fabricated. Fixed: `_page_text_by_url` now includes the title alongside the body text for
  evidence-checking purposes (BEHAVIOURS.md B-29, new test in test_pipeline.py). Also
  suspicious and *not* explained by the title fix: `traction.named_customers` rejected
  "CloseKnit Health" with evidence "CloseKnit Health" verbatim -- the exact same string as
  both value and quote, still reported "not found in page text". Worth a closer look in Week
  3 (possibly a case-study page whose client name only appears in a logo image, never in
  actual text or title, which would make this a legitimate rejection rather than a checker
  bug -- unconfirmed, this session can't fetch the live page to check).
- **Bajaj Auto** -- first attempt **crashed**, not just downgraded: `openai.BadRequestError:
  context_length_exceeded` (158,814 tokens against gpt-4o-mini's 128,000-token limit), no
  output file written at all. Root cause: bajajauto.com's owner's-manual pages link straight
  to CDN-hosted PDFs, and the crawler had no concept of content-type -- it fetched 13 of
  those PDFs as if they were HTML pages (eating half the 25-page budget) and ran their binary
  bytes through the HTML cleaner as "text", each capped at 16,000 characters same as a real
  page. Fixed (content-type gate in fetch.py, B-27; actual enforcement of the already-declared
  `llm.max_input_tokens_per_run`, B-28 -- see below) and **re-run confirmed it**: 12 PDFs
  correctly skipped, 16,708 tokens (well inside budget), no crash, gate **PASSED**: 15
  schema-valid, 13/15 populated claims evidenced -- the strongest result of the whole dev set.
  Two claims still rejected: `pricing.sales_motion` (a real over-claim -- "direct sales
  through dealers" backed only by "Find dealer near you", correctly caught) and
  `company_identity.name` again -- claimed "Bajaj Auto", evidenced with the literal identical
  string "Bajaj Auto", still "quote not found in page text". An *exact* string match failing
  rules out a title/near-verbatim-matching explanation (B-29 above, already deployed, didn't
  stop this one) -- the only thing that reliably produces that exact symptom is the evidence
  checker being handed *empty* page text, which happens when a claim's `source_url` doesn't
  match any crawled page's URL at all (e.g. a trailing-slash difference between what the model
  reproduces and what `crawl_site` actually fetched and keyed its pages by). Fixed: the
  page-text lookup now normalises both sides with `crawl_site`'s own `normalize_url()` before
  comparing (B-30), and `RejectedClaim` now records the `source_url` the model claimed, so if
  this happens again the next run's output will show directly whether it's a URL mismatch or
  something else. Not yet re-confirmed against a live site (this fix landed after the last
  live run) -- worth a spot-check next time any dev-set site is re-run.

Dev-set baseline status: **all 5 sites run**, all gate PASS. Bajaj Auto's crash is fixed and
confirmed; Darwinbox's JS-fallback follow-up is now also confirmed working end-to-end (see
below) -- nothing deferred left in this baseline round.

### Darwinbox JS-fallback follow-up (2026-09-26)

Uttam installed Playwright (`pip install playwright && playwright install chromium`) and
flipped `crawl.js_fallback_enabled: true` in `config.yaml`, then re-ran darwinbox.com. Result:
byte-identical to the pre-fallback run -- `cache: hit`, 0 tokens, still only the same 3 pages
at 235/130/235 characters each, no "N JS-rendered" in the crawl summary. The fallback had not
fired at all, despite being enabled, despite Playwright being installed, and despite this being
exactly the thin-content case B-16 exists for.

Root cause: `wi/crawl/js_fallback.py`'s `visible_text_length()` -- the function
`needs_fallback()` uses to decide whether static content is "too thin" -- stripped only
`script`/`style`/`noscript` tags before counting text. Its own docstring claimed this was
"deliberately the same measure wi/crawl/clean.py's own fallback text extraction uses," but
`clean.py`'s actual fallback (`_fallback_text`) also strips `nav`/`header`/`footer`. The two
had silently drifted apart. On a real corporate SPA shell like darwinbox.com -- global nav,
footer link columns, cookie banner, language switcher -- the raw nav+footer boilerplate text
alone is comfortably over the `js_fallback_min_text_chars` default of 200, even though the real
cleaned content (what actually reaches the LLM, per `clean_page()`) was only 235 characters.
`needs_fallback()` was measuring the wrong thing and reporting "not thin enough" on a page that
plainly was.

Fixed (B-31): promoted `clean.py`'s `_fallback_text` to a public `extract_fallback_text`
(keeping `_fallback_text` as a backward-compatible alias, matching the `normalize_url`/
`_normalize_url` pattern already used this session in `fetch.py`), and rewrote
`visible_text_length()` to call it directly instead of maintaining a second, driftable copy of
the same tag-stripping list. Added `test_visible_text_length_ignores_nav_header_and_footer` and
`test_needs_fallback_true_for_nav_heavy_js_shell_at_default_threshold` to
`tests/test_js_fallback.py`, reproducing the Darwinbox shape (heavy nav/header/footer text,
near-empty real body) offline. Full suite: **141/141 passing** (up from 139).

Re-run #1 came back with only 1 page fetched and no successful fetch at all -- looked
alarming, but `run_site.py` was silently discarding the actual per-page fetch error, so there
was no way to tell a real code regression from a one-off live-site hiccup (bot detection after
several automated hits that day, a timeout). Added a diagnostic: when no pages fetch
successfully, each failed page's URL, `error_code` and `error` message are now printed instead
of just the generic "nothing to extract" line.

Re-run #2 (same day) fetched 2 pages successfully (235 / 130 chars -- home and /cortex, one
short of the earlier 3-page run, most likely ordinary crawl variance on a live site, not a
regression) but still showed no "N JS-rendered" in the summary -- meaning `needs_fallback()`
correctly triggered the fallback (B-31 confirmed working) but the actual Playwright render
still silently failed every time. `render_with_playwright()`'s blanket `except Exception:
return None` gave no way to see why.

Root cause (B-32): the function required Playwright's `page.goto(..., wait_until="networkidle")`
to succeed as a single step. `networkidle` demands the page go fully quiet -- no in-flight
network requests for 500ms -- which a real marketing site with a chat widget, analytics
beacons, or ad trackers polling in the background may never reach within the configured
timeout, even though the page has already loaded real, usable content by then. That single
strict wait was silently discarding an otherwise-successful render every time. Fixed: `goto`
now only has to reach `"load"` (the step that actually determines whether navigation
succeeded); a separate, best-effort `wait_for_load_state("networkidle", ...)` follows, but only
a timeout on *that specific wait* is swallowed -- any other failure (DNS, connection refused,
browser crash) still falls through to the original broad except and returns None. That broad
except now also prints the real exception to stderr instead of a silent None, so a genuine
future failure is diagnosable from the terminal instead of looking identical to "fallback not
needed." Added `test_render_with_playwright_still_returns_content_when_only_networkidle_times_out`
and `test_render_with_playwright_returns_none_when_load_itself_fails` to
`tests/test_js_fallback.py`. Full suite: **143/143 passing**.

Re-run #3 (bumped `js_fallback_timeout_s` from 15 to 30 first): `/cortex` still failed, but
now with a real diagnostic instead of silence -- `TimeoutError('Page.goto: Timeout 30000ms
exceeded... waiting until "load"')`. So this wasn't a "needed a longer timeout" problem at
all: `"load"` never fired even at 30s, because `"load"` requires literally every subresource
on the page (images, fonts, ad pixels, third-party tracking/chat-widget scripts) to finish,
and just one hung request -- a very common outcome when a headless browser trips some
anti-automation heuristic -- blocks it forever regardless of how long the timeout is. (The
homepage never even attempted the fallback this run, correctly -- its 235 real chars sit just
above the 200-char threshold, so `needs_fallback()` judged it didn't need Playwright at all.
Expected behaviour, not a bug.)

Fixed (B-33): made `"domcontentloaded"` (the document itself is parsed, DOM exists -- including
anything an SPA framework rendered into it by then) the only required wait, exactly the
condition CRL-04 actually needs. `"load"` and `"networkidle"` are now both best-effort
follow-ups after that, each independently swallowing only its own timeout (a `"load"` timeout
now skips trying `"networkidle"` too, rather than waiting out a second full timeout for no
benefit). Added `test_render_with_playwright_still_returns_content_when_load_and_networkidle_time_out`
and `test_render_with_playwright_returns_content_even_when_load_event_never_fires` to
`tests/test_js_fallback.py` (renamed/restructured the B-32 tests to share fixture helpers).
Full suite: **144/144 passing**.

Not yet re-confirmed against a live Darwinbox run -- this is the third fix in the same
JS-fallback chain (B-31: trigger measurement, B-32: networkidle resiliency, B-33: load
resiliency), each only found by actually running the previous fix against the real site.
Asked Uttam to re-run `python run_site.py https://darwinbox.com/` one more time.

**Re-run #4: CONFIRMED WORKING.** `domcontentloaded` got past the earlier timeouts. Result: 8
pages fetched (up from 3), 2 JS-rendered, budget exhausted (`max_pages` hit -- real navigable
links now exist because Playwright actually rendered the SPA shell). `/cortex` went from 130
static chars to **1745 rendered chars**. The crawl also picked up several priority pages that
were simply unreachable before (customer-success-stories, industry-recognition, about-us,
partner-with-us, contact-us -- all on `explore.darwinbox.com`, a subdomain only discoverable
once a rendered page's real nav links were present). Gate **PASSED: 15 schema-valid, 3/3
populated claims evidenced** -- small in absolute count, but the honest number is up from
Darwinbox's original 1/15, and there's now real content flowing through the pipeline for this
site instead of a near-empty shell. B-31/B-32/B-33 are all confirmed working end-to-end on the
real site that surfaced every one of them, not just in the offline regression tests.

One remaining page, `/experience-cortex`, still times out on `domcontentloaded` even now --
but this degrades exactly as designed (falls back to its original 41-char static content, run
continues normally) rather than blocking anything. Not investigated further; if it matters
later, the next hypothesis would be genuine bot-detection on that specific page rather than a
wait-condition problem, since domcontentloaded is about as lenient a wait as Playwright offers.

Two new, smaller things surfaced by this run, not yet acted on (noted for Week 3 tuning, not
urgent): (1) two schema pairing mismatches (`products.names` 26 values vs 2 evidence quotes,
`customers.industries` 4 values vs 1 quote) -- caught and safely downgraded by the existing
validator, same defense-in-depth as the Day 5 basecamp.com run; (2) `traction.named_customers`
partially rejected -- the value array parsed fine, but one evidence quote for "Yatra.com"
("Yatra.com's paperless onboarding transformation with Darwinbox") wasn't found in the page
text, possibly a smart-quote (’) vs straight-quote (') mismatch between what the model echoed
and the actual page markup, though unconfirmed.

## Week 2 checklist (gate: principal relevant pages found on 80%+ of dev sites, no uncontrolled crawling)

- [x] Duplicate-page dedup, normalised URL + content hash (CLN-01 / B-15) -- 2026-09-26
- [x] Redirect-cap reporting, distinguishable from other fetch errors (B-12) -- 2026-09-26
- [x] JS-only page fallback via Playwright, injectable/off by default (CRL-04 / B-16) -- 2026-09-26
- [x] Caching layer for unchanged sites -- whole-site fingerprint, not per-page (CST-01 / B-17, B-21) -- 2026-09-26; see wi/crawl/cache.py's docstring for why it's whole-site rather than the PRD's literal per-page wording
- [x] Realistic large-site page-cap test at the 10,000-page scale the behaviour names (B-14) -- 2026-09-26
- [x] Priority-ordered crawl so pricing/customers pages aren't starved out of the page budget (CRL-01, predates the PRD's behaviour list -- see B-26) -- 2026-09-25
- [x] Non-HTML content-type gate (linked PDFs/images no longer crawled as pages -- B-27) -- 2026-09-26, found on a real bajajauto.com run
- [x] Input-token budget actually enforced before the LLM call, never crashes on a real site's content volume (B-28) -- 2026-09-26, found on the same run; not a substitute for B-19 below
- [x] Evidence check accepts a quote drawn from a page's `<title>`, not just its body text (B-29) -- 2026-09-26, found after `company_identity.name` failed evidence on 2 of 4 live runs
- [x] Evidence-text lookup normalises `source_url` before comparing, and rejections now record the claimed `source_url` for diagnosis (B-30) -- 2026-09-26, found when B-29 alone didn't stop the same field failing on an exact-string match
- [x] Token/page limit breach -> partial profile with `limit_reached` flag (CST-03 / B-19) -- 2026-09-27, once wi/profile/ existed (see Week 3 checklist below)

All Week 2 items above are covered by tests (see tests/BEHAVIOURS.md for which test file covers which behaviour); `python -m pytest -q` passes 144/144 as of 2026-09-26 (B-31 added 2 tests, B-32 added 2 more, B-33 added 1 net new -- 2 renamed/restructured, 1 brand new).

## Week 3 checklist (gate: frozen schema/ledger/profile, schema and evidence-presence checks, field-level baseline, bounded optimisation trial)

- [x] Canonical profile assembly, `wi/profile/builder.py` (OUT-01's second output; unblocks B-19 above) -- 2026-09-27

### Canonical profile assembly, `wi/profile/` (2026-09-27)

OUT-01 asks for two separate outputs: the evidence ledger (claims -- already existed since
Week 1) and "a canonical profile that references claim IDs. The profile is derived from
validated claims, not from model prose." Only the ledger existed until now; nothing turned it
into the second, product-facing shape the PRD's Section 5 example and Section 6 reference page
both assume. B-19 (a limit breach returns "a partial profile with `limit_reached`") was blocked
on this the whole time -- there was no profile to attach the flag to.

`wi/profile/builder.py`'s `build_profile(run, pages_scanned, retrieved_at, schema_version,
crawl_budget_exhausted)` is pure reorganisation of an already-validated `ExtractionRun` -- no
new extraction, no LLM call, nothing invented that isn't already a `Claim`. Design decisions,
none spelled out verbatim by the PRD, so recorded here as well as in the module's own
docstring:

- **Field-to-group mapping.** `wi/extract/fields.py`'s 15 fields (`"<prefix>.<short_name>"`)
  map onto the PRD Section 4/5 group names via a small `GROUP_MAP` (e.g. `pricing` ->
  `pricing_commercial`). The PRD's Section 4 lists more subfields per group than our frozen
  schema actually has (e.g. Products lists six subfields, we have two) -- the profile reflects
  schema-v1 as frozen, not the PRD's full illustrative list.
- **Populated fields only under their group heading.** A field's entry appears in
  `profile[group]` only when `extracted` or `inferred`. PRD Section 6 item 9 is explicit that
  `not_found` fields "live [in the gaps panel], not as empty cards."
- **Conflicting claims go to `gaps_conflicts`, not their group.** EVD-05 says a conflict must
  "never silently pick one" value -- showing one arbitrarily under the main heading would do
  exactly that to anyone not also reading the ledger. `gaps_conflicts` holds both `not_found`
  and `conflicting` fields, each referencing its claim_id so the full picture (both disputed
  values, with evidence) is one lookup away.
- **`evidence_support_rate`** (part of the coverage strip, PRD Section 6 item 2) is defined as
  `populated / (populated + rejected)` -- of everything the model backed with evidence and
  attempted, what fraction survived `wi/validate/evidence.py`'s deterministic check. A plain
  `not_found` (nothing attempted) is excluded from the denominator on purpose: it's an honest
  gap, not a failed verification, and including it would make the number measure extraction
  completeness instead of evidence trustworthiness. `None` (not 0) when nothing was attempted
  at all, so "nothing to measure" is distinguishable from "measured at zero."
- **`limit_reached`** (B-19) is true if either hard limit CST-03 names was actually hit:
  `run.dropped_pages` non-empty (the LLM input-token-budget guard, B-28, trimmed pages) OR the
  caller passes `crawl_budget_exhausted=True` (`wi/crawl/fetch.py`'s `CrawlResult
  .budget_exhausted` -- the crawl's own page/depth caps were hit). `wi/profile/builder.py` has
  no visibility into the crawl result itself, so `run_site.py` passes the second flag through
  explicitly.
- **Defensive, not fragile.** A field somehow missing a claim (shouldn't happen --
  `extract_claims()` guarantees one claim per field) is treated as `not_found` with
  `claim_id: null` rather than raising. A broken profile builder would be strictly worse than
  an honest gap.

Wired into `run_site.py`: `retrieved_at` is now computed once and passed to both
`extract_claims()` and `build_profile()` (previously each would have called `date.today()`
separately, a real if rare way for the ledger and profile to silently disagree across a
midnight boundary). The output JSON keeps its existing top-level `"claims"` key unchanged (so
`eval/check_gate.py` and any existing run.json consumer needs no changes) and adds `"profile"`,
`"schema_version"` and `"limit_reached"` alongside it.

16 new tests in `tests/test_profile.py`: field-to-group placement (populated/inferred/
not_found/conflicting), a "living contract" test that every `FIELDS` prefix has a `GROUP_MAP`
entry (fails loudly if a 7th group is ever added without updating this file), coverage-count
correctness, both `evidence_support_rate` cases (measured vs. nothing-attempted), all three
`limit_reached` cases, schema-version stamping, JSON round-tripping, and one end-to-end test
through a real `extract_claims()` call (fake completer, no network). Full suite: **160/160
passing**. **Confirmed live 2026-09-27** against a fresh (uncached) darwinbox.com run -- see the
Log row below for the real numbers.

### Field-level accuracy baseline, `wi/eval/scoring.py` + `eval/baseline.py` (2026-09-27)

Week 3's second workstream (Section 10: "field-level baseline. One bounded DSPy or
prompt-optimisation trial, only after the baseline exists"). `wi/eval/scoring.py` is pure,
LLM-free comparison logic implementing the PRD's Section 12 scoring table exactly (Correct /
Incorrect / Correct abstention / Miss / Unsupported), plus one documented addition: a system
`conflicting` claim gets its own `Verdict.CONFLICTING` bucket rather than being forced into
Correct or Incorrect, because AC-11 asks for "conflict handling" to be reported *separately* from
extraction/inference accuracy -- folding it into Correct/Incorrect would contradict that. Value
comparison ("after normalising") is casefold + strip + collapse-whitespace for strings, and the
same applied item-by-item to an order-independent set for lists -- a deliberately literal, **not**
paraphrase-aware reading, documented in the module as a real scoring limitation, not an oversight
(see below). `eval/baseline.py` pairs each of the 5 dev-set hand-labels with its already-produced
`data/runs/*.json` (explicit label-file/run-file table, not guessed from the label's URL, since a
run's slug depends on crawl-time redirects -- zerodha.com's run is `www_zerodha_com.json`).
21 new tests in `tests/test_scoring.py`. Full suite: **181/181 passing**.

**Ran it against the real 5-site dev set (2026-09-27) -- first real numbers, well under target:**

| | correct | correct_abstention | incorrect | miss | unsupported | conflicting | accuracy |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Overall (75 field-checks) | 3 | 18 | 20 | 28 | 6 | 0 | **28%** |

Extraction accuracy (AC-11): 21%. Inference accuracy (AC-11): 0% (every one of the handful of
`inferred` claims scored, scored `incorrect` against strict normalising). AC-02's target is 80%
"across the agreed core fields" -- 28% is nowhere close, which is exactly why the PRD requires
this baseline *before* any prompt-optimisation trial rather than tuning blind. Per-field range:
best were `company_identity.headquarters` (80%), `pricing.free_trial` and
`comparisons.named_alternatives` (60% each); worst were `company_identity.description`,
`products.names`, `products.delivery_model`, `customers.segments` and `pricing.revenue_model`,
all at 0%. Full breakdown and every non-correct field's label-vs-system detail is in
`eval/baseline_report.json` (device-only, like `data/runs/*.json` -- generated from real API
output, not duplicated into the sandboxed scratchpad copy of this repo).

Reading the 0%s and misses, four different things are being blended into that one 28% and need
to be told apart before deciding what (if anything) to tune:

- **Strict scoring, not necessarily a real gap.** Free-text fields (`company_identity.description`,
  `products.delivery_model`, `customers.segments`, the prose pricing fields) score `incorrect`
  whenever the model's wording differs at all from the label's, even when substantively right --
  e.g. label "Online platform to invest in stocks..." vs system "Online platform to invest in
  stocks..." (zerodha) differ only by one trailing clause the label added. This is the documented,
  deliberate cost of not doing paraphrase matching (see module docstring) -- it may be overstating
  how wrong the model actually is on these fields specifically.
- **No partial credit on list fields.** A list field where the system found a true subset of the
  label's list (e.g. `bajajauto/products.names`: system found 6 of 12 real product names, all
  correct as far as they went) still scores a flat `incorrect` against the full-set comparison.
  Real under-coverage, but the current metric can't distinguish "found nothing" from "found half."
- **A recurring evidence-check rejection on easy fields -- new finding, not yet investigated.**
  `company_identity.name` -- arguably the single easiest field -- was downgraded to `not_found`
  via a `replacement:` claim (the pipeline's existing evidence-rejection safety net) on 3 of 5
  sites: zerodha, bajajauto, thoughtbot. Same class of bug as B-29/B-30 (evidence-quote lookup
  failing on genuinely correct claims), but recurring on different sites after those fixes landed.
  The original rejection reason isn't in the run's saved JSON (only printed to stdout at run time,
  and these 4 runs predate this baseline script), so root cause is unknown until re-run with that
  captured. Worth investigating before any prompt trial, since it would otherwise be invisible to
  that trial too.
- **A real over-inference pattern on `pricing.revenue_model`.** 3 of 5 sites (darwinbox, bajajauto,
  thoughtbot) got an `unsupported` verdict here specifically: the label says `not_found` (the site
  genuinely gives no pricing/revenue information), but the system confidently `inferred` a revenue
  model anyway ("subscription", "sales of vehicles", "project-based"). `pricing.revenue_model` is
  in `INFERENCE_WHITELIST` for cases like "Contact sales implies sales-led, not self-serve
  subscription" (B-02/B-03) -- but inferring *any* revenue model from context alone, with no
  pricing signal on the site at all, looks like the model over-applying that license. A real,
  specific prompt-tuning candidate if a trial happens.
- **Genuine crawl-coverage misses, separate from the above.** Several `miss` verdicts are pages
  the crawler never visited at all (thoughtbot's pricing/services pages, zerodha's SEBI
  registration/certifications page, darwinbox's ~80-name customer list on a page outside the
  crawled set) -- a coverage problem, not an extraction or evidence problem.

### Diagnosing the `company_identity.name` rejection pattern -- and a bigger bug found along the way (2026-09-27)

Uttam asked to fix the recurring `company_identity.name` evidence-check rejection first, before
the prompt-optimisation trial -- the right call, since a baseline contaminated by a pipeline bug
isn't a baseline the trial's "measurable gain" can be trusted against. The original rejection
reasons for zerodha/bajajauto/thoughtbot weren't in `run_site.py`'s saved output (only printed
to stdout at run time), so a fresh live run looked like the only way to see them again -- but
`wi/extract/pipeline.py`'s `RunCache` payload already stores each rejected claim's field, reason,
attempted value and evidence (it's what B-17's caching writes to disk), so the original diagnostic
data was sitting in `data/runs/cache/*.json` the whole time. No re-run needed to read it:

- **zerodha**: `attempted_value="Zerodha"`, `attempted_evidence="We pioneered the discount
  broking model in India."`, reason `quote not found in page text`.
- **thoughtbot**: `attempted_value="thoughtbot"`, `attempted_evidence="Our team is driven by our
  purpose and values..."`, reason `quote does not support the value`.
- **bajajauto**: `attempted_value="Bajaj Auto"`, `attempted_evidence="Bajaj Auto"` (identical
  strings!), reason `quote not found in page text`.

thoughtbot's case is unambiguous and not a bug: `quote_in_page` succeeded (that sentence really
is on the page) but `value_supported_by_quote` correctly failed -- "thoughtbot" doesn't appear
anywhere in that quote. The model attached a real but irrelevant quote to its easiest field
instead of grounding the name with text that actually contains it. EVD-02 did exactly its job;
the fix for this (if worth making) is a prompt-level nudge, not a code change, and belongs to
the bounded prompt-optimisation trial, not this fix.

zerodha and bajajauto are the concerning ones, especially bajajauto's exact-string match still
failing -- the same symptom B-30 was built to fix. But checking the raw cache file revealed why
it's unconfirmed either way: **both cache entries' `rejected` records are missing the
`source_url` field entirely**, proving they were written by the pipeline *before* B-30 added
that field to `RejectedClaim`. And that's the real, bigger bug: `run_fingerprint()`'s cache key
is `content_hash + prompt_version + schema_version + model` (config.yaml's own `cache.key`
documents exactly this) -- every INPUT to the model, but not the deterministic Python code that
checks the model's output. A fix to `wi/validate/evidence.py` or `_page_text_by_url()` changes
none of those four ingredients, so it can never bust a previously-cached site's result. Every
dev-set site has been sitting cached since 2026-09-26; B-29 and B-30 may or may not have actually
fixed zerodha/bajajauto's `company_identity.name` rejections, but a routine re-run would never
have told us either way -- it would have silently kept serving the pre-fix cached answer,
indefinitely (up to the 30-day expiry), with `cache_status: "hit"` looking exactly like success.

**Fixed:** added `EXTRACTION_LOGIC_VERSION` (`wi/crawl/cache.py`), folded into `run_fingerprint()`
alongside the four existing ingredients (now `content_hash+prompt_version+schema_version+model+
logic`, updated in config.yaml's `cache.key` comment too). Bumped 1 (implicit) -> 2 as part of
this fix, which makes every site cached before today unreachable under the new fingerprint --
correct, since none of them were ever checked against this constant, so treating all of them as
stale-by-default is the honest default, not overcaution. Going forward, any real fix to
extraction/evidence logic bumps this constant, and every affected site gets a fresh, honest
re-check on its very next run instead of possibly serving a stale answer with no visible sign
that anything is wrong. 2 new tests in `tests/test_cache.py` (fingerprint changes when the
constant changes; a cached entry becomes unreachable once it's bumped). Full suite: **183/183**.
This is B-34 in `tests/BEHAVIOURS.md`.

**Net effect for the baseline:** the 28% number from the last run may already be stale in ways
neither better nor worse than reality -- it's simply unverified against current code. The next
re-run of any dev-set site will, for the first time, genuinely exercise every evidence-checking
fix made this session (B-29, B-30, and this one) rather than risk quietly reusing pre-fix
results. Worth re-running all 5 dev-set sites and re-running `eval/baseline.py` before treating
28% as the number to beat.

### Real post-B-34 baseline: bajajauto's rejection was the caching bug, zerodha/thoughtbot's isn't (2026-09-27)

Uttam re-ran all 5 dev-set sites and `eval/baseline.py` after the config-sync incident was fixed.
Every site logged `cache: miss`, confirming B-34 forced the honest re-check it was built for.

**New result: 32% headline accuracy** (3 correct, 21 correct_abstention, 14 incorrect, 34 miss,
3 unsupported, 0 conflicting, of 75) -- up from the stale 28% (3, 18, 20, 28, 6, 0). Extraction
accuracy (AC-11) rose more sharply, 21% -> 30%; inference accuracy stayed at 0%.

The `company_identity.name` finding resolves cleanly into the two separate causes suspected
earlier:

- **bajajauto: CONFIRMED FIXED.** The field that originally exposed B-30 (claimed "Bajaj Auto",
  evidenced with the literal identical string "Bajaj Auto", still rejected as "quote not found in
  page text") now extracts cleanly -- evidence check passes, `cache: miss` proves it ran under
  current code, not a stale cache entry. It still scores `incorrect` in the baseline, but only
  because the label is "Bajaj Auto Ltd." and the system said "Bajaj Auto" -- a strict-string
  scoring quirk (a corporate suffix), not an evidence or extraction bug. B-30 + B-34 together are
  now validated live on the exact site/field that surfaced the original bug.
- **zerodha and thoughtbot: genuinely still rejected, confirmed NOT a caching artifact.**
  zerodha's run: claimed "Zerodha", evidence tried "We pioneered the discount broking model in
  India." -- a real quote, but one that never names the company. thoughtbot's run: claimed
  "thoughtbot", evidence tried "Our company" -- again real, again silent on the actual name
  (different quote than the pre-B-34 run, same failure shape). Both are the same pattern as
  thoughtbot's originally-diagnosed case: the model reaches for a plausible-sounding real quote
  instead of one that actually contains the company name, and EVD-02 correctly rejects it. This
  is now a clean, evidence-backed prompt-optimisation target: 2 of 5 sites (40%) fail grounding on
  arguably the single easiest field on the whole schema.

Two more patterns confirmed live (not caused by caching, present under current code):

- **`products.delivery_model` at a flat 0%** across all 5 sites -- the model infers a generic
  label ("software as a service" x2, "manufacturing and distribution", another "software as a
  service") in place of each site's more specific, evidenced description every time. A second
  concrete over-generalisation pattern alongside `pricing.revenue_model`'s over-inference (still
  present too: bajajauto "vehicle sales" and thoughtbot "project-based", both `unsupported`
  against a `not_found` label -- confirmed under current code, not a caching artifact).
- **Crawl-coverage misses remain the largest single bucket** (34 of 75 field-checks) -- e.g.
  darwinbox's ~80-name customer list and most of its list-shaped fields (its js_fallback stayed
  off this run, `crawl.js_fallback_enabled: false` in config.yaml, so it's back to the pre-B-31
  3-page shell) and zerodha's SEBI registration/certifications page, neither an extraction nor an
  evidence-checking problem.

Net: the caching fix (B-34) did its job -- it separated one confirmed-fixed bug (bajajauto) from
two confirmed-still-real ones (zerodha, thoughtbot), on real, current-code data rather than a
guess. `pricing.revenue_model`'s over-inference and `company_identity.name`'s weak quote-grounding
are now the two best-evidenced candidates for the bounded prompt-optimisation trial (Week 3's
final piece); `products.delivery_model`'s over-generalisation is a third, freshly surfaced one.

### Bounded prompt-optimisation trial: rule 9, `company_identity.name` quote-grounding (2026-09-27)

Uttam picked `company_identity.name` grounding as the trial's target -- the PRD (Section 10)
allows exactly one bounded trial after the field-level baseline exists, and this session already
has the baseline (32%, post-B-34) plus a precise, confirmed-live diagnosis of the failure to
target: zerodha and thoughtbot both attach a real, on-topic quote to the name field that never
actually contains the company's name ("We pioneered the discount broking model in India." for
"Zerodha"; "Our company" for "thoughtbot"). No existing prompt rule said a real quote can still
fail to *support* a specific value if it never uses that value's own words -- which is exactly
what `wi/validate/evidence.py`'s `value_supported_by_quote()` already checks deterministically
(>=60% of the value's significant words must literally appear in the quote). The model was never
told this directly.

Change, kept deliberately narrow to stay within the PRD's "bounded" gate:

- **`wi/extract/prompt.py`**: added rule 9 (one paragraph) plus one worked example, following the
  established fictional-example convention (the Day 5 lesson: never reuse a real benchmark
  site's text or name in a worked example, since the model can echo it back on that exact site's
  own run -- `test_system_prompt_worked_examples_do_not_name_a_real_benchmark_site` already
  guards this and covers the new example automatically). Phrased to cover any specific
  name/proper-noun value, not only `company_identity.name`, since the same grounding failure
  could recur on `products.names` or similar fields, but the worked example is built around the
  diagnosed name-field case. No other rule, pipeline code, or schema touched.
- **`config.yaml`**: `prompt_version` bumped `"0"` -> `"1"`. This is not cosmetic -- it is exactly
  why `prompt_version` exists in `run_fingerprint()`'s cache key (the same reasoning as B-34's
  `EXTRACTION_LOGIC_VERSION`, but for the prompt text instead of the checking code). The 5
  dev-set sites are already cached under the current fingerprint from the last run; without this
  bump, a re-run with unchanged page content would silently serve the OLD prompt's cached
  answer (`cache: hit`) and never exercise rule 9 at all -- the trial would look like it ran and
  actually measure nothing.
- **`tests/test_prompt.py`**: one new plumbing test asserting rule 9's key phrase and the
  `company_identity.name` worked example are present in the built system prompt (these tests
  check the prompt's own text, per this file's docstring, not the LLM's response to it -- an
  actual accuracy verdict can only come from a live re-run). Full suite: **184/184**.

**Not yet measured live.** Per the PRD gate ("keep the optimisation only if held-out gain is
measurable and provenance is intact"): this rule is kept only if a re-run of the 5 dev-set sites
plus `eval/baseline.py` shows `company_identity.name`'s accuracy improve on zerodha and/or
thoughtbot without regressing any other field. Provenance is intact by construction -- rule 9
only changes which quote the model is told to prefer; `wi/validate/evidence.py` still verifies
every claim exactly as before, unchanged.

### Rule 9 trial result: no measurable gain, reverted (2026-09-27)

Uttam re-ran all 5 dev-set sites plus `eval/baseline.py` against the rule-9 prompt. Measured
against the PRD's own gate ("keep the optimisation only if held-out gain is measurable and
provenance is intact"), the result is a clean null:

- **thoughtbot: no effect at all.** The rejected `company_identity.name` claim is byte-for-byte
  identical before and after -- same claimed value ("thoughtbot"), same exact wrong evidence
  quote ("Our company"), same rejection reason. Rule 9 did not change this site's output in any
  detectable way.
- **zerodha: still rejected, different wrong quote.** The model stopped using the old quote ("We
  pioneered the discount broking model in India.") but the new one still doesn't contain
  "Zerodha" anywhere, so it still fails `value_supported_by_quote()`. Possible the rule nudged
  quote selection without fixing the underlying failure to find or prefer a genuinely
  name-containing sentence -- but zero sites flipped from rejected to correct, which is what the
  gate actually asks for.
- **bajajauto: unaffected either way**, as expected -- its `company_identity.name` fix was B-30 +
  B-34, unrelated to rule 9, and it scored the same before and after (correct extraction, scored
  `incorrect` only on the "Ltd." label-wording technicality).
- **darwinbox: not usable for judging this trial.** Its crawl failed entirely this run on an
  unrelated live-site read-timeout, not on anything rule 9 touches. Its data is excluded from the
  trial's evaluation rather than counted as a regression.

Headline accuracy moved 32% -> 31% and extraction accuracy 30% -> 17% on this re-run, but the
extraction-accuracy drop is confounded by darwinbox's crawl failure removing that site's
extracted claims from the count entirely -- it is not evidence that rule 9 made anything worse on
the sites it actually ran against. Even setting that confound aside, no evidence anywhere in this
run shows a gain: zero claims flipped from rejected to correct on the targeted field.

**Decision: revert.** Per the gate and the commitment recorded when this trial was designed
("kept only if a re-run shows a real, held-out gain... without regressing other fields"), rule 9
does not earn its keep. Reverted in this same session:

- `wi/extract/prompt.py`: rule 9 and its worked example removed; `SYSTEM_PROMPT` restored to its
  pre-trial 8-rule text (the docstring keeps a record of the trial and its result instead of
  describing a rule that no longer exists).
- `config.yaml`: `prompt_version` reverted `"1"` -> `"0"`.
- `tests/test_prompt.py`: `test_system_prompt_requires_the_name_itself_inside_the_quote()` removed.
- Full suite back to **183/183** (was 184/184 with rule 9's test).

**Why it likely didn't work (diagnostic hypothesis, not verified, not acted on)**: B-29 made page
`<title>` text part of the searchable/quotable page content, but the model may still not be
reliably treating a page's title as a candidate source for a name-field quote even when the
company's own name sits right there in the title tag. A more forceful instruction pointing the
model specifically at title text could be worth a future trial -- but the PRD frames this as "one
bounded trial," so that would need Uttam's explicit go-ahead as a separate, new trial rather than
a second attempt bundled into this one. Not pursued here.

Week 3's "one bounded prompt-optimisation trial" line item is now closed, with a documented null
result rather than a kept change -- an honest outcome per the PRD gate, not a failure to fix
something that needed fixing. Two other evidenced candidates from the same baseline
(`pricing.revenue_model` over-inference, `products.delivery_model` over-generalisation at a flat
0%) remain available if Uttam wants to spend further, separately-scoped effort here.

### Rule 9, take 2: "title-pointing" name-grounding, a second bounded trial (2026-09-27)

Given take 1's null result, Uttam chose to take a second, separately-scoped crack at
`company_identity.name` grounding rather than switch targets, this time addressing a different
candidate mechanism from the same diagnosis: `build_messages()` has always shown the model a
`TITLE: ...` line for every page, and a page's own `<title>` tag very often states the company's
name directly even on pages whose body text talks about the company without ever naming it --
exactly zerodha's and thoughtbot's failure shape in both the pre-trial baseline and take 1's
re-run. Take 1 only restated the evidence-support requirement in different words (measured, no
effect); take 2 instead tells the model directly where to look for a name-field quote.

Change, again kept narrow to stay within the PRD's "bounded" gate:

- **`wi/extract/prompt.py`**: added a new rule 9 (take 1's rule 9 is gone -- reverted, and this
  is a fresh rule reusing the same number since only one rule 9 exists at a time) instructing the
  model to check each page's TITLE line first for a name-field quote, with a worked example
  built around a fictional company whose title names it but whose body text doesn't. No
  evidence.py change needed -- B-29 already made title text checkable; this only tells the model
  to actually look there for this field type.
- **`config.yaml`**: `prompt_version` bumped `"0"` -> `"2"` (not back to `"1"`, take 1's now-dead
  value, to guarantee this trial's re-run can't collide with take 1's retired fingerprint and
  silently serve a stale answer cached under either prior version).
- **`tests/test_prompt.py`**: one new plumbing test checking the new rule's key phrase and the
  `company_identity.name` worked example are present in the built system prompt. Full suite:
  **184/184**.

**Not yet measured live.** Same PRD gate as take 1: kept only if a re-run of the 5 dev-set sites
plus `eval/baseline.py` shows `company_identity.name`'s accuracy improve on zerodha and/or
thoughtbot (a claim actually flipping from rejected to correct, not just a different wrong quote
as take 1 produced) without regressing any other field.

### Rule 9 take 2 measured: two back-to-back re-runs, wildly inconsistent result (2026-09-27)

Uttam ran all 5 dev-set sites plus `eval/baseline.py` twice in a row, same session, same code,
same `prompt_version: "2"` fingerprint (both logged `cache: miss` on every site). The two runs
disagree sharply on the exact field the trial targets:

- **Run A**: `company_identity.name` 20% (1 correct -- basecamp; 1 incorrect -- bajajauto's
  "Ltd." label-wording quirk; 3 miss -- zerodha, thoughtbot, darwinbox all evidence-rejected).
  zerodha's rejected quote ("Invest in everything Online platform to invest in stocks...") and
  thoughtbot's ("Our team is driven by our purpose and values...") -- thoughtbot's is
  byte-for-byte the same wrong quote as both the pre-trial baseline and take 1's failed re-run.
  Headline accuracy 31%, extraction accuracy 17% (darwinbox's crawl failed entirely this run on
  an unrelated live-site timeout, confounding the extraction-accuracy number same as take 1's
  measurement).
- **Run B** (immediately after, same 5 sites, same script): `company_identity.name` **80%** (4
  correct -- basecamp, zerodha, thoughtbot, darwinbox; only bajajauto still "incorrect" on the
  same "Ltd." label-wording quirk, not a real failure). zerodha and thoughtbot -- the two sites
  this whole trial exists to fix -- both extracted the name correctly this run. Headline accuracy
  35%, extraction accuracy 38%.

This is a real, reproducible-in-principle mechanism (title-pointing clearly *can* work -- Run B
proves the model will use it) but not yet a *reliable* one across runs. The two runs used
identical code, config, and page content (both crawls fetched the same 25 pages for basecamp/
zerodha/thoughtbot/bajajauto) -- the only thing that differs run to run is the model's own
sampling, and `config.yaml`'s `llm.temperature` is `0.1`, not `0`, so some non-determinism in
which quote the model picks for a given field is expected, evidently including whether it
follows rule 9's title-pointing instruction at all on a given call. Two data points isn't enough
to call this either "measurable gain" or "no gain" per the PRD gate with confidence -- it's
genuinely both, depending which run you look at.

Not yet decided: keep, revert, or gather more repetitions before deciding. No code/config change
made in response to this finding yet -- asked Uttam how he wants to proceed (see Log).

### Methodology bug caught before it corrupted the repeat-run measurement: cache hits aren't independent samples (2026-09-27)

Uttam agreed to run 3-5 more repetitions to get a real read on rule 9 take 2's reliability. The
very next run exposed a real problem with that plan: basecamp, darwinbox, zerodha, and thoughtbot
all logged `cache: hit` (0 tokens, 0.0s) -- only bajajauto logged `cache: miss` (its live crawl
picked up a slightly different duplicate/PDF count this time, changing its content fingerprint).
`wi/crawl/cache.py`'s whole-site fingerprint is `content_hash + prompt_version + schema_version +
model + logic` -- nothing in it changes between two back-to-back runs of an unchanged live site
under the same `prompt_version: "2"`. So this "third run" was not a third independent draw from
the model at all: for 4 of 5 sites it returned the *literal* payload written by the previous run
(Run B) verbatim, byte for byte -- confirmed by its `company_identity.name` per-field result
matching Run B's 80% exactly, correct=4/incorrect=1 with the identical per-site breakdown. Taking
this at face value would have looked like "the gain replicated," when it actually measured
nothing new.

This is precisely the caching behaviour CST-01/B-17 was built for (skip re-billing an unchanged
site) -- correct for its intended purpose, wrong for gauging the model's own run-to-run sampling
variance, which by definition needs a fresh model call every time. Fixed properly rather than
telling Uttam to manually delete cache files between runs: added a `--no-cache` flag to
`run_site.py` (`python run_site.py <url> --no-cache`), which passes `cache=None` through to
`wi.extract.pipeline.extract_claims()` -- already supported, skips both the cache read and the
cache write for that call, so a `--no-cache` run neither reuses nor pollutes the real cache. Kept
intentionally out of the automated test suite, consistent with `run_site.py`'s existing untested
status (it's a live-network/API entry point, not unit-testable the way the rest of the pipeline
is) -- verified instead by an `ast.parse` syntax check plus the full suite staying green (184/184,
unaffected since nothing in the tested pipeline changed). Told Uttam to re-run the remaining
repetitions with `--no-cache` so each one is a genuine independent sample.

### Rule 9 take 2, third genuine sample obtained ("Run C") -- 2 of 3 independent runs favour keeping it (2026-09-27)

Uttam's next re-run finally used `--no-cache` correctly: all 5 sites printed the
`(--no-cache: forcing a fresh LLM call...)` confirmation and logged `cache: miss`, so this is the
first confirmed-genuine repeat sample since the cache-contamination bug (previous section) was
caught and fixed -- two prior re-run attempts after Run B were both silent cache replays, not new
data. Call this **Run C**.

`company_identity.name` came back 80% (4/5 correct) -- basecamp, zerodha, thoughtbot, and darwinbox
all correct; only bajajauto incorrect, and for the same pre-existing, trial-unrelated reason as
every other run this session (the "Bajaj Auto Ltd." vs "Bajaj Auto" label-wording quirk, not an
evidence-rejection). Confirmed by checking that neither zerodha nor thoughtbot appear in Run C's
"worth a human spot-check" list for this field.

Tally across all three genuine (`--no-cache`-confirmed or, for Run A/B, `cache: miss`-confirmed)
independent runs, on the two sites the trial specifically targets:

| Run | zerodha | thoughtbot |
| --- | --- | --- |
| A | rejected (miss) | rejected (miss) |
| B | correct | correct |
| C | correct | correct |

Two things stand out. First, the mechanism never produces a mixed result across these two sites --
when it works it works on both simultaneously, and when it fails it fails on both -- consistent
with a single underlying cause (whether the model happens to draw on the TITLE line this sample)
rather than two independent per-site coin flips. Second, headline accuracy stayed in a stable band
across all three runs (31% / 35% / 36%), with no field showing a regression pattern attributable to
rule 9 -- the run-to-run movement is concentrated on the one targeted field, as intended, not
spreading noise elsewhere. 2 of 3 genuine independent runs show the fix working on both target
sites; 1 of 3 shows it failing on both -- a real, evidenced 1-in-3 failure rate on the exact
mechanism this trial exists to fix, not zero, but a majority in its favour. Decision on keep vs.
revert vs. gather more reps is Uttam's, per this session's established practice of not unilaterally
making genuinely-his calls; asked him directly rather than picking for him.

### Rule 9 take 2: KEPT. Week 3's bounded prompt-optimisation trial is closed (2026-09-27)

Uttam's decision, given the 3-run tally above: keep rule 9 take 2. Rationale as put to him: 2 of 3
genuine independent runs show the title-pointing mechanism working on both target sites at once,
the one failure (Run A) is real and not dismissed, but headline accuracy stayed in a stable band
across all three runs with no regression traceable to this rule anywhere else in the schema -- a
majority-favourable, evidenced result across independent repetitions, which is what the PRD's own
gate ("keep the optimisation only if held-out gain is measurable and provenance is intact") asks
for. No code change needed for this decision: rule 9 take 2 and `prompt_version: "2"` are already
in place on both the scratchpad and the device from when the trial was built, and both have stayed
untouched through every measurement run since. This closes Week 3's single-bounded-trial line item
per PRD Section 10 -- the PRD permits exactly one, and this was it (counting take 1 and take 2
together as one continuous trial on the same target field, per the scoping note in
`wi/extract/prompt.py`'s own docstring). The two other evidenced-but-unpursued candidates
(`pricing.revenue_model` over-inference, `products.delivery_model` flat 0%) remain openly recorded
as possible future work, not silently dropped, should Uttam want a genuinely new trial later.

### Sync-drift caught: `requirements.txt` had silently diverged (2026-09-27)

While preparing to sync an unrelated fix to the device, a routine pre-sync checksum check found
`requirements.txt` already differed between the scratchpad and the device -- the device had an
extra line, `lxml_html_clean>=0.4.0` (trafilatura's dependency chain needs it separately on newer
lxml versions), that Uttam had evidently added directly on the device at some point, which never
got round-tripped back into the scratchpad's copy. Exactly the same class of bug as the
2026-09-27 "config-sync incident" above (a device-side edit the scratchpad didn't know about),
just caught before it caused a live failure this time instead of after. Fixed by adding the
missing line to the scratchpad copy (the device side was already correct, so no device-side
change was needed); checksums confirmed matching on both sides afterward. No test impact --
`requirements.txt` isn't exercised by the test suite.

### B-06/EVD-05 fixed: conflicting claims were never evidence-checked at all (2026-09-27)

Uttam explicitly delegated the next-step choice ("pick one of the four candidates for a new
trial, or move to the older backlog items"). Decided against a fifth prompt trial: Week 3's one
bounded prompt-optimisation trial (PRD Section 10) is already spent and closed on rule 9 (see
above), so spending another now would exceed that budget rather than use it once as intended.
Picked **B-06** instead -- a concretely scoped, PRD-evidenced correctness gap, not a new trial,
consistent with this session's pattern of prioritising validation/correctness fixes (B-29
through B-34) over exploratory tuning when both are on the table.

**The gap.** EVD-05 requires: "Preserve conflicting values with evidence. Never silently pick
one." B-06's acceptance criterion: "Given two pages with different headquarters, status is
`conflicting` and both values are kept." In the actual code, `Status.conflicting` claims had
*zero* schema requirements (`wi/schemas/claim.py` required nothing at all for that status) and
were *never checked against real page text* -- `wi/validate/evidence.py`'s `check_claim()`
explicitly short-circuits `if claim.status in (Status.not_found, Status.conflicting): return
True, "no quote check needed"`, and `wi/extract/pipeline.py`'s verification loop only ever
called that function for `Status.extracted`/`Status.inferred`, never for `conflicting`. A
hallucinated "these two pages disagree" claim -- entirely invented, no real quotes at all --
would have sailed straight through to the profile output unverified. Confirmed via the real
`docs/PRD.MD` (device-only, read-only) wording before designing the fix, not just BEHAVIOURS.md's
paraphrase of it.

**The fix.** Rather than inventing a new shape for "value describing both" (which would itself
risk violating rule 7 -- never fabricate a sentence not verbatim on the page), reused the
*existing*, already-tested paired value/evidence array mechanism built for `MULTI_VALUE_FIELDS`
(2026-09-23/24), extended to `conflicting` claims on *any* field, not just ones on that list:

- `wi/schemas/claim.py`: a `conflicting` claim now must carry `value` as a list of >= 2 differing
  raw values (one per disagreeing page) and `evidence` as a matching list of one real quote per
  entry. Exempted from the `MULTI_VALUE_FIELDS` field-membership check specifically for
  `Status.conflicting` (a conflict inherently needs two values regardless of the field's normal
  shape); the exemption does not leak into `extracted`/`inferred`, which still enforce
  `MULTI_VALUE_FIELDS` exactly as before.
- `wi/validate/evidence.py`: new `check_conflicting_claim(claim, corpus_texts)` checks each
  `evidence[i]` against the *whole crawled corpus* (every page's text), not one fixed
  `source_url` the way `check_claim()` does for extracted/inferred -- a conflict's two values
  legitimately come from two different pages, and `Claim` only carries a single `source_url`
  field, so there's no one right page to check against.
- `wi/extract/pipeline.py`: added an `elif claim.status == Status.conflicting:` branch to the
  verification loop, calling the new check and downgrading to the safe not_found replacement
  (logged in `run.rejected`) on failure -- mirroring exactly how extracted/inferred claims are
  already handled, so a fabricated conflict is now caught and demoted just like a fabricated
  extraction always has been.
- `wi/extract/prompt.py`: reworded rule 2's `conflicting` bullet from a vague "value describing
  both, and evidence that shows the conflict" to a precise paired-array-format instruction
  (matching rule 6's existing multi-value array wording), with a new fictional worked example
  ("Bengaluru, India" / "Mumbai" headquarters -- checked against
  `test_system_prompt_worked_examples_do_not_name_a_real_benchmark_site`'s benchmark-site list to
  confirm no collision; that list screens company names, not city names).
- `wi/crawl/cache.py`: `EXTRACTION_LOGIC_VERSION` bumped 2 -> 3 (deterministic checking code
  changed -- same reasoning as B-34, which introduced this version field for exactly this
  purpose). `config.yaml`: `prompt_version` bumped "2" -> "3" (the text sent to the model also
  changed). Both bumps needed since this fix touched both halves of the cache fingerprint --
  every previously-cached site's result is now correctly forced to re-check under the new logic
  and prompt rather than silently serving a stale pre-fix result.

**Tests.** 6 new tests in `tests/test_claim.py` (shape enforcement: no value/evidence, single
string, only one value, evidence-length mismatch, list-value exemption for `conflicting` on a
non-multi-value field, and confirming the exemption doesn't leak into `extracted`). 4 new tests
in `tests/test_evidence.py` (`check_conflicting_claim`: real quotes on different pages pass;
fails against a single page missing the second quote -- the actual reason to check the whole
corpus rather than one page; a fabricated quote fails; a real quote paired with the wrong value
fails). 2 new tests in `tests/test_pipeline.py` (end-to-end: a genuine two-page conflict survives
the pipeline with both values kept; a fabricated conflict is downgraded to not_found and logged
in `run.rejected`, never silently kept). 1 new test in `tests/test_prompt.py` (the system prompt
specifies the paired-array format). `tests/BEHAVIOURS.md`'s B-06 row updated from `todo` to
`done`.

**4 pre-existing tests broke** against the new stricter schema and needed fixing, since they'd
constructed `conflicting`-status `Claim` fixtures using the old, now-invalid single-string shape:
`test_profile.py::test_conflicting_field_lands_in_gaps_conflicts_not_under_its_group`,
`test_profile.py::test_coverage_counts_populated_inferred_conflicting_and_not_found`,
`test_scoring.py::test_label_not_found_system_conflicting_is_also_unsupported`,
`test_scoring.py::test_conflicting_against_a_valued_label_is_its_own_verdict_not_correct_or_incorrect`.
Fixed by rewriting `test_profile.py`'s `_conflicting()` helper and `test_scoring.py`'s `_claim()`
helper's conflicting branch to produce valid paired-list shapes -- confirmed safe first by
checking neither test file's assertions actually depend on `value`'s exact string content (only
on `status`/`claim_id`/counts/verdict), so no test's actual intent changed, only its fixture's
shape.

Full suite: **197/197** (was 184, +13: 6+4+2+1 new tests), verified independently on both the
scratchpad and the device via a fresh throwaway venv on the device side. Checksums verified
matching on both sides for every changed file (`wi/schemas/claim.py`, `wi/validate/evidence.py`,
`wi/extract/pipeline.py`, `wi/extract/prompt.py`, `wi/crawl/cache.py`, `config.yaml`,
`requirements.txt`, and all 7 touched/added test and doc files).

A leftover patch script (`patch_b06.py`) used to apply the code/config changes to the device was
left behind in the project folder after `rm` failed with a permissions error; the follow-up
delete-permission request was declined, so it was moved to `_to_delete/patch_b06.py` in the
connected folder instead, for Uttam to delete himself.

### Independent re-check of the 5 hand-labels (2026-09-27)

Uttam picked this as the next backlog item to work through. The concern flagged since Day 4: all
5 dev-set labels (`eval/labels/*.json`) were drafted by Claude, the same assistant building the
extraction pipeline they score -- the PRD wants ground truth researched independently of the
pipeline, and a self-drafted answer key risks unconsciously matching the pipeline's own blind
spots rather than catching them.

**What "independent" means here.** A full human review is still the PRD's real ask and hasn't
happened -- that's unchanged by this session. What this pass adds is a genuinely separate
*process*: rather than re-reading the same draft, every populated field in all 5 label files was
checked against freshly fetched live pages via `WebFetch`/`WebSearch` (Anthropic's own browsing
tools, unrelated to the extraction pipeline's OpenAI calls or to whatever reasoning produced the
original draft), adversarially -- looking for whether the live site actually supports each claim,
not just whether the claim looks plausible. This is a real, evidence-based cross-check, not a
rubber stamp, but it's still Claude doing the checking, so a human spot-check (Uttam or Abhishek)
remains the recommended final step before treating these as locked ground truth.

**Result, company by company:**

- **Basecamp** -- every field confirmed accurate against fresh fetches. No corrections. Two
  things noted but deliberately left alone: `traction.certifications` lists only PCI DSS
  (excluding a CSA CAIQ self-assessment and an EDUCAUSE HECVAT toolkit response found on the same
  page, since both are self-assessments the company answers, not certifications issued to it --
  same reasoning as bajajauto.json's pre-existing award-vs-certification distinction);
  `traction.partnerships` lists 13 confirmed-real integration partners out of roughly 80 now
  listed on the live integrations page -- a genuine but non-exhaustive subset, not an error.
- **Darwinbox** -- **1 correction**: `company_identity.headquarters` was wrongly `not_found`.
  darwinbox.com/en-us itself never states an HQ, but the company's own newsroom subdomain
  (`newsroom.darwinbox.com`) explicitly announces a "Global Headquarters in Hyderabad" (a Nov
  2022 press release) -- now `extracted` as Hyderabad, India. Flagged for later scoring
  interpretation: this is a genuine first-party statement, but on a separate subdomain from the
  primary crawled site, so the *pipeline* not finding it would be a crawl-coverage gap, not
  necessarily an extraction bug. Also re-confirmed `traction.certifications` stays `not_found`
  (a second independent check found nothing first-party, strengthening confidence this isn't a
  rendering artifact) and confirmed the `comparisons.named_alternatives` blog page is real and
  on-topic. The ~76-name `traction.named_customers` list matched a re-fetch at roughly 97%
  (74/76) -- the handful of differing names look like logo-carousel rotation or lossy
  page-summarization rather than a real error, so left unchanged rather than edited on shaky
  grounds.
- **Zerodha** -- **1 correction**: registered address, SEBI/DP registration numbers, every named
  product, and every brokerage/AMC/DP fee line all matched the live site byte-for-byte. But
  `pricing.public_plans`' Kite Connect API line only listed the paid ₹500/month "Connect" tier;
  zerodha.com/products/api actually offers a free "Personal" tier alongside it -- both are now
  listed. Also confirmed `comparisons.named_alternatives` correctly stays `not_found` (the one
  comparison-flavoured page found refers to rivals only as "Other brokers," never by name).
- **Bajaj Auto** -- spot-checked 3 of 19 bike prices against the live `/bikes` page; all matched
  byte-for-byte including the unusual digit-grouping, which increases confidence in the full
  19-item list. Company name, HQ address, and description all matched exactly. Re-checked
  `traction.certifications` a second time (a fresh web search plus a direct fetch of the
  about-bajaj-group page) -- still nothing first-party, confirming the pre-existing
  award-vs-certification correction was right, not a miss. **1 correction**: `pricing.sales_motion`
  was wrongly `not_found` -- the `/bikes` page has a live "Book a Test Ride" call-to-action on
  every model, a real, stated sales mechanism (book online, then buy through an authorised
  dealer) -- now `extracted` rather than an abstention.
- **thoughtbot** -- description, delivery-model quote, and a 12-of-33 sample of named customers
  (Real Chemistry, Postmates, MoMA, Vimeo, Hilton, Disney, and others) all matched exactly.
  Confirmed `pricing.public_plans`/`free_trial`/`revenue_model` correctly stay `not_found` (an
  independent fetch of `/services` explicitly found no pricing or engagement-cost information
  anywhere), and confirmed the remote-first, no-stated-office pattern supports
  `company_identity.headquarters` staying `not_found` too. **1 correction**:
  `customers.industries` was missing "Technical and Business Assistance (TABA)", listed
  alongside Healthcare/Finance/Insurance/Government under the site's own industry-expertise
  heading -- added.

**Net effect**: 4 real corrections applied across 4 of the 5 label files (Basecamp needed none),
all additive (a `not_found` becoming `extracted`, or a list gaining an item the site actually
states) -- none reversed an existing `extracted` claim as wrong. Every `review_notes` field and
`labelled_by` field updated to record exactly what was independently checked, what changed, and
what remains a human-review item. All 5 files re-validated as parseable JSON, synced to the
device, checksums matched on both sides. `eval/labels/*.json` isn't read by the pytest suite
(only by `eval/baseline.py`, a live-run script) -- full suite re-confirmed **197/197**,
unaffected, on both scratchpad and device, as due diligence rather than because it was at risk.

Since two of the corrections (Darwinbox headquarters, Bajaj Auto sales motion) turn a field from
`not_found` to `extracted`, the next time `eval/baseline.py` is re-run against the existing cached
run outputs, those two fields will very likely flip from `correct_abstention` to either `miss` or
`unsupported` for the pipeline's own output on those sites (the pipeline almost certainly won't
have found either fact, especially the newsroom-subdomain headquarters) -- a real, expected
consequence of fixing the ground truth, not a regression to chase.

### Re-ran the baseline against the corrected labels (2026-09-27)

`eval/baseline.py` needs no LLM call -- it's pure comparison logic pairing each label with
whatever run JSON already sits in `data/runs/*.json` -- so this was run directly rather than
asking Uttam to do it.

**New result: 32% headline** (5 correct, 19 correct_abstention, 17 incorrect, 31 miss, 3
unsupported, 0 conflicting, of 75) -- extraction accuracy (AC-11) **36%**, inference accuracy 0%.

**Important caveat, so this isn't read as a clean "label-fix-only" delta**: `data/runs/*.json`
holds whatever each site's *most recent* real run left behind, and a lot happened to those files
between the last documented baseline (post-B-34, 32% headline / 30% extraction, prompt_version
`"0"`) and now -- specifically, every one of Uttam's `--no-cache` reps for the rule 9 take 2 trial
overwrote them, so the cached runs being scored here are already rule-9-take-2-era output
(prompt_version `"2"`) with `company_identity.name` already at its confirmed 80%, not the older
pre-trial runs. So today's number reflects *both* the corrected labels *and* an already-improved
pipeline, not the label fix in isolation -- there's no way to isolate the two from cached data
alone. None of this baseline's cached runs reflect the B-06 fix yet either (that bumped
`prompt_version` to `"3"` and `EXTRACTION_LOGIC_VERSION` to `3`, and no site has been re-run since).

Two things worth calling out despite the confound:

- **Headline accuracy is coincidentally flat at 32%** (same as the pre-correction/pre-rule-9
  post-B-34 number), but the underlying composition shifted: correct went 3 -> 5, incorrect went
  14 -> 17, miss went 34 -> 31, correct_abstention went 21 -> 19. More of the scored verdicts are
  now genuine correct/incorrect calls and fewer are abstention credit -- a byproduct of two label
  corrections (Darwinbox headquarters, Bajaj Auto sales_motion) turning a `not_found`-vs-`not_found`
  free pass into a real miss the pipeline should go find, exactly as flagged when those corrections
  were made.
- **Extraction accuracy's rise to 36%** is most plausibly rule 9 take 2 showing up in scoring for
  the first time (this is the first baseline run scored since that trial was kept), not the label
  corrections -- none of the 4 corrected fields had a system status of `extracted` in this run's
  cached data (all four are currently `not_found` on the system side), so they don't enter
  `extraction_vs_inference()`'s denominator at all.

Per-field: `company_identity.name` 80% (matches the rule 9 take 2 tally exactly), `headquarters`
and `comparisons.named_alternatives` 60-80%; `company_identity.description`, `products.names`,
`products.delivery_model`, `customers.segments`, `pricing.sales_motion` all still 0%. Full detail
in `eval/baseline_report.json` (device-only, regenerated by this run).

**The clean next step**, if a genuinely current number is wanted: re-run all 5 dev-set sites
fresh (any run now forces a real re-check anyway, since `prompt_version`/`EXTRACTION_LOGIC_VERSION`
both bumped for B-06) and re-run `eval/baseline.py` against that -- that would be the first number
reflecting corrected labels, rule 9 take 2, *and* B-06 all at once, with no confound left.

### The clean baseline: corrected labels + rule 9 take 2 + B-06, all together, no confound (2026-09-27)

Uttam re-ran all 5 dev-set sites fresh in his own terminal (this sandbox still can't reach
`api.openai.com` -- confirmed again with a direct connectivity check before asking him, rather
than assuming). All 5 logged `cache_status: "miss"` -- confirmed genuine re-checks, exactly what
B-06's `EXTRACTION_LOGIC_VERSION`/`prompt_version` bump was built to force. `eval/baseline.py`
needs no LLM call, so it was run directly rather than asking Uttam to do that too.

**Result: 31% headline** (5 correct, 18 correct_abstention, 17 incorrect, 31 miss, 4 unsupported,
0 conflicting, of 75). Extraction accuracy (AC-11) 36%, inference accuracy 0%. This is the first
number with no confound left -- corrected labels, rule 9 take 2 (`company_identity.name` still at
its confirmed 80%), and the B-06 fix are all reflected in the same set of genuinely fresh runs.

Versus the previous (confounded) 32%/36% read: nearly identical, with a 1-point headline dip (32%
-> 31%) from `comparisons.named_alternatives` losing one `correct_abstention` to `unsupported` on
a fresh sample -- ordinary run-to-run model variance at `llm.temperature: 0.1`, not a regression
introduced by any of this session's fixes.

One field is worth calling out as a direct, positive confirmation that the hand-label review was
worth doing: `bajajauto/pricing.sales_motion` now scores `incorrect` rather than `miss` --
the corrected label ("Dealer-led: customers book a test ride online, then complete purchase
through an authorised dealer") and the system's fresh output ("direct sales through dealers")
are saying essentially the same thing in different words, but strict string normalising still
marks it wrong. Before the correction this field was invisible to scoring entirely (a
`not_found`-vs-`not_found` free pass); now it's visible as exactly the kind of strict-scoring
free-text noise flagged as a real, separate limitation back when `wi/eval/scoring.py` was built --
not a new problem, just one the old mislabel had been hiding.

Crawl-coverage misses remain the largest single bucket (31 of 75) -- still untouched, still the
top open item if headline accuracy is the thing to move next.

### B-01/02/03/07/08/10/18 behaviour-testing pass (2026-09-27)

Uttam picked this cluster of 7 individually-tracked PRD behaviours next. Investigated each
against the current codebase and the device-only PRD text before writing any code, to correctly
triage "already correct, just needs a test" from "genuine implementation gap." Three turned out
to be the former, four the latter.

**Already correct, confirmation tests only added (no code changes):**
- **B-01** (pricing page: plan amounts/currency/period captured with the quote) -- already
  satisfied by `pricing.public_plans`' existing free-text list design (from the basecamp.com
  multi-span fix, 2026-09-23). New dedicated pipeline test in `test_pipeline.py`.
- **B-02** ("Contact sales" + no amounts -> `sales_motion` inferred sales-led, `public_plans`
  `not_found`) -- already satisfied by `pricing.sales_motion` already being in
  `INFERENCE_WHITELIST` and the existing not_found path. New dedicated pipeline test.
- **B-08** (no customer evidence -> `named_customers` `not_found` with coverage) -- already
  satisfied by the existing EVD-04 coverage requirement on `not_found`. New dedicated pipeline
  test.

**Genuine gaps, fixed:**

- **B-10** (mixed forms: bare value / `null` / literal `"not_found"` string, all rejected) --
  2 of 3 sub-cases were already correctly rejected by existing Pydantic/required-field logic
  (a missing `status` fails the enum's own required check; a `null` value already fails the
  pre-existing "claim is missing 'value'" check). The 3rd sub-case was a real, previously
  unguarded gap: nothing stopped an `extracted`/`inferred` claim from using the literal string
  `"not_found"` (or `"not found"`) as its `value` -- self-contradictory (claiming a value while
  stating there is none) but schema-valid before this fix, since it's just an ordinary non-empty
  string to every earlier check. Fixed with a new rule in `wi/schemas/claim.py`'s
  `_evidence_rules`, checked case/underscore-insensitively and per-item when `value` is a list.
  4 new tests in `test_claim.py` (one per sub-case, plus the list-item case).

- **B-18** (malformed model JSON -> one corrective retry, then `not_found`) -- confirmed a real,
  well-scoped gap: `wi/extract/pipeline.py`'s `extract_claims()` fell straight back to
  all-`not_found` on the first parse failure, no retry at all. Fixed by adding exactly one
  additional `completer.complete()` call when the first response fails to parse, with retry
  messages built as `[original messages..., the bad assistant response, a corrective user
  message spelling out the required shape]`. `run.usage` now reports the SUM of both calls'
  tokens/elapsed time when a retry happens (both are real cost). If the retry also fails,
  behaviour is unchanged from before (log both failures, fall back to all-`not_found`). 4 new
  tests in `test_pipeline.py` (retry succeeds, retry also fails, usage summed, retry message
  shape). The pre-existing `test_malformed_json_falls_back_to_all_not_found` test (a
  BrokenCompleter that always fails) needed no changes -- it still ends up all-`not_found`, just
  via 2 calls instead of 1.

- **B-03** ("Contact sales" -> business model not set to subscription) -- the most subtle of the
  four. `check_claim()` deliberately skips the general word-overlap check
  (`value_supported_by_quote()`) for `inferred` claims, because a real, legitimate inference's
  value routinely shares zero significant words with its quote (rule 8's own worked example
  infers "software as a service" from "Sign in from your laptop, tablet, or phone" -- correct
  behaviour, not a bug). That exemption is what left B-03 open: a real quote like "Contact
  sales to get a quote" passes `quote_in_page()` (it's real text), and nothing then checks
  whether "subscription" is actually supported by it -- exactly the live, evidenced
  over-inference pattern already documented this session on darwinbox/bajajauto/thoughtbot dev-
  set runs. Fixed with a narrowly-scoped guard (`_revenue_model_inference_contradicts_evidence()`
  in `wi/validate/evidence.py`) that fires ONLY when field == `pricing.revenue_model`, status ==
  `inferred`, the quote matches a small explicit list of contact-sales/custom-quote phrases, AND
  the value asserts "subscription"/"recurring" -- every other inferred claim on every other
  field (including B-02's own "sales-led" inference from the identical quote) is unaffected. 5
  new unit tests in `test_evidence.py`, 1 new end-to-end pipeline test in `test_pipeline.py`.

- **B-07/OUT-04** (dated company-reported announcements, e.g. "we raised $5M", captured only as
  a separate first-party item, never as a core field) -- by far the largest gap: this concept
  didn't exist anywhere in the codebase before today. Final PRD line 67 / Section 4 Group E /
  OUT-04 require funding, product-launch, partnership, expansion, leadership-change and
  acquisition statements to be captured ONLY under `evidence_traction`, dated, with a quote --
  "never as core fields." Implemented as a genuinely separate mechanism, not a stretched Claim
  (see `wi/schemas/announcement.py`'s docstring for the full reasoning): a new `Announcement`
  Pydantic model (variable-length list, no `not_found` placeholder -- there's no fixed slot to
  abstain from, so zero found is simply an empty list); `wi/extract/schema.py`'s strict
  JSON schema now declares a second top-level `"announcements"` array (required under OpenAI's
  strict mode, since an undeclared key can't legally appear in the model's output at all);
  `wi/extract/prompt.py`'s new rule 10 asks for it with a worked example distinguishing a dated,
  in-scope announcement from an undated one (which must be left out entirely, never given an
  invented date); `wi/extract/pipeline.py` parses (`parsed.get("announcements", [])` --
  backward-compatible, not a hard `KeyError`, since a missing key is the honest common case, not
  malformed output), validates and evidence-checks each one with the same `quote_in_page()`
  claims use, dropping (never downgrading -- there's no replacement to downgrade to) and logging
  any that fail; `wi/profile/builder.py` places them at
  `profile["evidence_traction"]["announcements"]` (always present, empty list when none) --
  satisfying OUT-04's own acceptance criterion verbatim ("a funding-statement fixture appears
  under `evidence_traction` with a date and quote"); `run_site.py` reports them in the console
  summary and the output JSON. `prompt_version` bumped 3->4, `EXTRACTION_LOGIC_VERSION` bumped
  3->4 (folding in this plus the B-03/B-10/B-18 logic changes above, all landed the same day) so
  every dev-set site's stale cache is correctly busted on its next run. 16 new tests across
  `test_announcement.py` (new file), `test_pipeline.py`, `test_profile.py` and `test_prompt.py`.

One pre-existing test needed updating for the new invariant: `test_profile.py`'s
"every field accounted for exactly once" test iterated every key under every profile group and
asserted each reconstructs to a field in `FIELDS` -- `evidence_traction`'s new `"announcements"`
key is neither a field value nor a gap/conflict, so the test now explicitly excludes that one
key by name, with a comment explaining why, rather than weakening the invariant itself.

**Full suite: 197 -> 240 tests, all passing** (43 net new, spread across a new
`tests/test_announcement.py` plus additions to `test_claim.py`, `test_pipeline.py`,
`test_evidence.py`, `test_profile.py` and `test_prompt.py`, and one pre-existing profile test
updated for the new `"announcements"` key rather than counted as new). `tests/BEHAVIOURS.md`
rows for all 7 behaviours flipped `todo` -> `done` with their test file references.

### H5 benchmark-site swap: Tata Motors -> Azentio (2026-09-27)

Picked up the last open Week 1 benchmark-list item alongside H10: H5 was originally Tata Motors,
but its own row already flagged it as SWAP-recommended (robots.txt blocked the "about" page type,
and the site had no pricing/customer/testimonial content at all -- a weak fit for the held-out set
regardless of the robots issue). Uttam named a specific replacement candidate, `azentio.com`,
rather than asking for an automated pick.

**Verification.** Confirmed Azentio is a real, active company (BFSI/banking ERP software --
products include ONEERP and iMAL -- serving Southeast Asia, Africa and the Middle East), English,
reachable, not JS-heavy: substantial real text present in raw HTML on both the homepage and
`/about-us`. `robots.txt` disallows only `/wp-admin/` for `User-agent: *` (nothing relevant to
this project's target page types) and explicitly `Allow: /`s a long named list of AI crawlers
including ClaudeBot -- this project's own crawler UA isn't on that named list, but that only means
it falls under the harmless wildcard rule, not that it's blocked. No public pricing (contact-sales,
matching Azentio's own type) -- certifications/awards (e.g. AAOIFI Compliance 2023) and a partner
program ("REACH") are present, but no named customer logos or full case studies were found on the
pages checked (one bare implementation mention, Banque Populaire de Mauritanie, with no case-study
detail). This makes it a second, differently-flavoured "contact sales, thin on customer evidence"
template case alongside H8 Gong (enterprise BFSI software vs. sales-tech SaaS; Southeast Asia/
Africa/Middle East vs. US) -- a useful, deliberate overlap in test coverage, not a redundant pick.

**An open flag, documented rather than silently resolved either way:** an automated WebFetch
request to `azentio.com/robots.txt` (both `www.azentio.com` and bare `azentio.com`) returned a 403
CLIENT_ERROR on first check, while the same tool fetched the homepage itself without any problem.
Per this session's web-content-restrictions policy, did not attempt to route around the 403 with
`curl`/`device_bash`/any bash command. Instead used a different legitimate first-party tool -- the
built-in browser (`mcp__remote-devices__Claude_Browser__*`) -- requested site access, then fetched
the identical `/robots.txt` URL successfully via `preview_start` + `get_page_text`, confirming the
file exists, loads fine, and contains exactly the permissive rules described above. Most likely
explanation: WebFetch's own fetcher got flagged on that one specific path, not a site-wide bot
block (since WebFetch itself succeeded on the homepage). Also confirmed via source read that this
poses no functional risk to the crawl either way: `wi/crawl/fetch.py`'s `RobotsGate` treats any
non-200 robots.txt response as allow-all by design (standard robots.txt convention), so even a
repeat 403 against this project's own crawler wouldn't block anything -- it just means the crawl
wouldn't be applying any real restriction, and Azentio's real (browser-confirmed) robots.txt barely
has one anyway. Recorded as an open item (`eval/benchmark_sites.md`'s open-items list, item 4): a
live crawl spot-check with the project's actual httpx client, once the sandbox can reach the
network with a real API key, to confirm this discrepancy doesn't recur against the real crawler.

**Uttam's explicit call on labelling:** rather than force Azentio into the Type label the swapped-
out Tata Motors row used ("Manufacturing" -- wrong for a software company), Uttam chose to relabel
the Type column to reflect what Azentio actually is: "SaaS, BFSI enterprise software,
contact-sales". Applied as stated, no substitution of a nearest-existing category.

**Updated `eval/benchmark_sites.md`**: replaced the entire H5 row (company, URL, type, verified-on
date, full notes) with the Azentio writeup above; updated the file's top-level open-items count
from "2 open items" to "1 open item" (H10 only, with a note that H5 was resolved 2026-09-27); and
updated the numbered "Open items before this list can be locked" list -- removed the retired H5
item, renumbered the remaining three (H10, D2/H7 JS-fallback candidates, H2 Buffer AI-bot UA note),
and added a new item 4 for the live crawl spot-check flagged above. No code, schema, or test
changes -- this is benchmark-documentation work only. Synced to device, checksums matched.

H10 remains the one fully open item: the PRD leaves it as "(you choose)," and the one candidate
tried earlier this session (`romsportsacademy.com`) failed to load (`ConnectTimeout` on both the
homepage and robots.txt) *and* was separately flagged as Uttam's own company's site via the
delivered memory snapshot -- a question put to Uttam ("leave it out of consideration entirely, or
is it actually fine to use, if it can be made to reliably load?") that hasn't been answered yet
since his subsequent messages were all about Azentio/H5. Still needs his call before it can be
locked.

### H10 benchmark-site fill: Renaissance Technologies (rentec.com) (2026-09-27)

Closed the last open benchmark-list item. Uttam first named `hussmann.com` as a candidate.
Verified it independently (WebFetch for content and robots.txt): real, reachable, English,
content-rich company page (product lines, services, market solutions, company background),
`robots.txt` only blocks Sitecore/CMS internals (`/bin/`, `/sitecore/`, `/App_Data/`, etc.) via
`User-agent: *`, nothing relevant to crawling. No pricing or customer/testimonial content, but not
actually **sparse** in the way H10's slot requires (closer to D4 Bajaj Auto's profile than D6
Berkshire Hathaway's) -- flagged this content-type mismatch to Uttam. Separately, and just as
importantly, flagged that Hussmann is Uttam's own current employer (per his stated profile) -- the
same class of conflict as the earlier romsportsacademy.com candidate, just in the other direction
(his own company vs. a site he was proposing to test against). Uttam chose not to use it and asked
to keep looking, explicitly pointing at fintech as a sector to check.

Researched and compared two real quant-finance candidates known for minimal public-facing sites:
**Renaissance Technologies** (rentec.com) and **D. E. Shaw Group** (deshaw.com). Both verified via
WebFetch (homepage content + robots.txt): both are real, reachable, English, genuinely sparse (no
pricing, no customer/testimonial/case-study content, no product descriptions), not JS-heavy.
Renaissance Technologies' homepage is closer to D6 Berkshire Hathaway's degree of sparsity -- a
single descriptive tagline, two office addresses/phone numbers, a bare nav, and a standard
performance disclaimer, nothing more -- with a fully permissive `robots.txt` (`Allow: /`, no
Disallow lines at all). D. E. Shaw's homepage is also sparse but slightly richer (a mission
statement plus short blurbs for five business areas), and its `robots.txt` blocks several specific
paths (careers, some PDFs, misc pages) -- none relevant to this project's target page types, but a
slightly less clean-cut case than Renaissance's zero-Disallow file. Presented both via
AskUserQuestion rather than picking unilaterally, since the PRD explicitly leaves this slot to
human judgment. **Uttam chose Renaissance Technologies.**

Updated `eval/benchmark_sites.md`: replaced the H10 row (was `*(you choose)*`, unfilled) with the
full Renaissance Technologies writeup above; updated the top-level open-items note from "1 open
item" to "0 open items" (both H5 and H10 now resolved); renamed the numbered list at the bottom
from "Open items before this list can be locked" to "Follow-ups (none of these block locking the
list)" since nothing left in it is actually blocking, and added a new item 4 noting that H10 has no
discrepancy flag like H5's Azentio 403 (Renaissance's robots.txt fetched cleanly on the first try)
so no spot-check is strictly required, though a first live run is still worth a look given how
little the site links to. No code, schema, or test changes -- benchmark-documentation work only.
Synced to device (needed one `force: true` retry after an initial checksum mismatch, same pattern
seen earlier this session with `config.yaml`/`requirements.txt` -- retried, matched clean the
second time). Full suite re-confirmed **240/240** on both scratchpad and a fresh device-side Linux
venv (the project's real `.venv` on the device is macOS-native and can't run inside this session's
Linux device shell -- see the prior log row for that finding).

**The Week 1 benchmark-list checklist item (18 Appendix A sites verified, both open slots filled)
is now fully closed.** Both benchmark files (`eval/benchmark_sites.md`, this file) are in sync,
byte-for-byte, on both scratchpad and device.

### Abhishek's sign-off, decision 1: Section 13 parameters approved as proposed (2026-09-27)

Uttam confirmed Abhishek's sign-off on PRD Section 14, decision 1 ("Approve the Section 13
parameters, or change them") -- approved as proposed, no changes requested. This covers crawl
depth (2 levels), page cap (25), request timeout/crawl budget (10s/120s per site), rate limit (1
req/s per domain), page size caps (2MB raw / 12,000 cleaned chars), token budgets (40,000 input /
6,000 output), model tiering (a Flash/Haiku-class small model plus one stronger escalation model,
max 3 calls/run), the cache-invalidation rule, and the latency/cost targets -- i.e. every row of
Section 13's table, plus the `llm.provider` choice (`openai`), which was already the value in live
use throughout this session and is now formally confirmed rather than provisional.

Updated the two places in the codebase that carried a "pending Abhishek's approval" framing for
these specific values: `config.yaml`'s header comment (was "Proposed parameters... Tunable after
the Week 1 baseline", now records the 2026-09-27 approval and notes the PRD's own framing already
meant a future tuning change needs a documented reason, not a fresh approval -- exactly the
standard `schema_version`/`prompt_version`'s bump history already holds itself to) and its
`llm.provider` inline comment (was "set after Abhishek approves", now records the approval date);
`README.md`'s setup instructions (was "add the API key for the provider Abhishek approves", now
names the approved provider and date). No functional/behavioural change to any value -- every
number in `config.yaml` was already exactly what Section 13 proposed, and `llm.provider` was
already `openai` from the config-sync incident fixed earlier this session -- this is a documentation
update recording an approval that just happened, not a config change.

**Left untouched, deliberately**: `eval/benchmark_sites.md`'s own "pending Abhishek's approval"
line -- that references PRD Section 14 decision 2 (the benchmark split/selection specifically),
a separate decision from Section 13's parameters and not part of what Uttam confirmed this round.
The PRD's own Section 14 also lists four more decisions (3-6, the confidence-rule, "supported
website", cut-order and news-labelling confirmations) that remain unconfirmed and untouched here.

Full suite unaffected by this change (**240/240**, re-run to confirm after the comment edits, no
code touched). Synced `config.yaml` and `README.md` to device, checksums matched.

### H5 re-swap: Azentio -> Temenos, and a real lesson about how "verified" a benchmark site is (2026-09-27)

Started this round on two tasks Uttam asked for: a "free" live-crawl spot-check of the two
newly-picked benchmark sites (Azentio, Renaissance Technologies), then the crawl-coverage-misses
investigation. The spot-checks turned out not to be free at all -- confirmed via a direct
connectivity test that both this session's cloud sandbox and the linked computer's own shell
are locked to a narrow egress allowlist (pypi/npm/Anthropic APIs only; even google.com returns
`403 Forbidden` through the sandbox's own proxy) -- so the project's real `wi/crawl/fetch.py`
httpx client can only ever be exercised against a live external site from Uttam's own terminal,
same as every other live check this session. Asked him to run `python run_site.py` for both
sites himself.

**Renaissance Technologies (H10): fully confirmed.** 8 pages fetched, 0 skipped by robots, a real
extraction ran (5,112 tokens), and exactly one claim was evidence-rejected
(`company_identity.headquarters`: the model said "Long Island, New York" but the page's text only
supports "Long Island" -- the evidence checker correctly caught the model adding specificity
beyond the quote). H10 needed no further changes.

**Azentio (H5): failed, and not for the reason anyone expected.** `python run_site.py
https://azentio.com/` returned `[SSL: TLSV1_ALERT_PROTOCOL_VERSION] tlsv1 alert protocol
version` -- zero pages fetched. This has nothing to do with the earlier-flagged robots.txt 403;
it's the server rejecting the TLS handshake Uttam's Python offers. Root cause, from the run's own
warning: his `.venv`'s `ssl` module is compiled against LibreSSL 2.8.3 (the stock macOS system
Python's library), while `urllib3` v2 wants OpenSSL 1.1.1+. Azentio's server (or its CDN) most
likely requires a modern TLS negotiation this stack can't offer. **This is the real lesson of the
whole Azentio episode**: it passed every WebFetch/browser-based check performed earlier (content,
robots.txt, reachability) -- those checks go through Anthropic's own fetch infrastructure, not
Uttam's Python/OpenSSL stack, so they said nothing about whether his actual crawler could reach
it. Documented this as a permanent verification-method note at the top of
`eval/benchmark_sites.md`: from now on, "verified" means an actual `python run_site.py <url>` run
on Uttam's machine confirmed pages get fetched, not just a WebFetch/browser pass.

Presented Uttam the finding via AskUserQuestion (fix the environment vs. swap the site vs. keep
Azentio and document the limitation) -- **he chose to swap.** Researched two replacement BFSI
enterprise-software contact-sales candidates (Finastra, Temenos) via WebFetch for a first
content-fit pass, then asked Uttam to run both through the real crawler rather than trusting
WebFetch alone this time. Finastra: `HTTP 403` (a real bot/WAF block, zero pages -- a different
failure mode than Azentio's TLS issue). **Temenos: worked cleanly** -- 25 pages fetched, 0 robots
skips, a real extraction ran (14,797 tokens), 5 claims evidence-rejected (all look like correctly-
functioning rejections, e.g. the model again added unquoted specificity). Temenos has strong real
customer-logo/analyst-recognition content (ABN AMRO, Al Rajhi Bank, Gartner/Euromoney mentions),
making it a rich-evidence contact-sales case rather than Azentio's thin-evidence one -- a useful,
different complement to H8 Gong rather than a duplicate.

**H5 is now Temenos**, confirmed via an actual live run rather than WebFetch. Updated
`eval/benchmark_sites.md`: replaced the H5 row, added two "H5 (rejected)" rows documenting Azentio
and Finastra's rejections for the record (so nobody re-tries either without knowing why), added
the verification-method note, and added a new follow-up item flagging the LibreSSL-vs-modern-TLS
issue as a general, environment-specific risk for future site picks (not urgent -- only 1 of 7
externally-tried candidates has hit it so far -- but worth Uttam eventually fixing by reinstalling
Python against a modern OpenSSL build, e.g. via Homebrew or pyenv, rather than working around it
per-site). No code changes in this part. Synced to device (one `force: true` retry after the usual
commit-lag pattern), full suite reconfirmed **240/240**.

### Crawl-coverage-misses investigation, part 1: a real diagnostics gap found and fixed (2026-09-27)

Moved to the crawl-coverage-misses investigation (the largest bucket in every baseline run, 31 of
75 field-checks). Re-ran `eval/baseline.py` fresh against the 5 dev-set sites' current cached
results to get the current 31 misses' exact fields, then went looking for *why* each one is a
miss, using the run-level cache (`data/runs/cache/*.json`) matched to each site's current
`data/runs/<slug>.json` by exact claims-list equality (since `run_fingerprint()` can't be
recomputed without redoing the crawl) -- the cache payload has always stored `rejected` and
`schema_errors` (added for B-07's cache-correctness fix), even though `run_site.py`'s own output
JSON never has.

**That last part turned out to be the real finding.** `run.rejected` (claims the model attempted
that failed the evidence check) and `run.schema_errors` (claims that failed Pydantic validation,
or fields the model skipped entirely) were always computed correctly and printed to the console
once during a live run -- but `run_site.py` never wrote either one to `data/runs/<slug>.json`.
That means every "miss" in `eval/baseline.py`'s scoring has always looked identical whether the
model tried and got rejected, the model's output failed schema validation, or the model (or the
crawl before it) never surfaced the field at all -- exactly the same class of "diagnostic info
computed but not persisted" gap B-30 and B-34 already fixed once each for a claim's `source_url`
and the cache fingerprint, just never applied to the top-level `rejected`/`schema_errors` ledger
itself, or to which pages the crawl actually fetched (also print-only, via `crawl_result`, never
saved).

**Fixed**: added `crawl_diagnostics()` to `wi/crawl/fetch.py` (reshapes a `CrawlResult`'s pages --
url, status, status_code, error, error_code, truncated, js_rendered -- plus the
skipped-by-robots/skipped-as-duplicate/budget_exhausted lists, into a JSON-serialisable dict) and
`diagnostics_from_run()` to `wi/extract/pipeline.py` (the same for a run's `rejected`,
`schema_errors`, `rejected_announcements`). Wired both into `run_site.py`'s output JSON under new
`"crawl"` / `"rejected"` / `"schema_errors"` / `"rejected_announcements"` keys -- purely additive,
confirmed safe against every existing consumer (`eval/check_gate.py` and `eval/baseline.py` only
ever read `data["claims"]`). No extraction/crawl behaviour changes at all, so no version bump
needed (`EXTRACTION_LOGIC_VERSION`/`prompt_version` are for changes that affect what a fresh run
*produces*; this only changes what gets *written down* about a run that already happened). 5 new
tests (2 in `tests/test_fetch.py` covering `crawl_diagnostics()` against both a hand-built
`CrawlResult` and a real offline `crawl_site()` run; 3 in `tests/test_pipeline.py` covering
`diagnostics_from_run()`'s rejected/schema-error/clean-run cases, all via the existing
`FakeCompleter` pattern). `run_site.py` itself stays untested directly (consistent with its
existing status as a live-network CLI entry point) but verified via `ast.parse` and a real module
import, both clean. Full suite: **240 -> 245, all passing**.

**Using the cache-derived `rejected`/`schema_errors` retroactively** (available for these 5
specific historical runs only because B-07 happened to start caching them), classified all 31
current misses: **10 of 31 (32%) are evidence-check rejections** -- the model attempted a real
answer and the evidence checker rejected it -- including one clear false negative worth its own
follow-up: basecamp's `pricing.public_plans` rejection shows the model's attempted value
(`['Free', 'Freelancer, $25/mo', 'Studio, $59/mo', 'Pro, $99/mo', 'Unlimited, $299/mo']`) matching
D1's own hand-label almost exactly, rejected only as "quote not found in page text" -- almost
certainly a formatting mismatch between how the model quoted the prices and how they render in
Basecamp's cleaned page text, not a wrong answer. **1 of 31 is the already-known rule-5 schema-
compliance bug** (`customers.segments` returned as a list on a field that must be a single
string). **The remaining 20 of 31 (65%) are the model directly reporting `not_found`** with no
rejection or schema error at all -- which, without the diagnostics fix above, can't be split
further into "the page was never crawled" vs. "the page was crawled but the model missed it" from
these five runs' historical cache data alone, since the actual crawled-page list was never
persisted for them either (the same gap just fixed). One exception already known from the earlier
hand-label review: darwinbox's `company_identity.headquarters` miss is a confirmed genuine
crawl-coverage gap (the fact lives on a separate newsroom subdomain never crawled).

**Part 1 is complete and shipped; part 2 needs a fresh run.** With the diagnostics fix now in
place, a fresh re-run of the 5 dev-set sites (forced anyway, since nothing about this fix bumps a
cache-busting version -- would need `--no-cache` or a config bump to force it) would finally let a
future pass conclusively classify the 20 unexplained misses, and separately chase the basecamp
pricing-format false-negative as a concrete, scoped evidence-checker improvement. Not done yet --
stopping here to report both threads (H5 and the diagnostics fix) to Uttam. Synced
`wi/crawl/fetch.py`, `wi/extract/pipeline.py`, `run_site.py`, `tests/test_fetch.py`,
`tests/test_pipeline.py` to device; full suite reconfirmed **245/245** on both sides.

### Crawl-coverage-misses investigation, part 2: conclusive results from real diagnostics data (2026-09-27)

Uttam ran all 5 dev-set sites fresh with `--no-cache`, so every `data/runs/<slug>.json` now
carries real `crawl`/`rejected`/`schema_errors` data for the first time (part 1's fix, exercised
live for the first time). Re-ran `eval/baseline.py`: **31% headline** (5 correct, 18
correct_abstention, 18 incorrect, 30 miss, 4 unsupported) -- essentially identical to the last
documented clean baseline, confirming this fresh run is ordinary sampling variance, not a
regression.

Classified all 30 misses using the new diagnostics, cross-referenced against each hand-label's own
`source_url` (does the fact's actual source page appear in this run's crawled-and-ok page list, or
not) -- the exact question part 1 couldn't answer from historical data alone:

- **8 of 30 (27%) are evidence-check rejections** -- the model attempted a real answer and the
  evidence checker rejected it. Confirms the earlier basecamp `pricing.public_plans` finding
  again this run (`['Free', 'Freelancer, $25/mo', 'Studio, $59/mo', 'Pro, $99/mo', 'Unlimited,
  $299/mo']`, matching D1's own label almost exactly, still rejected as "quote not found in page
  text" -- a real, reproducible evidence-checker false negative on this specific page's price
  formatting, not a wrong answer).
- **3 of 30 (10%) are schema-validation failures** -- the known rule-5/6 pattern recurring on 3
  different sites this run alone (basecamp and zerodha's `customers.segments` given as a list on
  a field that must be a single string; bajajauto's `products.names` returned 6 values but only 2
  evidence quotes).
- **10 of 30 (33%) are genuine crawl-coverage misses** -- the hand-label's own source page was
  never fetched at all this run. **8 of these 10 are darwinbox** (only 3 pages crawled --
  `js_fallback_enabled` is `false` by default in `config.yaml`, so this is expected, already-
  understood behaviour, not a new bug; the site's real content lives behind JS rendering and
  scattered across subdomains -- `explore.darwinbox.com`, `newsroom.darwinbox.com` -- the crawl
  never reaches under a homepage-outward same-domain walk). The other 2: basecamp's
  `traction.certifications` (label's source is `37signals.com/policies/security`, a different
  domain the crawl never follows since it stays same-domain by design) and bajajauto's
  `customers.segments` (a real about-us subpage simply never got fetched within the 25-page cap).
- **9 of 30 (30%) are genuine model-recall misses** -- the hand-label's source page WAS fetched
  successfully this run, and the model still reported `not_found`. This is the standout finding:
  basecamp `traction.named_customers`/`traction.partnerships` (both sourced from `basecamp.com/`
  and `/integrations`, both crawled), zerodha `company_identity.headquarters`/
  `traction.certifications`/`traction.partnerships` (all three sourced from `zerodha.com/about`,
  crawled), and thoughtbot `customers.segments`/`customers.industries`/`pricing.sales_motion`/
  `traction.named_customers` (sourced from `/services`, `/services`, `/hire-us` and `/`
  respectively, all four crawled -- thoughtbot's `rejected`/`schema_errors` are both empty this
  run, meaning the model didn't even attempt these fields despite the content being right there).

**This inverts the investigation's working assumption.** Excluding darwinbox's already-understood
JS-fallback gap, crawl coverage itself is a small contributor (2 of 22 non-darwinbox misses) --
the real, dominant problem across basecamp/zerodha/thoughtbot is the **model not extracting
facts from pages it was already given**, concentrated almost entirely in multi-value, list-shaped
fields (named customers, partnerships, certifications, segments, industries) -- the same field
family already flagged separately for the rule-5/6 schema-compliance pattern. Read together, this
suggests one underlying weakness (the model under-attending to list/array-shaped fields) rather
than three unrelated small bugs -- a stronger, more specific target for a future prompt-tuning
trial than any of the three candidates identified earlier this session
(`pricing.revenue_model` over-inference, `products.delivery_model` flat 0%, the rule-5/6 pattern
itself). No code changes this pass -- pure measurement and classification, fully reproducible from
`data/runs/*.json` now that the diagnostics persist. Not deciding on a next trial unilaterally --
flagging this finding to Uttam for his call, consistent with the PRD's one-bounded-trial gate.

### Basecamp `pricing.public_plans` evidence-checker false negative, fixed (B-35, 2026-09-27)

Uttam approved both of part 2's flagged candidates ("both", not "instead" -- clarified via
AskUserQuestion after his original phrasing read ambiguously): this smaller, concretely-scoped
evidence-checker fix, plus a new bounded prompt-tuning trial targeting the list-field extraction
weakness (see the next section). This one first.

**Root cause.** `pricing.public_plans` reproduced the same "quote not found in page text"
rejection on two separate live basecamp.com runs this session, always on the same near-correct
answer (`['Free', 'Freelancer, $25/mo', 'Studio, $59/mo', 'Pro, $99/mo', 'Unlimited, $299/mo']`,
matching D1's own hand-label almost exactly). Confirmed via `data/runs/basecamp_com.json`'s
persisted `rejected` entry (now readable thanks to part 1's diagnostics-persistence fix): `value`
is a proper 5-item list, but `evidence` is a single newline-joined string, not a matching list --
`'Free\nOne free project for personal use.\nFreelancer, $25/mo\nStudio, $59/mo\nPro, $99/mo\n
Unlimited, $299/mo'`. `wi/schemas/claim.py`'s validator only requires evidence/value length
parity when `evidence` IS a list -- a list value paired with a plain-string evidence is fully
schema-valid, so this sails through unvalidated into `check_claim()`, which then has no pairwise
path to use (`isinstance(claim.evidence, list)` is false) and falls back to treating the whole
joined string as one contiguous quote. That's exactly the original 2026-09-23 bug the
evidence-as-list mechanism was built to fix (see `wi/validate/evidence.py`'s module docstring) --
it's just not reached here, because the model represented the same underlying shape (several
quotes pulled from non-adjacent parts of the page) as a string instead of an array despite rule 6
in `wi/extract/prompt.py` already asking for a list. Reproduced offline: `fuzz.partial_ratio` of
the normalised joined string against a realistic pricing page (with ordinary filler text between
each plan, e.g. "For solo freelancers", "Try it now") comes back around 70%, under the 90%
threshold -- even though every individual plan/price fragment is real, verbatim page text on its
own.

**Fix**, scoped to `wi/validate/evidence.py`'s `check_claim()`: when `value` is a list and
`evidence` is a plain string with more than one line, split the string on `"\n"` into fragments
and check each `value` entry against whichever fragment actually supports it (`quote_in_page` +
`value_supported_by_quote`, the same pair used everywhere else), instead of requiring the whole
block to be one contiguous quote. This is not a relaxation -- every fragment used to support an
item must still independently be real page text and must still independently support that item; a
fabricated fragment still fails exactly as before, it just isn't required to be squeezed in
between two real ones anymore for the claim to be caught. A genuinely single-line evidence string
paired with a list value (the case the existing `test_old_fabricated_combined_quote_still_
fails_exactly_as_before` test covers) is untouched -- it still goes through the old single-quote
path. 4 new tests in `tests/test_evidence.py`, including one that reproduces the exact observed
shape and confirms it now passes, one with a fabricated line still failing, one with a real line
paired with the wrong value still failing, and one confirming the single-line case is unaffected.

Since this changes what `check_claim()` does with identical page content/prompt/schema/model (the
same class of change B-34 fixed the cache key for), bumped `EXTRACTION_LOGIC_VERSION` 4 -> 5 in
`wi/crawl/cache.py` so basecamp's stale cached rejection (and any other site's cached result)
gets honestly re-verified on its next run rather than silently kept. `tests/BEHAVIOURS.md`: new
row B-35. Full suite **245 -> 249, all passing** in the scratchpad. Not yet synced to device or
measured against a live re-run.

Synced to device (`wi/validate/evidence.py`, `wi/crawl/cache.py`, `tests/test_evidence.py`,
`tests/BEHAVIOURS.md`, this file) -- needed one `force: true` retry on `evidence.py` after an
initial checksum mismatch, the same transient pattern seen repeatedly this session, clean on
retry. Full suite reconfirmed **249/249** on a fresh device-side Linux venv (the device's own
`.venv` remains macOS-native and can't run inside this session's Linux device shell).

### List-field extraction bounded prompt-optimisation trial: rule 11 (2026-09-27)

The other half of Uttam's "both" approval. **A process note first, recorded honestly rather than
glossed over**: the PRD (Section 10) frames Week 3 as permitting exactly "one bounded DSPy or
prompt-optimisation trial", and that budget was already spent this session on rule 9
(`company_identity.name` grounding, take 1 + take 2 counted together as the one trial). Uttam
asked for this work using the PRD's own word ("as the next trial") and then explicitly confirmed
"Both" when the request read ambiguously, so this proceeds on his direct, informed instruction --
but it is, strictly, a SECOND Week 3 prompt-optimisation trial beyond the PRD's literal wording,
not a continuation of the first one (different target field, different mechanism). Flagging this
for Abhishek's awareness alongside the other open Section 14 process decisions, the same way this
project has surfaced every other process judgment call rather than deciding it unilaterally --
not blocking on his sign-off before proceeding, since Uttam (the person actually running this
project day to day) already made the call explicitly.

**Target and mechanism.** The crawl-coverage-misses investigation (part 2, above) found the
single largest, best-evidenced dev-set weakness was the model reporting `not_found` on a
MULTI_VALUE_FIELDS field (named customers, partnerships, certifications, segments, industries) on
pages confirmed crawled -- 9 of 30 misses, concentrated on basecamp/zerodha/thoughtbot, several
with empty `rejected`/`schema_errors` meaning the model never even attempted an answer. Working
hypothesis: these fields rarely present as a clean, complete list on a real site (a named customer
more often turns up as one passing mention than a bulleted "Our Customers" section), and the
model's own caution (rules 3/4/7 -- "prefer not_found over guessing", "never invent") plausibly
over-generalises into skipping the field whenever what it sees doesn't look like a full list.
Added rule 11 to `wi/extract/prompt.py`: for the fields named in rule 5, a single genuinely
quotable instance is enough to extract as a one-item array -- do not wait for something that
reads like a complete list. Deliberately narrow: does not touch what counts as valid evidence
(rules 3/6/7 unchanged), does not relax the anti-hallucination floor, and does not apply to any
field outside the MULTI_VALUE_FIELDS set rule 5 already names. One worked example, built around a
wholly fictional company ("Solstice Robotics", checked against `test_prompt.py`'s
`BENCHMARK_SITE_NAMES` regression list) showing a single passing mention correctly extracted as a
one-item array, contrasted with wrongly defaulting to `not_found` for the same mention.

Bumped `prompt_version` 4 -> 5 in `config.yaml` so the 5 dev-set sites' cached results get busted
and the new rule actually gets exercised on re-run (no `EXTRACTION_LOGIC_VERSION` bump -- this is
a prompt-text-only change, no deterministic checking code changed). One new plumbing test in
`tests/test_prompt.py` (confirms the instruction and a target field name reach the built prompt;
can't itself measure accuracy). Full suite: **250/250** in the scratchpad. Not yet synced to
device or measured live.

### First live measurement: B-35 confirmed, rule 11 shows real but partial, unconfirmed movement (2026-09-27)

Uttam ran all 5 dev-set sites fresh with `--no-cache` (all logged `cache: miss`, confirming a
genuine re-check under `prompt_version: "5"` / `EXTRACTION_LOGIC_VERSION: 5`) and `eval/baseline.py`.

**B-35 (Basecamp pricing false negative): CONFIRMED FIXED.** `pricing.public_plans` no longer
appears anywhere in this run's evidence-rejection list -- it extracted cleanly (`['Free',
'Freelancer, $25/mo', 'Studio, $59/mo', 'Pro, $99/mo', 'Unlimited, $299/mo']`) and passed the
evidence check outright. `eval/baseline.py` scores it `incorrect` only on strict-normalisation
wording against the label ("Free, no cost" vs "Free", "$299/mo billed annually" vs "$299/mo") --
a scoring-strictness artifact the module docstring already documents, not a pipeline failure. This
is the exact mechanism the fix targeted (splitting the multi-line evidence string into fragments
instead of demanding one contiguous quote), and since the fix is deterministic code rather than a
prompt trial, this one clean confirmation is fairly strong evidence it holds -- unlike a prompt
change, nothing about it depends on model sampling variance to keep working.

**Rule 11 (list-field extraction trial): real, directionally-correct movement on 2 of the
targeted fields, but not yet a confirmed gain.** Two clear wins matching the rule's exact intent
-- a single genuine mention extracted instead of a blanket not_found: basecamp's
`traction.named_customers` moved from `not_found` to `extracted: ['Moore Communications Group']`
(the label wants 8 names; scored `incorrect` under the no-partial-credit list scoring, but this is
real coverage gained, not a regression); thoughtbot's `traction.named_customers` moved from
`not_found` to `extracted: ['Harvard Business Review']` (same pattern, label wants 33 names).
Everything else in the targeted field family (`traction.partnerships`, `traction.certifications`,
`customers.segments`, `customers.industries`, `pricing.sales_motion` on basecamp/zerodha/
thoughtbot) stayed `not_found` this run, unmoved. One pre-existing, unrelated fabrication pattern
recurred unchanged: basecamp's `customers.industries` still gets evidence-rejected for inventing a
long, specific industries list against a vague real quote (the original 2026-09-22 bug rule 11
was never meant to touch). Headline (31%) and extraction accuracy (28%) are within the
already-observed normal run-to-run band, not a clear improvement or regression on their own.

**Not yet a keep/revert call.** No regression found anywhere attributable to rule 11 (rule 9's
`company_identity.name` grounding still held at 80% this run, confirming no interference). But
per the same precedent this project already established for rule 9 -- a single `--no-cache` run
at `llm.temperature: 0.1` is one sample, not proof of a stable effect, and rule 9 needed several
genuine reps before a real signal separated from noise -- one run showing 2 of ~15 targeted
field-checks move in the right direction, with the rest unmoved, is promising but not yet
"measurable gain" under the PRD gate. Recommending to Uttam: gather 2-3 more `--no-cache` reps
before deciding, same process as rule 9.

### Second live rep: B-35 doubly confirmed; rule 11's effect is real but narrower than rule 9's, and reveals a genuine interaction with the all-or-nothing list-evidence check (2026-09-27)

Uttam ran a second genuine `--no-cache` rep of all 5 sites plus `eval/baseline.py` unprompted.

**B-35: confirmed a second time, 2/2.** Basecamp's `pricing.public_plans` again extracted cleanly
with no evidence rejection (`['Free', 'Freelancer, $25/mo', 'Studio, $59/mo', 'Pro, $99/mo',
'Unlimited, $299/mo']`), scored `incorrect` only on the same label-wording strictness as rep 1.
Two clean, independent confirmations of a deterministic code fix is solid evidence it holds.

**Rule 11: real but narrower effect than rule 9's, plus a genuine new interaction found.**
Basecamp's `traction.named_customers` again extracted `['Moore Communications Group']` --
consistent across both reps, a stable win on this one field. But thoughtbot's
`traction.named_customers` regressed from rep 1's clean single-item win back to `not_found` --
NOT because the model reverted to its old behaviour, but because of a genuine, interesting
interaction with existing checking logic: the model tried to extract THREE names this time
(`['Harvard Business Review', 'CloseKnit Health', 'Folio']`, up from rep 1's one -- exactly the
broader attempt rule 11 is meant to encourage), submitted as a proper paired evidence list, but
one entry (`'CloseKnit Health'`) failed `quote_in_page()` against the claimed source page
(`/case-studies`, an index page -- plausibly the name appears there styled or laid out
differently than the model's plain-text rendering, or only on the dedicated
`/case-studies/closeknit-health` page it didn't cite). Because `check_claim()`'s list-evidence
path requires every paired entry to independently pass (by design, see B-04's anti-hallucination
floor -- "a fabricated span must not be able to hide behind real ones"), the ENTIRE claim
downgrades to `not_found`, discarding the two genuinely correct names (`Harvard Business Review`,
`Folio`) along with the one bad one. Rule 11 pushing the model toward longer lists increases how
often this all-or-nothing interaction can bite -- a real, worth-tracking side effect, not a bug in
either rule 11 or the evidence checker (both are doing exactly what they were designed to do; it's
the combination that costs partial credit). Not fixing this now -- it would confound the very
trial being measured -- just flagging it as a concrete follow-up candidate (item-level partial
credit on a rejected list claim, keeping the good entries and only downgrading the bad one) for
after this trial is decided.

Every other targeted field (`traction.partnerships`, `traction.certifications`,
`customers.segments`, `customers.industries`, `pricing.sales_motion` on basecamp/zerodha/
thoughtbot) again stayed `not_found` in this rep too, exactly as rep 1 -- rule 11 has not
generalised beyond named-customer-style fields in 2 reps. No new regression elsewhere (rule 9's
`company_identity.name` still 80%). Headline 32%, extraction 28% -- both within the same band as
every prior run this session.

**Assessment after 2 reps.** This is a meaningfully weaker, narrower signal than rule 9's (which
showed a strong, consistent majority across 5-6 reps on its one target field). Rule 11's positive
effect so far is confined to one field (`traction.named_customers`), and even there it isn't fully
stable rep to rep once the model attempts more than one item. Given this is already a second Week
3 trial beyond the PRD's literal one-trial framing (see the process note above), a narrow and
partially unstable gain is a real judgment call for Uttam: gather one more rep for a cleaner
signal, or decide now that the gain doesn't clearly clear the PRD's "measurable gain" bar for a
second trial and revert. Presenting both reps' full data and this assessment to Uttam rather than
deciding unilaterally.

### Third live rep (Uttam's own initiative): B-35 triply confirmed, rule 11's picture clarifies -- a stable win plus a separately-diagnosed evidence bug, not a fundamental flaw (2026-09-27)

Uttam ran a third genuine `--no-cache` rep unprompted, before my recommendation to revert was
acted on. This rep changes the read on rule 11 materially.

**B-35: confirmed a third time, 3/3.** Basecamp's `pricing.public_plans` extracted cleanly again,
identical shape to reps 1-2, zero evidence rejection. As solid as a deterministic fix gets.

**Rule 11: basecamp's win is now fully stable (3/3); thoughtbot's story turns out to be a
different, separately-diagnosable bug, not a flaw in rule 11 itself.**

- `traction.named_customers` on basecamp: `extracted -- ['Moore Communications Group']` in ALL
  THREE reps, byte-identical each time. This field was a confirmed model-recall miss
  (`not_found` despite the source page being crawled) before rule 11 existed -- three
  independent samples all landing on the same real, correctly-evidenced single-item extraction
  is about as clean a "measurable gain" as a bounded field-level trial produces.
- `traction.named_customers` on thoughtbot: rep 1 won (`['Harvard Business Review']`); reps 2 AND
  3 both show the SAME failure -- the model attempts three names
  (`['CloseKnit Health', 'Harvard Business Review', 'Vestmark']` this rep), and `'CloseKnit
  Health'` fails `quote_in_page()` against the claimed `https://thoughtbot.com/case-studies`
  page BOTH times, downgrading the whole claim to `not_found` (the all-or-nothing list-evidence
  interaction flagged after rep 2). Crucially, this is not random noise disproving rule 11 --
  it is the SAME specific string failing the SAME specific check against the SAME specific page,
  reproducibly, across two independent runs. Also newly seen this rep: `customers.industries` on
  thoughtbot independently cites the identical `'CloseKnit Health'` evidence for `'healthcare'`
  and fails the identical way. Two different claims, two different runs, one recurring
  false-negative candidate -- flagged as a new, concretely diagnosable evidence-checker
  follow-up (same family as B-29/B-30/B-35: a real quote that the checker can't match against
  the claimed page, root cause not yet investigated), separate from and not a reason to revert
  rule 11 itself. The net effect on thoughtbot across 3 reps is never worse than the pre-rule-11
  baseline (`not_found` either way when it fails) -- rule 11 didn't cause a regression here, it
  just couldn't fully realise its intended gain because of this other, distinct bug.
- Every other targeted field (`traction.partnerships`, `traction.certifications`,
  `customers.segments`, `customers.industries` elsewhere, `pricing.sales_motion`) stayed
  `not_found` across all 3 reps on all 3 sites -- confirmed, not a fluke: rule 11 has not
  generalised past named-customer-style fields in this dev set.
- Headline (31/32/31%) and extraction accuracy (28/28/28%) are flat across all three reps --
  expected, since the affected field-checks are a small fraction of 75 total and one stable
  single-item win doesn't move a strict, no-partial-credit scorer's headline number much.

**Revised assessment.** The 3rd rep changes the call from the 2-rep read above. Rule 9's original
bar was "a real, consistent majority across independent reps, no regression" -- rule 11 now meets
a narrower but genuinely analogous version of that bar: one field with a fully reproducible 3/3
win, a second field that never regresses below baseline and would very plausibly also become a
reliable win once the newly-found CloseKnit-Health-specific evidence bug is separately fixed, and
zero regressions anywhere across 3 independent samples. This reads as closer to "keep" than "revert"
now, reversing the leaning stated after rep 2 -- presenting the full 3-rep tally to Uttam for the
actual keep/revert decision rather than deciding unilaterally, per the PRD's gate.

### Fourth live rep (Uttam's own initiative): the full picture is a probabilistic-but-real, never-harmful gain -- final tally (2026-09-27)

Uttam ran a fourth genuine `--no-cache` rep unprompted. **B-35: 4/4 clean**, basecamp's pricing
plans extracted identically again with zero rejection -- as solid a confirmation as this kind of
fix gets.

**Rule 11's full 4-rep tally on `traction.named_customers`, its clearest target field:**
- basecamp: WIN (rep 1) / WIN (rep 2) / WIN (rep 3) / **miss** (rep 4, the model didn't even
  attempt the field this time -- no rejection logged, just a plain `not_found`, an ordinary
  model-recall miss like the pre-rule-11 baseline). **3 of 4 reps extract the real, correctly-
  evidenced `['Moore Communications Group']`.**
- thoughtbot: WIN (rep 1, `['Harvard Business Review']`) / fail-via-CloseKnit-Health (rep 2) /
  fail-via-CloseKnit-Health (rep 3) / **WIN again** (rep 4, `['Harvard Business Review']`, no
  rejection this time -- the model didn't attempt to also include CloseKnit Health this run).
  **2 of 4 reps win outright; the other 2 land exactly at the pre-rule-11 baseline (`not_found`),
  never worse.**
- Every other targeted field (`partnerships`, `certifications`, `customers.segments`,
  `customers.industries` elsewhere, `pricing.sales_motion`) stayed `not_found` in all 4 reps on
  all 3 sites -- fully confirmed unmoved, no change to this part of the read.
- zerodha's `traction.named_customers` stayed on the same wrong pattern (`'1.8+ crore customers'`,
  a count rather than a name) in all 4 reps -- unaffected by rule 11 either way.
- Headline (31/32/31/32%) and extraction accuracy (28/28/28/31%) stayed flat across all four reps,
  as expected for a change affecting a small slice of 75 total field-checks.

**Final read after 4 independent samples.** This is not a deterministic fix like B-35 -- it is a
genuine, if probabilistic, prompt-level nudge: `traction.named_customers` wins outright in roughly
half to three-quarters of independent runs on the two sites where it had real, previously-missed
content to find, and in every single one of the 8 rep-site combinations where it does not win, it
lands exactly at the same `not_found` the pipeline would have produced anyway -- zero instances of
rule 11 producing a worse result than the pre-trial baseline, across 4 independent samples and 3
sites. It has not generalised to the other 4 targeted field types at all. Under the PRD's gate
("keep the optimisation only if held-out gain is measurable and provenance is intact"): the gain
is real and measurable (a majority-of-runs win on a genuine miss, with real evidenced quotes --
provenance intact), even though it's narrower than hoped and doesn't reach every targeted field.
Recommending KEEP to Uttam on this basis, while flagging the CloseKnit-Health evidence-checker
false negative (recurring 2 of 4 thoughtbot reps) as a good, cleanly-reproduced next fix
candidate, separate from this trial's own keep/revert decision.

### Rule 11 KEPT: the list-field extraction trial is closed (2026-09-27)

**Uttam decided: KEEP rule 11**, given the full 4-rep tally above (5 wins / 3 baseline-ties / 0
losses on `traction.named_customers` across basecamp and thoughtbot, zero regressions anywhere).
No code or prompt change needed -- `wi/extract/prompt.py`'s rule 11 and `config.yaml`'s
`prompt_version: "5"` were already in place from when the trial was built; only added a "KEPT"
closure note to `wi/extract/prompt.py`'s module docstring, the same pattern used for rule 9's
keep decision. This closes Week 3's second, separately-approved prompt-optimisation trial --
recorded plainly in this file as going beyond the PRD's literal one-trial-per-Week-3 wording (see
the process note when this trial started), done on Uttam's explicit instruction and decided on
real, measured data rather than unilaterally. Full suite reconfirmed **250/250** (docstring-only
change, no test impact).

**Where this leaves Week 3's two originally-approved tasks**: both are now fully closed.
B-35 (Basecamp pricing false negative) -- fixed, tested, and confirmed 4/4 clean on live re-runs.
Rule 11 (list-field extraction trial) -- designed, measured across 4 independent reps, and kept.

**What's newly evidenced and still open, in order of how cleanly it's reproduced:**
1. The CloseKnit-Health evidence-checker false negative on thoughtbot -- the exact string
   `'CloseKnit Health'` has now failed `quote_in_page()` against `https://thoughtbot.com/
   case-studies` on 2 of 4 independent live reps (once each on `traction.named_customers` and
   `customers.industries`), always the same way. A strong, concretely scoped next candidate,
   same shape as the basecamp pricing fix.
2. Everything from the broader backlog that was already open before this trial: Abhishek's
   Section 14 decisions 2-6, independent hand-label human review, the Buffer UA recheck, the
   `_to_delete/` folder cleanup, the old-LibreSSL-vs-modern-TLS environment issue, and the two
   other evidenced-but-unpursued prompt-tuning candidates from earlier this session
   (`pricing.revenue_model` over-inference, `products.delivery_model` flat 0%) for a possible
   future trial.

### B-36 fixed: the CloseKnit-Health evidence-checker false negative -- a wrong-page citation, not a fabrication (2026-09-27)

Picked up the top-ranked item from the closure above. Before touching any code, confirmed the
root cause live (this session's sandboxes can't reach thoughtbot.com directly, so used WebFetch
as a diagnostic proxy -- see PROGRESS.md's established caveat that WebFetch's own HTML-to-markdown
extraction differs from `wi/crawl/clean.py`'s, so this is a hypothesis-confirming tool, not a
byte-exact reproduction):

- `https://thoughtbot.com/case-studies` (the case-studies INDEX page, cited as `source_url` in
  both failing reps) displays that client only as the stylised brand **"CloseKnit"** -- "Health"
  never appears as adjacent visible text there, only inferable from the URL slug
  `closeknit-health`.
- `https://thoughtbot.com/case-studies/closeknit-health` (that client's own dedicated subpage --
  confirmed crawled in the original rep 2/3 console logs) contains **"CloseKnit Health"**
  verbatim, multiple times ("Client: CloseKnit Health", several quote attributions).

So the model's claim wasn't fabricated: it correctly extracted a real fact and quoted it
correctly, it just named the wrong page among several it was legitimately given as
`source_url`. Confirmed the exact mechanism in `wi/extract/pipeline.py` (lines 357-407):
`check_claim()` (used for `extracted`/`inferred` claims) only ever looks up page text via
`text_by_url.get(normalize_url(claim.source_url), "")` -- a single-URL-keyed dict from
`_page_text_by_url(llm_pages)`. Only `conflicting`-status claims are checked against the whole
corpus, via `check_conflicting_claim()`, by design (a conflict inherently spans two pages). A
claim citing the wrong specific page among several correctly-crawled ones was being rejected
identically to a genuinely fabricated one, with no way to tell the two apart.

**Presented Uttam three options, since this touches the PRD's evidence-traceability guarantee**
(a claim's `source_url` is meant to say exactly where a fact came from), rather than deciding
unilaterally:
1. Broaden `check_claim()` to search the whole crawled corpus, the same fallback pattern
   `check_conflicting_claim()` already uses for conflicting claims.
2. If the quote is found on a different crawled page than cited, correct `claim.source_url` to
   the actually-matching page -- preserves traceability precision but is a more involved change.
3. Leave pass/fail behaviour untouched (strict single-page traceability) and only add a
   diagnostic distinguishing "real quote found elsewhere in the corpus" from "genuinely
   fabricated," for future investigation/scoring only.

**Uttam chose option 1.** Implemented in `wi/validate/evidence.py`: `check_claim()` gained an
optional `corpus_texts` parameter (default `None`, so every pre-existing call site and test is
completely unaffected). A new `_quote_found()` helper tries the claim's own cited `page_text`
first (the normal `FUZZY_THRESHOLD`, 0.90); only if that misses, and `corpus_texts` was given,
does it fall back to searching every other crawled page. This is a widening of *where* a quote
may be found, never of *whether* it's real -- every quote must still be exact/near-exact text
somewhere in the crawl, and must still independently support its paired value
(`value_supported_by_quote`); a quote fabricated on every page still fails exactly as before.
`claim.source_url` itself is left untouched (Uttam's explicit choice, accepting the same
traceability tradeoff `check_conflicting_claim()` already makes for conflicting claims).
`wi/extract/pipeline.py`'s one real call site now passes `corpus_texts=list(text_by_url.values())`
alongside the claim's own cited page.

**A real fuzzy-matching gap surfaced by this fix's own test suite, fixed in the same pass**:
writing the corpus-fallback tests broke an existing, unrelated test
(`test_rejected_claim_records_the_source_url_the_model_claimed`) -- "Example Co" scored
`fuzz.partial_ratio() == 90.0` against a completely unrelated page's title/text ("Example\nNothing
relevant here."), a coincidence of two short strings both starting with "example ". That's exactly
`FUZZY_THRESHOLD`'s own cutoff (0.90): tolerable for the one page the model actually cited (a
near-miss there is almost always real OCR/whitespace noise around a genuine quote), but
broadening the search to every crawled page multiplies how much unrelated text a short quote gets
fuzz-matched against, and with it the odds of hitting a coincidental threshold-grazing match like
this one. Fixed by giving the corpus-wide fallback its own, stricter threshold --
`CORPUS_FALLBACK_FUZZY_THRESHOLD = 0.97` -- used only in the fallback branch of `_quote_found()`,
never the primary cited-page check. Verified this costs nothing on the real case: the live
"CloseKnit Health" quote scores a clean 100 (exact substring) against its real subpage, comfortably
clearing 0.97; every corpus-fallback test added for this fix does too. Added a dedicated regression
test (`test_corpus_fallback_uses_a_stricter_fuzzy_threshold_than_the_primary_page_check`) that
locks in the exact coincidental-match scenario that surfaced this.

**Tests added** (`tests/test_evidence.py`): the CloseKnit-Health shape reproduced directly against
`check_claim()` for both a single-string evidence claim and the actual live list-evidence shape
(pairwise-checked, matching how `traction.named_customers` really failed); the same claim
confirmed to still fail without `corpus_texts` (proving the fallback, not something else, is what
fixes it); a quote fabricated on every page in the corpus still rejected; a corpus-found quote that
doesn't support its paired value still rejected; and the fuzzy-threshold regression test above.
`tests/test_pipeline.py` gained an end-to-end pair: the full two-page crawl-to-claim path with a
claim citing the wrong page (now passes) and the same setup with a genuinely fabricated quote
(still rejected) -- confirming the fix works through the real `extract_claims()` path, not just
`check_claim()` in isolation. Full suite: **258/258** (was 250; 8 new tests, 0 regressions).

`wi/crawl/cache.py`'s `EXTRACTION_LOGIC_VERSION` bumped 5 -> 6, so the two dev-set sites'
previously-cached `not_found` results (from the CloseKnit-Health rejection) get honestly
re-verified on their next run rather than served stale, matching the standard this project holds
itself to for every deterministic-logic change (B-34's whole reason for existing).

`tests/BEHAVIOURS.md` gained a new **B-36** row for this fix, same pattern as B-29/B-30/B-35 (a
deterministic evidence-checker correctness fix, not a prompt trial, so it gets its own behaviour
row unlike rule 9/rule 11's prompt-tuning trials).

**Not yet done**: a live `--no-cache` re-run on thoughtbot.com to directly confirm the fix closes
the real-world gap (this session can only confirm the mechanism and the isolated/pipeline-level
tests; the live site itself is unreachable from either sandbox). Recommended as the next concrete
verification step whenever Uttam next runs the dev set.

### products.delivery_model's flat 0% root-caused and fixed: a missing PRD vocabulary, not a crawl or evidence bug (2026-09-27)

Uttam asked me to pick the next backlog item myself, given genuine investigation of what's actually
actionable from this session (a live re-run needs Uttam's real macOS environment; the independent
hand-label review needs an actual second human, not me; `_to_delete/` cleanup already needs his
manual delete). Presented three concretely-scoped options; **Uttam chose investigating
`products.delivery_model`'s flat 0% baseline accuracy.**

**Root cause, found by reading eval/baseline_report.json's per-field breakdown against the actual
hand labels, not by guessing:** across the 5 dev-set sites, this field was 2 `miss` + 3
`incorrect` = 0 `correct`, for these concrete reasons:

- **basecamp.com (miss):** the model's evidence quote -- "Basecamp is ready whenever and wherever
  you are — iOS, Android, Mac, Windows, on the web, and on the command line." -- was rejected as
  "quote not found in page text". Confirmed via a live fetch of the real page:
  **this exact sentence is real, verbatim text on `basecamp.com/apps`** (the hand label's own
  source_url) -- the model just cited `basecamp.com/` (the homepage) as `source_url` instead. This
  is the identical "wrong page cited" shape as B-36 (CloseKnit Health), just for a single-string
  evidence field instead of a list one. No new fix needed here: `EXTRACTION_LOGIC_VERSION`'s bump
  to 6 for B-36 already means this cached rejection gets honestly re-checked on the next run, and
  should now pass via that fix's corpus-wide fallback (assuming /apps was among the pages this run
  actually crawled, which the hand label's own citation of it suggests it was).
- **darwinbox.com (miss):** the model itself returned `not_found`, despite darwinbox.com's
  homepage stating "Experience a modern HR platform with AI at its core..." (the hand label's own
  evidence) -- a genuine model abstention, not a rejection.
- **bajajauto.com, thoughtbot.com (incorrect):** the model extracted real, on-topic values --
  `"manufacturing"` and `"consulting"` respectively -- that are **not one of the Final PRD's own
  four delivery-model categories** ("software, service, marketplace, physical", Section 4 Group
  B). Checked `wi/extract/prompt.py`: the model was never told this vocabulary exists anywhere.
  The field's only guidance was rule 8's single worked example, which teaches exclusively the
  SaaS/software inference pattern -- nothing at all for a company whose product ships through a
  dealer network (bajajauto) or as professional services (thoughtbot). Both models' answers
  accurately describe what each company does; neither answers the field's actual question (how
  the product *reaches the customer*), because nothing ever told them that distinction mattered.
- **zerodha.com (incorrect):** the model's `"software as a service"` is directionally correct
  (the hand label says "Online software platform...") but scores `incorrect` under
  `wi/eval/scoring.py`'s deliberate exact-match-after-normalising comparison (see that module's
  own docstring, which explicitly names this field as one expected to suffer this way) -- not a
  model or prompt bug.

**Fix implemented:** rule 12 in `wi/extract/prompt.py`'s `SYSTEM_PROMPT`, giving the model the
PRD's own four-word vocabulary directly, with guidance mapping non-software business shapes to
categories (dealer/retail network -> physical; consulting/agency/freelance -> service; two-sided
transaction platform -> marketplace; software however delivered -> software, per rule 8), and a
worked example (a dealer-network page) contrasting the correct `"physical (dealer network)"`
against the wrong `"manufacturing"` -- describing what the company makes instead of how its
product reaches the customer. This is the same category of fix as rule 10's announcements array:
**implementing an already-written, explicit PRD requirement the prompt never actually carried, not
a new bounded prompt-optimisation trial** -- so it doesn't draw on Week 3's already-flagged
trial budget the way rules 9 and 11 did. `prompt_version` bumped 5 -> 6 in config.yaml (a prompt
text change; no `EXTRACTION_LOGIC_VERSION` bump needed, since no deterministic checking code
changed). New test in `tests/test_prompt.py` confirms the vocabulary and the "don't invent your
own category" instruction both reach the model. Full suite: **259/259** (was 258; 1 new test, 0
regressions).

**What this fix will and won't move, flagged plainly rather than overclaimed:** rule 12 should fix
the two genuine category errors (bajajauto, thoughtbot) and may help darwinbox commit to an answer
instead of abstaining, once measured on a live re-run. It will very likely **not** flip zerodha's
verdict to `correct` -- that hand label's wording ("Online software platform...") doesn't start
with the PRD's literal category word, so no non-paraphrasing prompt fix can close that gap without
either loosening `wi/eval/scoring.py`'s deliberate exact-match scorer (already explicitly declined
for this project, for good reason -- see that module's docstring) or tightening this field's
hand-label wording toward the PRD's own four-word vocabulary. **Flagging this hand-label-wording
question for Uttam's decision rather than editing eval/labels/*.json unilaterally** -- these are
his own hand-authored ground truth, and the tension is a real methodology question (should
delivery_model labels lead with the literal PRD category word?), not a bug I should quietly patch
around.

**Not yet done:** a live `--no-cache` re-run to confirm rule 12's actual effect (same live-access
limitation as B-36 -- this session can read and reason about real pages via WebFetch but cannot
run Uttam's actual crawler/LLM pipeline against them).

### Abhishek's sign-off, decisions 2-6: the remaining Section 14 decisions all approved as proposed (2026-09-27)

Uttam confirmed Abhishek's sign-off on the last five items of PRD Section 14, all approved exactly
as proposed with no changes requested:

- **Decision 2** (benchmark split and selection rule, Appendix A): the 8 development-set / 10
  held-out-set list, both slots (H5, H10) since filled and every site verified against the
  checklist -- see `eval/benchmark_sites.md`.
- **Decision 3** (the confidence rule in Section 5: rule-derived, shown as High/Medium/Low).
- **Decision 4** (the "supported website" definition in Section 11).
- **Decision 5** (the cut order in Section 10).
- **Decision 6** (news items, including the "legal or regulatory" category, are shown only as
  labelled third-party reported events and are never scored or turned into conclusions -- already
  the exact shape `tests/BEHAVIOURS.md`'s B-22 through B-25 describe for the still-`todo` Week 4
  P1 news feature, so this confirms the existing plan rather than changing it).

Together with decision 1 (Section 13 parameters, confirmed earlier this session), **all six PRD
Section 14 decisions are now confirmed** -- nothing remains open in that section.

Updated `eval/benchmark_sites.md`'s header (was "verified 2026-09-26, pending Abhishek's approval",
now records the 2026-09-27 approval and cites decision 2 by number), matching the same pattern
decision 1's sign-off used for `config.yaml`/`README.md`. No functional or code change for
decisions 3-6 -- Sections 5, 10 and 11's rules aren't implemented yet (they land with `wi/profile/`
and the Week 4 news feature), and B-22 through B-25 already describe decision 6's exact requirement
as a still-`todo` acceptance test; this is a documentation update recording approvals that just
happened, not new work.

**Deliberately left untouched**: every historical narrative comment in this file and in
`wi/extract/prompt.py`/`config.yaml` that describes rules 10 and 11 as proceeding "flagged for
Abhishek's awareness alongside the other open Section 14 decisions" -- those are point-in-time
journal entries explaining the reasoning at the moment each trial was decided, not a live status
flag, so rewriting them now to say "resolved" would misrepresent what was actually known when that
decision was made. This new section is the current record of the resolution instead.

Full suite unaffected by this change (**259/259**, no code touched) -- re-run to confirm after the
documentation edit, then synced to device.

### `_to_delete/` cleanup closed (2026-09-27)

Uttam manually deleted the leftover `_to_delete/` folder (a stray `patch_b06.py` transfer script,
flagged since the B-06 fix earlier this session -- delete permission was declined at the time, so
it had sat waiting for Uttam to remove it himself). Confirmed gone on the device (`ls` no longer
shows it). No files/tests affected -- this closes a pure housekeeping backlog item, nothing to
sync.

### B-38 fixed: pricing.revenue_model's over-inference, a guessed conclusion with no evidentiary link to revenue at all (2026-09-27)

Uttam's pick from the remaining backlog (root-cause and fix `pricing.revenue_model` over-inference,
the other flagged-but-unpursued candidate alongside `products.delivery_model`, using the same
approach: read the real data first, don't guess).

**Root cause, found by reading `eval/baseline_report.json`'s per-field breakdown against
`eval/labels/*.json` and `data/runs/*.json`'s actual claims:** this field scored 0.2 accuracy (1
correct_abstention, 1 incorrect, 1 miss, **2 `unsupported`** -- the PRD's most serious verdict).
The two `unsupported` cases:

- **bajajauto.com:** inferred `"product sales"` from the evidence "Bajaj Auto is the first
  two-wheeler and three-wheeler company in the world to have reached a market capitalisation of
  INR one trillion." -- a fact about company valuation, not about how the company charges for its
  product.
- **thoughtbot.com:** inferred `"project-based"` from "We specialize in building and modernizing
  software where reliability, compliance, and long-term maintainability matter as much as speed."
  -- a positioning/quality statement, not about billing structure.

Both hand labels say `not_found` -- correctly, since neither crawled page states or implies an
actual revenue model. Neither quote is a legitimate rule-8-style indirect inference (a real, if
implicit, topical link between quote and conclusion, the way `products.delivery_model`'s
"install-free multi-device access implies SaaS" genuinely is); both are free-associated guesses
with zero evidentiary connection to revenue at all -- exactly what rule 4 ("prefer not_found over
guessing") exists to prevent, and a materially different failure mode from B-03's already-fixed
pattern (a specific WRONG conclusion -- subscription -- from a specific evidence shape --
contact-sales). `check_claim()` deliberately exempts every inferred claim from
`value_supported_by_quote()`'s word-overlap check (a legitimate inference routinely shares no
words with its quote), but that exemption had no floor at all -- any quote could support any
conclusion, so long as the quote itself was real page text.

**Fix implemented** in `wi/validate/evidence.py`: a new, field-scoped guard,
`_revenue_model_inference_lacks_pricing_signal()`, checking whether an inferred
`pricing.revenue_model` claim's quote contains ANY term even plausibly about pricing, billing, or
how money changes hands (currency symbols, "price"/"fee"/"cost"/"bill"/"charge"/"subscription"/
"contract"/"pay"/"sale"/"purchase"/and similar) -- not word-overlap with the specific value, just
SOME topical connection to revenue at all. Deliberately uses currency **symbols** ($, ₹, €, £),
never bare currency **codes** ("INR", "USD") -- the real bajajauto.com quote that should be
rejected literally contains "INR" (spelled out as "INR one trillion", no symbol), so a
codes-based check would have let the exact bug back in. Scoped to `pricing.revenue_model` only,
same as the existing B-03 guard -- `products.delivery_model`'s own legitimate indirect-inference
pattern (rule 8) is completely untouched, confirmed by a dedicated test.
`EXTRACTION_LOGIC_VERSION` bumped 6 -> 7 (a deterministic checking-code change, not a prompt
change, so `prompt_version` is unaffected this time).

**Tests added** (`tests/test_evidence.py`): both real live over-inferences reproduced directly
against `check_claim()` (rejected); a genuine pricing-signal quote (unaffected, still passes); a
dedicated scope-isolation test confirming `products.delivery_model`'s legitimate inference pattern
is untouched; and a dedicated test confirming a bare currency code ("INR" in the real market-cap
sentence) does NOT count as a pricing signal on its own. Full suite: **264/264** (was 259; 5 new
tests, 0 regressions).

**Not yet done**: same limitation as B-36 and rule 12 -- a live `--no-cache` re-run to confirm this
actually flips bajajauto's and thoughtbot's `revenue_model` claims to the correct `not_found`
rather than the previously-accepted wrong inference, once `EXTRACTION_LOGIC_VERSION`'s bump forces
a genuine re-check. This session can reason about and test the deterministic logic in isolation
but cannot run Uttam's actual crawler/LLM pipeline against the real sites.

## Log

| Date | Done | Blocked | Next |
| --- | --- | --- | --- |
| 2026-09-26 | Fixed schema gap (added `pricing.revenue_model` to FIELDS, now 15 fields). Closed 6 of 7 remaining Week 2 code gaps: duplicate-page dedup, redirect-cap reporting, JS-only fallback (Playwright, off by default), run-level caching, a realistic 10k-page cap test, plus updated BEHAVIOURS.md and run_site.py to match. Verified all 18 Appendix A benchmark sites against the PRD's checklist. Drafted hand-labels for all 5 dev-set companies (flagged as needing independent review). **Week 1 Day 5 gate run and PASSED** against basecamp.com (15/15 schema-valid, 8/8 populated evidenced). **Ran the full 5-site dev-set baseline, all PASSED**: Basecamp (8/15 populated), Darwinbox (1/15 -- confirms the predicted JS-heavy problem, deliberately deferred as a JS-fallback follow-up), Zerodha (6/15), thoughtbot (2/15), Bajaj Auto (13/15 -- the strongest result, after fixing a crash on its first attempt). Five real bugs surfaced by these live runs, all fixed with new tests: a prompt bug (model echoing a worked example's basecamp.com-specific text), a content-type gate for linked PDFs that crashed Bajaj Auto's first run (B-27), actual enforcement of the previously-declared-but-unused `llm.max_input_tokens_per_run` (B-28), the evidence checker accepting a quote from a page's `<title>` (B-29), and normalising `source_url` before the evidence-text lookup plus recording it on rejection for diagnosis (B-30) -- found when an *exact* string match (claimed value == evidence, both "Bajaj Auto") still failed, which only a URL-lookup miss explains. All 139 tests pass. | H5 Tata Motors and H10 still need a human pick before the benchmark list locks. Abhishek's formal sign-off on provider choice and Playwright permission is still worth getting even though the pipeline now runs technically. 5 hand-labels still need independent review. B-30's fix hasn't been re-confirmed against a live run yet (landed right after the last one). | Spot-check B-30 on the next live run. Come back to Darwinbox and test the JS fallback for real. Pick H5's replacement and H10. Get Abhishek's sign-off. B-19 (limit_reached) still waits on wi/profile/ existing (Week 3). |
| 2026-09-26 | Followed up on Darwinbox specifically: Uttam installed Playwright and enabled `js_fallback_enabled`, but the re-run came back byte-identical (cache hit, still 3 pages, no JS-rendered pages) -- the fallback never fired at all. Diagnosed and fixed a real drift bug (B-31): `wi/crawl/js_fallback.py`'s `visible_text_length()` stripped only script/style/noscript, not nav/header/footer like `wi/crawl/clean.py`'s fallback extractor it claimed to match, so a nav/footer-heavy SPA shell's boilerplate text alone cleared the 200-char threshold and `needs_fallback()` wrongly said the page had enough content. Fixed by promoting `clean.py`'s `_fallback_text` to a public `extract_fallback_text` and having `visible_text_length()` reuse it directly instead of a second copy. Added 2 regression tests reproducing the Darwinbox shape offline. Full suite now 141/141. | Fix not yet re-confirmed against a live Darwinbox run (needs_fallback() runs before the cache layer, so a fresh run should actually invoke Playwright this time, but that's still unverified against the real site). | Ask Uttam to re-run `python run_site.py https://darwinbox.com/` and check the gate again to confirm the fallback now triggers and improves the result. Then: pick H5's replacement and H10, get Abhishek's sign-off, independent review of the 5 hand-labels, B-19 waits on wi/profile/ (Week 3). |
| 2026-09-26 | Darwinbox re-runs after B-31 kept showing no improvement and no "JS-rendered" pages. Added a diagnostic to run_site.py (prints per-page fetch error when nothing succeeds, instead of a bare "nothing to extract"), which surfaced that a re-run variance (2 vs 3 pages) was ordinary live-site noise, not a bug. The real remaining bug (B-32): `render_with_playwright()` required Playwright's strict `networkidle` wait to succeed, which a real site with a chat widget or analytics beacons polling forever may never reach, silently discarding an already fully-loaded render every time -- and the function's blanket except swallowed the reason too. Fixed by only requiring `"load"` to succeed and treating `networkidle` as best-effort, plus printing real failures to stderr. 2 new regression tests, full suite now 143/143. | Fix not yet re-confirmed against a live Darwinbox run -- this is the third fix in the JS-fallback chain (trigger measurement, then render resiliency), each only surfaced by actually running the previous fix live. | Ask Uttam to re-run `python run_site.py https://darwinbox.com/` once more and check whether "N JS-rendered" now appears and the result improves. Then: pick H5's replacement and H10, get Abhishek's sign-off, independent review of the 5 hand-labels, B-19 waits on wi/profile/ (Week 3). |
| 2026-09-26 | Bumped `js_fallback_timeout_s` from 15 to 30 to test whether B-32's timeout was just too short -- it wasn't. `/cortex` still failed, but this time with a real diagnostic: `page.goto(..., wait_until="load")` timed out completely even at 30s. Root cause (B-33): `"load"` requires every subresource on the page to finish, and just one hung request (very plausible: an anti-automation heuristic reacting to headless Chromium) blocks it forever no matter the timeout. Fixed by making `"domcontentloaded"` the only required wait -- the condition CRL-04 actually needs -- with `"load"`/`"networkidle"` both demoted to best-effort follow-ups. Confirmed via the run's own output that the homepage correctly never attempted the fallback at all (its 235 real chars sit just above the 200-char threshold -- expected, not a bug). 1 net new regression test (2 renamed/restructured), full suite now 144/144. | Fix not yet re-confirmed against a live Darwinbox run -- three fixes deep in the same JS-fallback chain now (trigger measurement, networkidle resiliency, load resiliency), each only surfaced by actually running the previous one live. If domcontentloaded still doesn't produce a JS-rendered page, the next hypothesis is genuine bot-detection blocking headless Chromium outright rather than a wait-condition issue. | Ask Uttam to re-run `python run_site.py https://darwinbox.com/` once more and check for "N JS-rendered" in the summary. Then: pick H5's replacement and H10, get Abhishek's sign-off, independent review of the 5 hand-labels, B-19 waits on wi/profile/ (Week 3). |
| 2026-09-26 | **Darwinbox JS-fallback CONFIRMED WORKING end-to-end.** The `domcontentloaded` fix (B-33) got past every earlier timeout: 8 pages fetched (up from 3), 2 JS-rendered, `/cortex` went from 130 static chars to 1745 rendered chars, and several previously-unreachable priority pages (`explore.darwinbox.com` customer stories, industry recognition, about-us, partner-with-us) got crawled once Playwright's rendered nav links existed. Gate PASSED: 15 schema-valid, 3/3 populated claims evidenced -- up from Darwinbox's original 1/15. One page (`/experience-cortex`) still times out even on domcontentloaded but degrades gracefully as designed (keeps its 41-char static content, doesn't block the run) -- not investigated further. This closes the B-31/B-32/B-33 chain: all three were needed, and all three are now validated against the real site that surfaced each one. | Two smaller, non-urgent findings from this same run for Week 3 tuning: two schema pairing mismatches (values/evidence count mismatch, safely downgraded by the existing validator) and one evidence-quote rejection on `traction.named_customers` that may be a smart-quote (’) vs straight-quote (') mismatch, unconfirmed. Also still open from earlier: H5/H10 benchmark picks, Abhishek's sign-off, independent hand-label review, B-19 waiting on wi/profile/. | Dev-set baseline round is fully closed out (all 5 sites PASS, no deferred items). Next natural step is Week 3: prompt/field tuning, wi/profile/ (unlocks B-19), or the smart-quote evidence-matching investigation above -- whichever Uttam wants to pick up. |
| 2026-09-27 | **Started Week 3.** Built `wi/profile/builder.py`: OUT-01's second output (canonical profile, derived from already-validated claims, referencing claim IDs), separate from the evidence ledger. Maps the 15 frozen fields onto the PRD's 6 profile groups, places only `extracted`/`inferred` fields under their group heading (not_found/conflicting both go to `gaps_conflicts` instead, per PRD Section 6 item 9 and EVD-05), computes a coverage strip (pages scanned, populated/inferred/conflicting/not_found counts, `evidence_support_rate` = populated / (populated + rejected)), and sets `limit_reached` (B-19) from either the input-token-budget guard (B-28's `dropped_pages`) or the crawl's own page/depth cap (`CrawlResult.budget_exhausted`). Wired into `run_site.py` -- output JSON keeps its existing `"claims"` key (no breaking change to `eval/check_gate.py`) and adds `"profile"`, `"schema_version"`, `"limit_reached"`. 16 new tests in `tests/test_profile.py`, including a living-contract test that fails if a future field's prefix has no `GROUP_MAP` entry. Full suite: 160/160. This closes B-19, previously blocked all the way back to Week 2 on this exact module not existing. | Not yet run against a live site -- next dev-set re-run will exercise the real `"profile"` output for the first time outside the test suite. Two remaining Week 3 workstreams (field-level accuracy baseline against the 5 hand-labels, then a bounded prompt-optimisation trial) haven't started. Several individually-tracked PRD behaviours (B-01/02/03/06/07/08/10/18, all still `todo` in BEHAVIOURS.md) may already pass against the current pipeline and just need tests written, or may not -- unknown until the baseline runs. | Sync to device, verify full suite there, then either: run a live dev-set site to see the new profile output for real, or move straight to the field-level baseline (the more informative next step per the user's own Week 3 priority pick). |
| 2026-09-27 | **Confirmed the profile output live** against a fresh darwinbox.com run (8 pages, cache miss). Output matched design exactly: 7 fields populated (4 `extracted` -- name, description, industries, certifications -- and 3 `inferred` -- `products.delivery_model`, `pricing.sales_motion`, `pricing.revenue_model`) under their group headings with claim_ids attached; `company_comparisons` correctly rendered as an empty group (`{}`) rather than omitted, since no field mapped there this run; the one evidence-rejected claim (`products.names`, its quote didn't match the crawled page text) correctly appears in `gaps_conflicts` with its replacement claim_id rather than under `products_services`. Coverage strip matched hand-computed values: `evidence_support_rate: 0.875` = 7 populated / (7 populated + 1 rejected), `fields_not_found: 8`. `limit_reached: true` fired correctly off `crawl_budget_exhausted` alone (`dropped_pages` was empty) -- the first live exercise of that half of the OR condition; tests had covered it but no real crawl had hit it yet. Full 6-task Week 3 canonical-profile workstream (design through live verification) is now complete. | No `conflicting`-status claims appeared in this run, so B-06's known gap (conflicting claims skip evidence verification in `wi/validate/evidence.py`/`pipeline.py`) still hasn't been exercised live -- remains open, tracked separately, not addressed this session. Two remaining Week 3 workstreams (field-level accuracy baseline, then a bounded prompt-optimisation trial) haven't started. | Move to the field-level accuracy baseline against the 5 hand-labels (PRD Section 12 scoring: Correct / Incorrect / Correct abstention / Miss / Unsupported) -- the second Week 3 workstream, and the one Uttam didn't pick first but that's next in sequence. Only after that baseline exists does the PRD's Week 3 gate allow the one bounded DSPy/prompt-optimisation trial. |
| 2026-09-27 | **Built and ran the field-level accuracy baseline.** `wi/eval/scoring.py` (pure scoring logic, PRD Section 12's 5 cases plus a documented `conflicting` extension for AC-11) + `eval/baseline.py` (pairs each dev-set label with its run JSON, no LLM call). 21 new tests, full suite 181/181. **Real result against the 5-site dev set: 28% headline accuracy** (3 correct, 18 correct_abstention, 20 incorrect, 28 miss, 6 unsupported, 0 conflicting, of 75 field-checks) -- extraction accuracy 21%, inference accuracy 0%, well under AC-02's 80% target, as expected for a first un-tuned baseline. Full per-field detail in `eval/baseline_report.json`. Five things identified as blended into that number, from least to most actionable: strict non-paraphrase scoring on free-text fields (may overstate real error), no partial credit on list fields, genuine crawl-coverage misses (pages never fetched), a **new recurring evidence-check rejection on easy fields** (`company_identity.name` downgraded to not_found on 3/5 sites -- same bug class as B-29/B-30, root cause unknown since the original rejection reason wasn't captured for these older runs), and a **real over-inference pattern**: `pricing.revenue_model` confidently inferred on 3/5 sites where the label says not_found at all (no pricing signal on the site whatsoever) -- a specific, credible prompt-tuning target. | The evidence-rejection-on-easy-fields finding needs a fresh run with the rejection reason actually captured before its root cause is known -- not yet done. Field-level baseline workstream is otherwise complete; the bounded prompt-optimisation trial (Week 3's third and final piece) hasn't started and per the PRD's own gate shouldn't be tuned blind against noise this baseline hasn't yet separated out. | Uttam's call: (a) re-run a site or two to capture the evidence-rejection reason and chase that bug first (higher-confidence, testable), (b) go straight at the `pricing.revenue_model` over-inference pattern as the prompt-optimisation trial's target, or (c) something else. Either way, re-run `eval/baseline.py` afterward and diff against `eval/baseline_report.json` to see whether the change actually moved the needle -- that diff is the whole point of having this baseline now. |
| 2026-09-27 | Uttam chose: fix the evidence-rejection bug first. Didn't need a fresh run to see the original rejection reasons after all -- `data/runs/cache/*.json` already had them (that's what B-17's caching writes). thoughtbot's rejection turned out not to be a bug: a real quote, correctly judged not to support "thoughtbot" (EVD-02 working as designed) -- a prompt question, not a code one. zerodha and bajajauto's "quote not found" cases turned up something bigger instead: both cached entries are missing the `source_url` field entirely, proving they were cached *before* B-30 added it -- and `run_fingerprint()`'s cache key (`content_hash+prompt_version+schema_version+model`) has no component for the deterministic checking CODE at all, so a real fix to `wi/validate/evidence.py` can never bust a previously-cached site's result. Every dev-set site has been sitting cached since 2026-09-26 -- B-29/B-30 may already have fixed zerodha/bajajauto, but a routine re-run would never have told us either way, and would have looked exactly like success (`cache_status: "hit"`) either way. **Fixed (B-34)**: added `EXTRACTION_LOGIC_VERSION` to the fingerprint, bumped 1->2, which makes every pre-existing cache entry unreachable and forces an honest re-check on the next run of any dev-set site. 2 new tests in test_cache.py, full suite **183/183**. | The 28% baseline number is now known to be *unverified* against current code, not confirmed wrong -- won't know the real current number until the 5 dev-set sites are re-run and `eval/baseline.py` re-run against fresh output. thoughtbot's real quote-grounding issue on `company_identity.name` is still open, correctly scoped to the prompt-optimisation trial rather than fixed here. | Ask Uttam to re-run all 5 dev-set sites (now guaranteed fresh, not cached) and re-run `eval/baseline.py` to get the real, current-code baseline number before deciding on the prompt-optimisation trial's target. |
| 2026-09-27 | **Config-sync incident, found and fixed within the hour.** Syncing the B-34 fix's `config.yaml` comment update to the device overwrote `llm.provider`/`llm.small_model` back to their placeholder empty strings -- the scratchpad copy of `config.yaml` had never been updated to match the real `openai`/`gpt-4o-mini` values Uttam set on the device back on 2026-09-26 (that edit happened device-side only, never round-tripped into the session's own copy). Surfaced immediately when Uttam tried to re-run all 5 dev-set sites: every one failed with `openai.BadRequestError: you must provide a model parameter` (the run log's "Extracting claims with  ..." showing a blank model name was the tell). Fixed on both the device and the scratchpad copy (`provider: "openai"`, `small_model: "gpt-4o-mini"`), full suite re-confirmed 183/183 on the device (config values aren't exercised by the test suite's fake config, so this couldn't have been caught by tests alone -- a live run was what caught it, same as several other bugs this session). Lesson: any future full-file sync of `config.yaml` must diff against the device's current values first, not just push the scratchpad version. | Uttam needs to re-run the 5 dev-set sites again now that the config is actually fixed -- the previous 5 attempts produced no output at all (crashed before any extraction). | Re-run all 5 dev-set sites, then `eval/baseline.py`, to finally get the real post-B-34 baseline number. |
| 2026-09-27 | **Got the real post-B-34 baseline: 32% (up from stale 28%), extraction accuracy 21% -> 30%.** All 5 sites logged `cache: miss`, confirming a genuine re-check. `company_identity.name`'s 3-site rejection pattern split cleanly in two: bajajauto's exact-string-match rejection is CONFIRMED FIXED (B-30 + B-34 validated live on the exact site/field that first exposed the bug -- it now extracts cleanly, scoring `incorrect` only on a label-wording technicality, "Bajaj Auto Ltd." vs "Bajaj Auto"); zerodha and thoughtbot are CONFIRMED still genuinely rejected, and for the same reason as each other -- the model grounds the name claim in a real but irrelevant quote ("We pioneered the discount broking model in India.", "Our company") rather than one that actually names the company. That's now a clean, evidence-backed prompt-optimisation target (2/5 sites, 40%, on the easiest field on the schema). Also confirmed live, not caching artifacts: `pricing.revenue_model` over-inference persists (bajajauto, thoughtbot both `unsupported`), and a new pattern -- `products.delivery_model` at a flat 0% across all 5 sites, the model substituting a generic label ("software as a service" x2, "manufacturing and distribution") for each site's more specific real answer every time. | Three prompt-tuning candidates now identified and evidenced (`company_identity.name` grounding, `pricing.revenue_model` over-inference, `products.delivery_model` over-generalisation) but none chosen yet -- the PRD only permits one bounded trial. Crawl-coverage misses (34/75, the largest bucket) remain a separate, untouched problem, and darwinbox's js_fallback was off for this run (config default), so its numbers reflect the pre-B-31 3-page shell, not its confirmed-working JS-rendered state. | Uttam's call: pick one of the three prompt-tuning candidates for Week 3's single bounded optimisation trial, per the PRD gate ("keep the optimisation only if held-out gain is measurable and provenance is intact"). Re-run `eval/baseline.py` after the trial and diff against this run's numbers to measure the gain. |
| 2026-09-27 | **Ran the bounded prompt-optimisation trial.** Uttam picked `company_identity.name` grounding. Added rule 9 to `wi/extract/prompt.py` (one paragraph + one fictional worked example) stating directly that a real, on-topic quote can still fail to support a name value if it never contains the name itself -- exactly what `value_supported_by_quote()` already checks but no rule had told the model. Bumped `prompt_version` 0 -> 1 in config.yaml so the 5 already-cached dev-set sites are forced to re-run under the new prompt rather than silently reusing the pre-trial cached answer (same reasoning as B-34's `EXTRACTION_LOGIC_VERSION`, applied to a prompt change instead of a code change). One new plumbing test in `tests/test_prompt.py` (checks the rule's text is in the built prompt; can't itself measure accuracy). Full suite: **184/184**, verified on both scratchpad and device. | Not yet measured live -- per the PRD gate this rule is kept only if a re-run shows a real, held-out gain on zerodha/thoughtbot without regressing other fields. | Ask Uttam to re-run all 5 dev-set sites (now guaranteed to bypass both the logic-version and prompt-version cache keys) and re-run `eval/baseline.py`, then diff company_identity.name's per-field result against this session's 32%/40% baseline to decide whether to keep rule 9. |
| 2026-09-27 | **Measured the trial: null result, reverted rule 9.** Re-run showed zero claims flip from rejected to correct on the targeted field -- thoughtbot's rejection was byte-for-byte identical before/after (same value, same wrong quote), zerodha's persisted with a different but still-unsupporting quote, bajajauto was unaffected either way. Headline 32%->31%, extraction 30%->17%, but the extraction drop is confounded by an unrelated darwinbox crawl timeout this run (excluded from judging the trial, not counted as a regression). Per the PRD gate and this session's own stated commitment, no held-out gain was measured, so rule 9 does not earn its keep. Reverted `wi/extract/prompt.py` (rule 9 + worked example removed), `config.yaml` (`prompt_version` 1 -> 0), and `tests/test_prompt.py` (its plumbing test removed). Full suite back to **183/183**, verified on both scratchpad and device. | None -- Week 3's bounded-trial line item is closed with a documented null result. Two other evidenced candidates (`pricing.revenue_model` over-inference, `products.delivery_model` flat 0%) remain unpursued, and the PRD frames the trial as a one-shot, so pursuing either needs Uttam's explicit go-ahead as separate, new work rather than "reopening" this trial. | Report the null result to Uttam plainly. Ask how he wants to proceed on Week 3's remaining work: pick a different candidate for a fresh bounded trial, propose a revised name-grounding approach (e.g. pointing the model more forcefully at page `<title>` text) as a new trial, or close Week 3's tuning line item here and move to the still-open items (B-06 conflicting-claim evidence bypass, B-01/02/03/07/08/10/18, H5/H10 benchmark picks, Abhishek's sign-off, independent hand-label review, crawl-coverage misses). |
| 2026-09-27 | Uttam chose to take a second, separately-scoped bounded trial at `company_identity.name` grounding: **rule 9 take 2, "title-pointing"**. Added a fresh rule 9 to `wi/extract/prompt.py` instructing the model to check each page's TITLE line first for a name-field quote (a page's own title very often names the company even when body text doesn't), with a worked example built around a fictional company. No evidence.py change needed -- B-29 already made title text checkable, this only points the model there. Bumped `prompt_version` `"0"` -> `"2"` (skipping `"1"`, take 1's dead value, so this trial's re-run can't collide with take 1's retired fingerprint). One new plumbing test in `tests/test_prompt.py`. Full suite: **184/184**, verified on both scratchpad and device. | Not yet measured live -- same PRD gate as take 1: kept only if a re-run shows a claim actually flip from rejected to correct on zerodha and/or thoughtbot, not just a different wrong quote (take 1's actual failure mode), without regressing other fields. | Ask Uttam to re-run all 5 dev-set sites and `eval/baseline.py`, then check whether `company_identity.name` actually extracts correctly on zerodha/thoughtbot this time before deciding whether to keep rule 9 take 2. |
| 2026-09-27 | Uttam ran the 5 dev-set sites + `eval/baseline.py` **twice in a row** under rule 9 take 2 (same code, same `prompt_version: "2"`, both `cache: miss`). Wildly inconsistent result on the targeted field: Run A -- `company_identity.name` 20% (only basecamp correct; zerodha and thoughtbot both still evidence-rejected, thoughtbot's wrong quote byte-for-byte identical to both the pre-trial baseline and take 1's failure). Run B, immediately after -- `company_identity.name` **80%** (basecamp, zerodha, thoughtbot, AND darwinbox all correct; only bajajauto's "Ltd." label-wording quirk remains). Same crawled pages both runs for the 4 non-darwinbox sites, so the only variable is the model's own sampling (`llm.temperature: 0.1`, not 0) -- the title-pointing mechanism clearly *can* work (Run B proves it), but isn't yet reliable run to run. Documented both runs in full in PROGRESS.md. No keep/revert decision made -- two data points isn't enough to call this "measurable gain" or "no gain" with confidence either way. | Whether to keep, revert, or gather more repetitions before deciding is genuinely Uttam's call given the conflicting evidence -- not decided yet. | Asked Uttam how he wants to proceed: run a few more repetitions to see which outcome predominates, or make the keep/revert call now given the mixed evidence. |
| 2026-09-27 | Uttam chose to gather 3-5 more repetitions. The very next run caught a real methodology bug before it could corrupt the measurement: 4 of 5 sites (basecamp, darwinbox, zerodha, thoughtbot) logged `cache: hit` -- the exact same fingerprint as the immediately-prior Run B under unchanged `prompt_version: "2"`, so the "third run" silently replayed Run B's literal cached payload instead of drawing a fresh, independent sample from the model (confirmed: its `company_identity.name` 80% result matched Run B exactly, correct=4/incorrect=1). Only bajajauto called the LLM fresh, because its live crawl happened to pick up a slightly different duplicate/PDF count this run. This is `wi/crawl/cache.py`'s whole-site fingerprint doing exactly its job (CST-01: never re-bill an unchanged site) but working against the specific need here (a genuinely independent draw each time to measure sampling variance). **Fixed properly**: added a `--no-cache` flag to `run_site.py` (`python run_site.py <url> --no-cache`), passing `cache=None` through to the already-cache-optional `extract_claims()` so a flagged run neither reads nor writes the cache. Not unit-tested (run_site.py is a live-network CLI entry point, consistent with its existing untested status) -- verified via `ast.parse` plus the full suite staying green (184/184, unaffected). Synced to device, checksums verified. | None on this specific fix -- it's a clean, isolated tooling addition. The repeat-run measurement itself is still incomplete: only Run A and Run B are genuine independent samples so far; the run that surfaced this bug doesn't count as a third one. | Ask Uttam to re-run the remaining repetitions with `--no-cache` (e.g. `python run_site.py https://zerodha.com/ --no-cache`) for all 5 sites each time, so every rep is a real, independent sample before tallying `company_identity.name`'s reliability across runs. |
| 2026-09-27 | Uttam re-ran the 5-site sequence again, but without the new `--no-cache` flag (likely re-ran from shell history before the fix landed in his working copy) -- same result as the run that surfaced the bug: basecamp/darwinbox/zerodha/thoughtbot all `cache: hit`, only bajajauto `cache: miss` (again from ordinary live-crawl variance in its duplicate/PDF count, not a genuine repeat sample of the trial). `company_identity.name` came back 80%, correct=4/incorrect=1, identical to Run B and the previous cache-hit run -- confirming again this isn't new data. No code change needed; this is user-side, not a bug. | Still only 2 genuine independent samples exist (Run A: 20%, Run B: 80%). | Told Uttam explicitly to include `--no-cache` on every `run_site.py` line this time, and to check for the "(--no-cache: forcing a fresh LLM call...)" print on each site as confirmation before trusting the next result. |
| 2026-09-27 | **Got a genuine third independent sample ("Run C") with `--no-cache` confirmed on all 5 sites.** `company_identity.name` 80% (basecamp/zerodha/thoughtbot/darwinbox correct, only bajajauto's pre-existing label-wording quirk incorrect). Tally across all 3 genuine runs on the two target sites: A = both rejected, B = both correct, C = both correct -- 2 of 3 favour the fix, and the mechanism never produces a mixed per-site result (works on both or fails on both together). Headline accuracy stable across all three runs (31%/35%/36%), no regression elsewhere attributable to rule 9. Documented the full tally and reasoning in PROGRESS.md. No code changes this row -- pure measurement and documentation. | Keep vs. revert vs. gather more reps on rule 9 take 2 is still undecided -- a real, evidenced 1-in-3 failure rate exists (Run A), not just noise dismissed away. | Report the 3-run tally to Uttam and ask how he wants to close this out: keep it given the 2/3 majority, gather 1-2 more `--no-cache` reps for higher confidence first, or revert given the demonstrated unreliability. |
| 2026-09-27 | **Uttam decided: KEEP rule 9 take 2.** Given 2 of 3 genuine independent runs favourable and no observed regression elsewhere, he chose to keep it rather than gather more reps or revert. No code change needed -- `wi/extract/prompt.py`'s rule 9 and `config.yaml`'s `prompt_version: "2"` were already in place and synced on both scratchpad and device from when the trial was built. This closes Week 3's single bounded prompt-optimisation trial (PRD Section 10 permits exactly one; take 1 + take 2 together count as that one trial, same target field throughout). Full suite reconfirmed 184/184 on both sides after the documentation update, checksums matched. | None on this line item -- it's closed. | Move to the still-open Week 3/backlog items: B-06 (conflicting-claim evidence bypass), B-01/02/03/07/08/10/18 (all still `todo`), H5/H10 benchmark picks, Abhishek's sign-off, independent review of the 5 hand-labels, and crawl-coverage misses (the largest single bucket in every baseline run, untouched so far). Uttam's call which to pick up next. |
| 2026-09-27 | Uttam ran two more `--no-cache`-confirmed reps after the keep decision (Runs D and E, not requested but freely offered extra confirmation). Both: `company_identity.name` 80%, zerodha and thoughtbot both correct again, bajajauto's sole "incorrect" the same pre-existing "Bajaj Auto Ltd." vs "Bajaj Auto" label-wording quirk seen in every run this session. Headline accuracy 36% (D) and 39% (E), consistent with the prior stable band (31%/35%/36%) -- no regression anywhere traceable to rule 9. Updated tally across all 5 genuine independent runs on the two target sites: A = both rejected, B/C/D/E = both correct -- 4 of 5, not 2 of 3. This is additional confirmation of an already-made decision, not a new decision point; recorded here purely for the record since it strengthens the evidence behind "keep" further. No code or config changes. | None -- purely confirmatory data on a closed line item. | No action needed on rule 9 take 2. Same open backlog as above. |
| 2026-09-27 | **Run F (another `--no-cache`-confirmed rep) and a new, separate finding.** `company_identity.name` 80% again, zerodha and thoughtbot both correct -- tally on the two target sites now 5 of 6 genuine runs favourable (A the lone failure). Separately, this run surfaced a recurring pattern worth tracking on its own: 3 schema-validation failures across this run and earlier ones this session (Run F's basecamp: `customers.segments` given as a list when the field isn't in `MULTI_VALUE_FIELDS` and must be a single string, plus `comparisons.named_alternatives` with evidence/value array-length mismatch; Run F's zerodha: `products.names` evidence/value length mismatch 8 vs 4; the same two error shapes also appeared in at least two earlier genuine runs this session). Traced in `wi/extract/pipeline.py` (lines ~235-240): any claim that fails Pydantic validation is silently converted to a `not_found_replacement` and logged only in `schema_errors`, not `rejected` -- meaning every one of these is scored as a "miss" in `eval/baseline.py`, indistinguishable from a genuine crawl-coverage gap or the model simply not finding the fact. This is intermittent model non-compliance with rules 5 (multi-value field membership) and 6 (array evidence pairing) at `llm.temperature: 0.1`, not a code bug -- the pipeline's handling of it (never crash, always downgrade to an honest not_found) is correct and intentional. Recording it as a fourth evidenced-but-unpursued prompt-tuning candidate, alongside `pricing.revenue_model` over-inference and `products.delivery_model` over-generalisation -- not investigated further this session since Week 3's one bounded trial is already spent. | None on rule 9 (still closed, still 5/6). The new schema-compliance pattern is flagged, not fixed -- no code change made, no investigation beyond tracing it to its exact cause in pipeline.py. | Uttam's call: keep gathering `--no-cache` reps (though the rule 9 question is well past a confident answer now), pick up one of the four now-evidenced prompt-tuning candidates as a genuinely new trial, or move to the older open backlog (B-06, B-01/02/03/07/08/10/18, H5/H10, Abhishek's sign-off, hand-label review, crawl-coverage misses). |
| 2026-09-27 | Caught and fixed a sync-drift bug before it caused a live failure: `requirements.txt` had silently diverged (device had an extra `lxml_html_clean>=0.4.0` line added directly there, never round-tripped into the scratchpad copy) -- same class of bug as the earlier config-sync incident. Fixed on the scratchpad side (device was already correct); checksums matched after. Uttam then delegated the next-step choice; chose **B-06** over a fifth prompt trial (Week 3's one bounded trial is already spent on rule 9) since it's a concretely scoped, PRD-evidenced correctness gap. **Fixed B-06/EVD-05**: conflicting claims previously had zero schema requirements and were never checked against real page text at all (`check_claim()` short-circuited them to `True`, and `pipeline.py` never called any check function for that status) -- a hallucinated conflict would have sailed through unverified. Fixed by extending the existing paired value/evidence array mechanism (built for `MULTI_VALUE_FIELDS`) to `conflicting` claims on any field: schema now requires >=2 differing values with matching evidence (`wi/schemas/claim.py`); new `check_conflicting_claim()` verifies each quote against the whole crawled corpus, not one fixed page, since a conflict's two values come from two different pages (`wi/validate/evidence.py`); pipeline now actually calls it and downgrades fabricated conflicts to `not_found` (`wi/extract/pipeline.py`); prompt's conflicting-status rule reworded to specify the paired-array format (`wi/extract/prompt.py`); `EXTRACTION_LOGIC_VERSION` 2->3 and `prompt_version` "2"->"3" bumped since both checking logic and prompt text changed. 13 new tests (6 claim, 4 evidence, 2 pipeline, 1 prompt) plus 4 pre-existing tests fixed against the new stricter schema (`test_profile.py`, `test_scoring.py` -- their conflicting-status fixtures needed the new paired-list shape; confirmed neither test's actual assertions depend on value content). `tests/BEHAVIOURS.md` B-06 row: `todo` -> `done`. Full suite **197/197**, independently verified on both scratchpad and a fresh device-side venv; all changed/added files checksum-matched on both sides. | A leftover `patch_b06.py` transfer script sits in `_to_delete/` in the connected folder (delete-permission request was declined) -- needs Uttam to delete that folder himself. Remaining backlog untouched: B-01/02/03/07/08/10/18 (`todo`), H5/H10 benchmark picks, Abhishek's sign-off, independent hand-label review, crawl-coverage misses (still the largest single bucket in every baseline run), and the three other evidenced-but-unpursued prompt-tuning candidates (`pricing.revenue_model` over-inference, `products.delivery_model` flat 0%, the rule 5/6 schema-compliance pattern) for a future trial. | Report B-06 completion and the requirements.txt fix to Uttam; ask what he wants to work on next from the remaining backlog. |
| 2026-09-27 | Uttam picked independent review of the 5 hand-labels next. **Independently re-checked all 5 `eval/labels/*.json` files against live pages via WebFetch/WebSearch** -- a process genuinely separate from both the original Claude-drafted labels and the extraction pipeline's OpenAI calls (though still not a human review, which remains the PRD's actual ask). Basecamp: fully confirmed, no corrections, two things noted and deliberately left alone (a self-assessment-vs-certification distinction, a confirmed-but-partial partnerships list). Darwinbox: **1 correction** -- `company_identity.headquarters` was wrongly `not_found`; the company's own newsroom subdomain explicitly states "Global Headquarters in Hyderabad," now `extracted` (flagged that this is a separate subdomain from the primary crawled site, so a pipeline miss here would be a crawl-coverage gap, not necessarily a bug); also re-confirmed certifications stays `not_found` and the comparison blog page is real. Zerodha: **1 correction** -- `pricing.public_plans`' Kite Connect API line was missing a free "Personal" tier alongside the paid ₹500/month "Connect" tier; added. Bajaj Auto: **1 correction** -- `pricing.sales_motion` was wrongly `not_found`; the live "Book a Test Ride" CTA is a real, stated sales mechanism, now `extracted` as dealer-led. Also spot-checked 3 of 19 bike prices byte-for-byte and re-confirmed the certifications not_found a second way. thoughtbot: **1 correction** -- `customers.industries` was missing "Technical and Business Assistance (TABA)," listed on the site's own industry-expertise heading; added. All corrections additive (a `not_found` becoming `extracted`, or a list gaining a real item) -- nothing previously `extracted` was found wrong. Updated every file's `review_notes`/`labelled_by` to record what was checked. All 5 files re-validated as JSON, synced to device, checksums matched; full suite re-confirmed **197/197** (labels aren't test-covered, checked as due diligence). | Two of the corrections (Darwinbox HQ, Bajaj Auto sales motion) flip a field from `not_found` to `extracted` in the ground truth -- the next `eval/baseline.py` run against existing cached outputs will very likely score those two as `miss`/`unsupported` instead of `correct_abstention`, since the pipeline almost certainly never found either fact. Expected, not a regression, but will move the headline accuracy number. A full human spot-check (Uttam/Abhishek) is still the PRD's actual ask and hasn't happened. | Re-run `eval/baseline.py` against the corrected labels to see the real (likely slightly lower) headline number. Then pick from the remaining backlog: B-01/02/03/07/08/10/18, H5/H10 picks, Abhishek's sign-off, crawl-coverage misses, or a new prompt-tuning trial. |
| 2026-09-27 | **Re-ran `eval/baseline.py`** (no LLM call needed, so run directly rather than asking Uttam). Result: **32% headline** (5 correct, 19 correct_abstention, 17 incorrect, 31 miss, 3 unsupported, 0 conflicting), extraction accuracy **36%** (up from 30%), inference accuracy 0%. Headline is coincidentally flat vs. the last documented number, but the composition shifted as expected (more correct, fewer free-pass abstentions) from the 2 not_found-to-extracted label corrections. Important caveat surfaced and documented: `data/runs/*.json` holds whatever each site's most recent real run left behind, and those files were overwritten by rule 9 take 2's `--no-cache` reps since the last documented baseline -- so this number reflects the corrected labels *and* an already-improved pipeline (rule 9 take 2's `company_identity.name` fix, confirmed showing up at 80%), not the label fix in isolation. None of the cached runs reflect the B-06 fix yet (no site re-run since that landed). No code changes this row -- pure measurement, fully documented in PROGRESS.md. | The two datasets (label corrections, pipeline improvements) are now confounded in this baseline number -- can't be cleanly separated from cached data alone. | If a clean current number matters, re-run all 5 dev-set sites fresh (forced to genuinely re-check anyway, since B-06 bumped both cache-fingerprint components) and re-run `eval/baseline.py` -- that would fold in corrected labels + rule 9 take 2 + B-06 together with no confound. Otherwise, pick up the next backlog item: B-01/02/03/07/08/10/18, H5/H10 picks, Abhishek's sign-off, crawl-coverage misses, or a new prompt-tuning trial. |
| 2026-09-27 | Uttam ran all 5 dev-set sites fresh in his own terminal; confirmed beforehand (direct connectivity check) that this sandbox genuinely can't reach `api.openai.com`, so didn't attempt it here. All 5 logged `cache_status: "miss"` -- B-06's version bump forced the real re-check it was built for. Ran `eval/baseline.py` directly (no LLM call needed). **Clean result, no confound left: 31% headline** (5 correct, 18 correct_abstention, 17 incorrect, 31 miss, 4 unsupported, 0 conflicting), extraction accuracy 36%, inference accuracy 0% -- corrected labels + rule 9 take 2 + B-06 all reflected together for the first time. Essentially identical to the previous confounded read (32%/36%), with the 1-point headline dip explained by one field's ordinary run-to-run sampling variance, not a regression. Positive confirmation the hand-label review mattered: `bajajauto/pricing.sales_motion` (corrected from `not_found` to a real dealer-led description) now scores `incorrect` against a system answer ("direct sales through dealers") that says essentially the same thing in different words -- exactly the documented strict-scoring free-text limitation, now visible instead of hidden behind a false abstention match. No code changes this row -- pure measurement, fully documented. | None -- this line item (re-establishing a clean current baseline number) is closed. Crawl-coverage misses remain the largest bucket (31/75), untouched. | Report the clean number to Uttam. Pick up the next backlog item: B-01/02/03/07/08/10/18, H5/H10 picks, Abhishek's sign-off, crawl-coverage misses, or a new prompt-tuning trial. |
| 2026-09-27 | **Completed the B-01/02/03/07/08/10/18 behaviour-testing pass (Uttam's picked cluster).** Triaged all 7 before writing code: B-01/B-02/B-08 were already correctly handled (dedicated confirmation tests only). Four genuine gaps fixed: B-10 (schema now rejects the literal string "not_found" as an extracted/inferred value -- 2 of 3 "mixed forms" sub-cases were already caught by existing checks); B-18 (pipeline now makes one corrective retry on malformed model JSON before falling back to all-not_found, showing the model its own bad output plus a correction); B-03 (new narrowly-scoped evidence guard stops an inferred pricing.revenue_model claim from asserting "subscription" against contact-sales-only evidence -- the exact live over-inference pattern already documented on darwinbox/bajajauto/thoughtbot this session -- without touching any other inferred field, including B-02's own "sales-led" inference from the identical quote); B-07/OUT-04 (the largest piece -- a wholly new `Announcement` schema, prompt rule, pipeline extraction/validation and profile placement under `evidence_traction`, capturing dated company-reported announcements like funding rounds completely separately from the 15 core fields, per OUT-04's own acceptance criterion). `prompt_version` 3->4 and `EXTRACTION_LOGIC_VERSION` 3->4 bumped to bust every dev-set site's stale cache. 43 new tests (`tests/test_announcement.py` new; additions to test_claim/test_pipeline/test_evidence/test_profile/test_prompt), full suite **197 -> 240, all passing**, verified in the scratchpad. `tests/BEHAVIOURS.md`: all 7 rows `todo` -> `done`. | Not yet synced to or verified on the device -- that's the immediate next step. H5 Tata Motors replacement and H10 sparse-site pick (the other half of Uttam's request this round) haven't been started yet. Crawl-coverage misses remain the largest untouched bucket in every baseline run. | Sync every touched file to the device (checksum-verify both sides), run the full suite there, then move to the H5/H10 benchmark-site research via WebFetch/WebSearch. |
| 2026-09-27 | **Synced the B-01/02/03/07/08/10/18 pass to the device and resolved H5.** All 18 touched files (`wi/schemas/claim.py`, `wi/schemas/announcement.py` new, `wi/extract/pipeline.py`, `wi/extract/schema.py`, `wi/extract/prompt.py`, `wi/validate/evidence.py`, `wi/profile/builder.py`, `run_site.py`, `config.yaml`, `wi/crawl/cache.py`, `tests/BEHAVIOURS.md`, and the six touched/added test files) checksum-matched on the device on the very first `device_commit_files` attempt -- no retry needed. Ran the full suite in a freshly-created Linux venv on the device side (the project's existing `.venv` there turned out to be a macOS-native venv whose symlinks don't resolve inside this session's Linux device shell, so a throwaway venv was built in the shell's own home directory, isolated from Uttam's real environment, and used only to execute pytest against the mounted code): **240/240 passing**, matching the scratchpad run exactly. Then researched and resolved **H5**: Uttam named `azentio.com` as a candidate to replace the already-flagged-weak Tata Motors row; verified it independently (WebFetch for content, robots.txt and reachability; the built-in browser tool as a second, legitimate check when WebFetch alone hit a 403 specifically on `azentio.com/robots.txt` while succeeding on the homepage -- resolved as most likely WebFetch's own fetcher being flagged on that one path, not a site-wide block, and confirmed functionally moot either way since `RobotsGate` treats any non-200 robots.txt as allow-all). Uttam confirmed via AskUserQuestion: Azentio replaces Tata Motors as H5, with the Type column relabeled to "SaaS, BFSI enterprise software, contact-sales" rather than forced into "Manufacturing". Full writeup, the WebFetch/browser discrepancy flag, and a new open item (live crawl spot-check against the project's real httpx client) added to `eval/benchmark_sites.md`; synced to device, checksums matched. See the dedicated "H5 benchmark-site swap" section above for the full detail. | H10 remains the one fully open item -- the earlier candidate (`romsportsacademy.com`) both failed to load and turned out to be Uttam's own company's site (surfaced via the delivered memory snapshot); the clarifying question put to him about it hasn't been answered yet, since his messages since then were only about Azentio/H5. Crawl-coverage misses remain the largest untouched bucket in every baseline run. | Circle back to Uttam on H10 specifically: leave the slot open for his/Abhishek's pick, or confirm romsportsacademy.com is fine to use once it reliably loads. Once H10 is locked, update the Week 1 benchmark-list checklist line and do a final combined sync-and-verify pass. |
| 2026-09-27 | **Resolved H10, closing out the benchmark-list workstream entirely.** Uttam first proposed `hussmann.com`; verified it (content-rich, no pricing/customer content, harmless robots.txt) but flagged two problems -- it isn't actually sparse (H10's requirement) and it's Uttam's own current employer -- so he passed on it and asked to keep looking, pointing at fintech. Researched and compared two real quant-finance candidates known for minimal sites: Renaissance Technologies (rentec.com) and D. E. Shaw Group (deshaw.com), both verified via WebFetch (content + robots.txt). Presented both via AskUserQuestion rather than picking unilaterally, since the PRD leaves this slot to human judgment. **Uttam picked Renaissance Technologies** -- the sparser of the two (single tagline, two office contacts, bare nav, zero-Disallow robots.txt), the closest match to D6 Berkshire Hathaway's profile in either set. Updated `eval/benchmark_sites.md`: filled the H10 row, flipped the top note to "0 open items", and renamed the bottom list from "Open items before this list can be locked" to "Follow-ups" since nothing left in it actually blocks locking. Synced to device (needed one `force: true` retry after an initial checksum mismatch -- same transient pattern seen earlier this session, resolved clean on retry). Full suite re-confirmed **240/240** on both scratchpad and a fresh device-side Linux venv (the device's own `.venv` is macOS-native and doesn't run inside this session's Linux device shell). See the dedicated "H10 benchmark-site fill" section above for full detail. No code changes -- documentation and benchmark-selection work only. | None on this line item -- the Week 1 benchmark-list workstream (18 Appendix A sites verified, both open slots filled) is now fully closed. Crawl-coverage misses remain the largest untouched bucket in every baseline run; several evidenced-but-unpursued prompt-tuning candidates (`pricing.revenue_model` over-inference, `products.delivery_model` flat 0%, the rule 5/6 schema-compliance pattern) also remain for a future trial. | Report the closed-out benchmark list to Uttam. Ask what he wants to pick up next: Abhishek's formal sign-off, a new live 5-site (or now, dev+held-out) run to exercise the fully current pipeline end-to-end, crawl-coverage misses, or a new prompt-tuning trial. |
| 2026-09-27 | **Abhishek's sign-off, decision 1 confirmed: Section 13 parameters approved as proposed.** Uttam confirmed the approval; no parameter changes requested. Updated the "pending approval" framing in `config.yaml` (header comment + `llm.provider` inline comment) and `README.md` (setup instructions) to record the 2026-09-27 approval date instead of an open question -- no functional config change, every value was already exactly what Section 13 proposed. Deliberately left `eval/benchmark_sites.md`'s own "pending Abhishek's approval" note untouched, since that covers Section 14 decision 2 (the benchmark split), a separate still-open decision. Full suite re-confirmed **240/240** (no code touched). Synced `config.yaml` and `README.md` to device, checksums matched. | Four more PRD Section 14 decisions (2-6: the benchmark split itself, the confidence-rule definition, the "supported website" definition, the cut order, and the news-labelling rule) remain unconfirmed by Abhishek. Crawl-coverage misses and the evidenced-but-unpursued prompt-tuning candidates also remain untouched. | Report decision 1's sign-off to Uttam. Ask whether he wants to pursue the remaining Section 14 decisions with Abhishek next, or pick up other backlog work (a new end-to-end live run, crawl-coverage misses, a new prompt-tuning trial). |
| 2026-09-27 | **H5 re-swapped (Azentio -> Temenos) after a live-crawl failure, and a real diagnostics gap found and fixed during the crawl-coverage-misses investigation.** Confirmed neither this session's cloud sandbox nor the linked computer's shell can reach arbitrary external domains (allowlisted to pypi/npm/Anthropic only) -- the "free" live spot-checks asked of Uttam needed his own terminal after all. He ran both: Renaissance Technologies (H10) fully confirmed (8 pages, 1 correctly-functioning evidence rejection); **Azentio (H5) failed with a TLS handshake error** (`TLSV1_ALERT_PROTOCOL_VERSION`, zero pages) -- unrelated to the earlier robots.txt 403, caused by his `.venv`'s old LibreSSL 2.8.3 vs. a server requiring modern TLS. This proved WebFetch/browser-based "verification" (used for every benchmark site all session) doesn't guarantee the project's own crawler can actually reach a site -- documented as a permanent verification-method note in `eval/benchmark_sites.md`. Uttam chose to swap again rather than fix the environment or keep Azentio. Tried Finastra (403, bot-blocked) and Temenos (worked: 25 pages, 0 robots skips, real extraction, 5 correct evidence rejections) -- **H5 is now Temenos**, confirmed via an actual live run. Then, moving into the crawl-coverage investigation itself, found that `run.rejected`/`run.schema_errors` (and the crawled-page list) were always computed correctly but only ever printed to the console, never persisted to `data/runs/<slug>.json` -- meaning a "miss" in `eval/baseline.py` has always looked identical whether the model was rejected, failed schema validation, or never attempted the field. **Fixed**: added `crawl_diagnostics()` (`wi/crawl/fetch.py`) and `diagnostics_from_run()` (`wi/extract/pipeline.py`), wired into `run_site.py`'s output JSON as new additive keys, no version bump needed (doesn't change what a run produces, only what gets written down). 5 new tests, full suite **240 -> 245, all passing**. Using the cache's existing `rejected`/`schema_errors` retroactively, classified the current 31 misses: 10 (32%) are evidence-check rejections (including a likely false negative on basecamp's `pricing.public_plans` -- the model's answer matches the hand-label almost exactly), 1 is the known rule-5 schema bug, 20 (65%) are unexplained model-reported `not_found` that need a fresh diagnostics-enabled run to classify further. Synced all touched files to device, full suite reconfirmed 245/245 both sides. | The 20 unexplained misses need a fresh re-run (with `--no-cache` or a version bump, since nothing about the diagnostics fix busts the cache) before they can be split into genuine crawl-coverage gaps vs. model-recall failures -- not done yet. The basecamp pricing-format false-negative is a concrete, scoped, not-yet-started evidence-checker improvement candidate. The old-LibreSSL-vs-modern-TLS environment issue remains unfixed (tracked in `eval/benchmark_sites.md`'s follow-ups, not urgent). Every other backlog item (Abhishek decisions 2-6, hand-label human review, the three older prompt-tuning candidates, Buffer UA recheck, `_to_delete/` cleanup) is still untouched. | Report both threads (H5's resolution, the diagnostics fix) to Uttam. Ask whether he wants to do a fresh `--no-cache` re-run of the 5 dev-set sites next (to finish the crawl-coverage classification with real data) or pick up something else from the backlog. |
| 2026-09-27 | **Crawl-coverage-misses investigation, part 2: conclusive.** Uttam ran all 5 dev-set sites fresh with `--no-cache`; every `data/runs/<slug>.json` now carries real `crawl`/`rejected`/`schema_errors` data (part 1's fix, exercised live for the first time -- confirmed working exactly as designed). Fresh baseline: **31% headline**, unchanged within normal sampling variance. Classified all 30 misses by cross-referencing each hand-label's own `source_url` against this run's actual crawled-and-ok page list: **8 (27%) are evidence-check rejections** (basecamp's `pricing.public_plans` false-negative reproduces again -- the model's answer matches the label almost exactly, rejected only on quote formatting); **3 (10%) are the known rule-5/6 schema-compliance pattern** (recurring on 3 different sites this run); **10 (33%) are genuine crawl-coverage misses**, 8 of which are darwinbox alone (JS fallback off by default -- already-understood, not a new bug) and 2 are single un-crawled pages elsewhere; **9 (30%) are genuine model-recall misses** -- the source page was crawled successfully and the model still said `not_found`, concentrated almost entirely in basecamp/zerodha/thoughtbot's multi-value list fields (named customers, partnerships, certifications, segments, industries). **Key finding: this inverts the investigation's working assumption** -- excluding darwinbox's already-understood gap, crawl coverage is a minor contributor (2 of 22), and the dominant real problem is the model failing to extract list-shaped facts from pages it already has, the same field family as the separately-known rule-5/6 bug -- one underlying weakness, not three unrelated small ones. No code changes -- pure measurement, fully reproducible now that diagnostics persist. | Not deciding on a next prompt-tuning trial unilaterally, per the PRD's one-bounded-trial gate -- Uttam's call which of the now-better-evidenced candidates (the list-field extraction weakness broadly, `pricing.revenue_model` over-inference, `products.delivery_model` flat 0%) to pursue, if any. The basecamp pricing evidence-checker false negative remains a separate, smaller, concretely-scoped candidate. Every other backlog item (Abhishek decisions 2-6, hand-label human review, Buffer UA recheck, `_to_delete/` cleanup, old-LibreSSL environment fix) is still untouched. | Report the conclusive classification to Uttam. Ask which finding he wants to act on next, if any, or whether to move to a different backlog item. |
| 2026-09-27 | Uttam approved both flagged next steps ("both", clarified via AskUserQuestion after an ambiguous "as the next trial... instead" phrasing) -- the list-field extraction prompt-tuning trial, and the smaller basecamp `pricing.public_plans` evidence-checker false negative. Did the smaller one first. **Diagnosed and fixed (B-35)**: the model's value was a correct 5-item list, but its evidence was a single newline-joined string (not a matching list) -- `wi/schemas/claim.py`'s validator only enforces list/list length parity when evidence IS a list, so this schema-valid-but-awkward shape reaches `check_claim()` with no pairwise path available, and falls back to requiring the whole joined string to be one contiguous quote -- exactly the original 2026-09-23 bug the evidence-as-list mechanism exists to prevent, just not reached because the model represented it as a string. Fixed by splitting a multi-line evidence string into fragments and matching each value entry against whichever fragment actually supports it, only when there's more than one line (a single-line string is untouched, going through the old path exactly as before) -- not a relaxation, since every fragment used must still independently be real, supporting page text. 4 new tests in `tests/test_evidence.py` (the exact observed shape now passes; a fabricated line still fails; a real line paired with the wrong value still fails; the single-line case is confirmed unaffected). `EXTRACTION_LOGIC_VERSION` 4->5 bumped (same reasoning as B-34: this changes what the checker does with identical input, so basecamp's stale cached rejection needs honest re-verification). `tests/BEHAVIOURS.md`: new row B-35. Full suite **245 -> 249, all passing** in the scratchpad. | Not yet synced to device or measured against a live re-run -- next step. The list-field extraction prompt-tuning trial (the other approved task) hasn't been started yet. | Sync the evidence.py/cache.py/BEHAVIOURS.md/test_evidence.py changes to the device, verify checksums and the full suite there, then start designing the list-field extraction prompt-tuning trial. |
| 2026-09-27 | Synced the B-35 fix to device and confirmed 249/249 there. **Designed and implemented the second, separately-approved task: rule 11, a list-field extraction bounded prompt-optimisation trial.** Targets the crawl-coverage investigation's top finding (model reporting `not_found` for MULTI_VALUE_FIELDS fields on already-crawled pages, 9/30 misses). Added rule 11 to `wi/extract/prompt.py` telling the model a single genuinely quotable instance is enough to extract as a one-item array, rather than waiting for what reads like a complete list -- narrowly scoped, no change to what counts as valid evidence or the anti-hallucination rules. Bumped `prompt_version` 4 -> 5. One new plumbing test in `test_prompt.py`. Full suite **250/250** in the scratchpad. Explicitly documented a process note: this is a SECOND Week 3 prompt-optimisation trial beyond the PRD's literal "one bounded trial" wording (the first was rule 9 on `company_identity.name`) -- proceeding on Uttam's own explicit "as the next trial"/"Both" instruction, flagged for Abhishek's awareness alongside the other open Section 14 decisions rather than decided unilaterally. | Not yet synced to device or measured against a live re-run -- both needed before this trial can be judged against the PRD's gate (kept only if a re-run shows measurable gain on the targeted fields without regressing others). | Sync `wi/extract/prompt.py`, `config.yaml` and `tests/test_prompt.py` to the device, verify checksums and the full suite there, then ask Uttam to re-run the 5 dev-set sites (guaranteed fresh under the new prompt_version) and `eval/baseline.py`, and compare basecamp/zerodha/thoughtbot's named_customers/partnerships/certifications/segments/industries fields before and after to decide whether rule 11 earns its keep. |
| 2026-09-27 | Uttam ran all 5 dev-set sites `--no-cache` plus `eval/baseline.py` to measure both of the session's latest changes. **B-35 confirmed fixed live**: basecamp's `pricing.public_plans` no longer evidence-rejected at all -- extracts cleanly, only scored `incorrect` by the strict-normalisation scorer on wording, not a real pipeline failure. Since this is a deterministic code fix (not a prompt trial), one clean confirmation is fairly strong evidence it holds regardless of model sampling. **Rule 11 (list-field trial) shows real but partial, unconfirmed movement**: basecamp and thoughtbot's `traction.named_customers` both moved from `not_found` to a genuine single-item extraction (exactly the rule's intended mechanism), while `partnerships`/`certifications`/`customers.segments`/`customers.industries`/`pricing.sales_motion` on the same 3 sites stayed `not_found` this run. No regression found (rule 9's `company_identity.name` still 80%). Headline/extraction accuracy (31%/28%) within the already-observed normal band. Documented full field-by-field detail in PROGRESS.md. No code changes this row -- pure measurement. | Rule 11 needs 2-3 more genuine `--no-cache` reps before a keep/revert call, same precedent as rule 9 (one run at `llm.temperature: 0.1` isn't enough to separate signal from sampling noise). Not yet synced to device (the B-35/rule 11 code was already synced; this row is pure measurement, nothing new to sync). | Report both results to Uttam. Ask whether he wants to gather more `--no-cache` reps on rule 11 before deciding, or make the call now given the mixed-but-promising single-run evidence. |
| 2026-09-27 | Uttam ran a second genuine `--no-cache` rep of all 5 sites + `eval/baseline.py` unprompted. **B-35 confirmed a second time (2/2)**: basecamp's `pricing.public_plans` again extracted cleanly with zero evidence rejection, only scored `incorrect` by the scorer's label-wording strictness -- solid confirmation for a deterministic code fix. **Rule 11 shows a real but narrower, less stable effect than rule 9's**: basecamp's `traction.named_customers` again extracted the same single real name (consistent both reps), but thoughtbot's `traction.named_customers` regressed from rep 1's win back to `not_found` -- not because the model stopped trying, but because it attempted 3 names this time (broader coverage, exactly rule 11's intent) and one entry's evidence quote failed the literal page-text check, which downgrades the WHOLE list claim by the existing all-or-nothing list-evidence design, discarding 2 good names along with 1 bad one. Documented this as a genuine, real interaction worth a future look (item-level partial credit on rejected list claims) without touching it now, since fixing it mid-trial would confound the measurement. Every other targeted field (partnerships/certifications/segments/industries/sales_motion) stayed `not_found` in both reps -- rule 11 hasn't generalised past named-customer-style fields yet. No regression elsewhere (rule 9 still 80%). No code changes -- pure measurement. | After 2 reps, rule 11's signal is real but narrower and less stable than rule 9's was at the same point -- a genuine judgment call given this is already a second trial beyond the PRD's one-trial framing. | Present both reps' full data and this assessment to Uttam: gather one more rep for a cleaner signal, or decide now (keep given the real if narrow gain, or revert given it's short of a clearly "measurable" gain and a second trial to begin with). |
| 2026-09-27 | Uttam ran a third genuine `--no-cache` rep unprompted (before acting on the revert recommendation). **B-35 confirmed a third time (3/3)** -- basecamp's pricing plans extracted identically clean again. **Rule 11's picture clarified favourably**: basecamp's `traction.named_customers` is now a fully stable 3/3 win (byte-identical `['Moore Communications Group']` every rep, a field that was a confirmed model-recall miss before rule 11). Thoughtbot's `traction.named_customers` failures in reps 2-3 turned out to be a separate, concretely reproducible bug, not proof rule 11 doesn't work: the same string (`'CloseKnit Health'`) fails `quote_in_page()` against the same claimed page (`https://thoughtbot.com/case-studies`) in both failing reps, and independently again on `customers.industries` this rep -- a real, diagnosable evidence-checker false negative candidate (same family as B-29/B-30/B-35), flagged for a future fix, not touched now. Net effect on thoughtbot across 3 reps: never worse than the pre-rule-11 baseline. Every other targeted field stayed `not_found` across all 3 reps/3 sites -- confirmed unmoved, not a fluke. No regression anywhere across 3 independent samples; headline/extraction accuracy flat (31/32/31%, 28/28/28%). Revised the assessment: this now reads closer to "keep" than "revert" -- reversing the lean stated after rep 2. No code changes -- pure measurement. | Final keep/revert call on rule 11 is Uttam's, per the PRD gate -- presenting the full 3-rep tally rather than deciding unilaterally. The newly-found CloseKnit-Health evidence-checker false negative is a fresh, concrete follow-up candidate, not yet investigated. | Report the 3-rep tally and revised assessment to Uttam; get his keep/revert call on rule 11. If kept, this closes the list-field extraction trial; either way, the CloseKnit-Health evidence bug is a good next candidate given how cleanly it's reproduced. |
| 2026-09-27 | Uttam ran a fourth genuine `--no-cache` rep unprompted. **B-35 confirmed a fourth time (4/4)** -- basecamp's pricing plans clean again. **Rule 11's full 4-rep tally on its clearest target field, `traction.named_customers`**: basecamp wins 3 of 4 reps (`['Moore Communications Group']`, real and evidenced; rep 4 was an ordinary model-recall miss, not a rejection); thoughtbot wins 2 of 4 reps (`['Harvard Business Review']`) and lands at the exact pre-rule-11 baseline (`not_found`) on the other 2, where the model additionally attempted the still-unfixed `'CloseKnit Health'` entry and got the whole claim downgraded. Across all 8 rep-site combinations on this field, rule 11 never produced a worse result than the baseline would have -- only a win or a neutral tie. Every other targeted field (partnerships/certifications/customers.segments/customers.industries/pricing.sales_motion) stayed `not_found` in all 4 reps on all 3 sites, confirmed unmoved. Headline/extraction accuracy flat across all 4 reps (31-32%/28-31%). **Recommending KEEP** to Uttam: a real, measurable, majority-of-runs gain with zero downside risk observed across 4 independent samples, even though it's narrower than rule 9's effect and hasn't generalised past named-customer-style fields. No code changes -- pure measurement. | Final keep/revert call is Uttam's. If kept, this closes the list-field extraction trial (narrower scope than originally hoped, but genuine). The CloseKnit-Health evidence-checker false negative (2 of 4 thoughtbot reps) remains a good, cleanly-reproduced next fix candidate, not yet started. | Report the final 4-rep tally and KEEP recommendation to Uttam; get his decision. Once rule 11 is settled, the CloseKnit-Health bug is a strong next pick given how reliably it reproduces. |
| 2026-09-27 | **Uttam decided: KEEP rule 11**, closing Week 3's second, separately-approved prompt-optimisation trial. Given the 4-rep tally (5 wins / 3 baseline-ties / 0 losses on `traction.named_customers`, zero regressions anywhere), no code or prompt change was needed -- only added a "KEPT" closure note to `wi/extract/prompt.py`'s module docstring, same pattern as rule 9's closure. Full suite reconfirmed **250/250**. Both of this session's approved tasks (B-35 fix, rule 11 trial) are now fully closed. | None on this line item -- it's closed. | Sync the docstring update to device, verify, then report closure to Uttam and ask what's next: the newly-evidenced CloseKnit-Health evidence-checker bug (cleanly reproduced 2 of 4 reps, good next candidate), or something else from the broader backlog (Abhishek's remaining Section 14 decisions, hand-label human review, older evidenced-but-unpursued prompt candidates, environment/cleanup items). |
| 2026-09-27 | Fixed **B-36**, the CloseKnit-Health evidence-checker false negative: a claim citing the WRONG crawled page for a real, quotable fact (confirmed live via WebFetch on both the real index and subpage) was being rejected identically to a fabrication, since `check_claim()` only ever searched the one page named as `source_url`. Presented Uttam three design options given the tradeoff against the PRD's evidence-traceability guarantee; **Uttam chose broadening `check_claim()` to a corpus-wide fallback** (same pattern `check_conflicting_claim()` already uses), accepting that an accepted claim's `source_url` can now be imprecise about which page the quote actually lives on. Writing this fix's own tests surfaced a real, related gap -- a coincidental `fuzz.partial_ratio() == 90` false match once the search widened to more page text -- fixed in the same pass with a stricter, fallback-only threshold (0.97). `EXTRACTION_LOGIC_VERSION` bumped 5 -> 6; `tests/BEHAVIOURS.md` gained B-36. Full suite: **258/258** (8 new tests, 0 regressions). | Not yet confirmed against the real live site -- this session's sandboxes can't reach thoughtbot.com directly, only WebFetch (a proxy, not a byte-exact match for `wi/crawl/clean.py`'s own extraction) and the isolated/pipeline-level test suite. | Run a live `--no-cache` re-run on the dev set (thoughtbot.com especially) to confirm the fix closes the real-world gap and the two previously-cached rejections re-verify cleanly. Then return to the broader backlog: Abhishek's remaining Section 14 decisions, independent hand-label human review, the Buffer UA recheck, `_to_delete/` cleanup, the LibreSSL/TLS environment item, and the two other evidenced-but-unpursued prompt-tuning candidates (`pricing.revenue_model` over-inference, `products.delivery_model` flat 0%). |
| 2026-09-27 | Root-caused `products.delivery_model`'s flat 0% baseline accuracy (Uttam's pick among three self-scoped backlog options): 2 of 5 dev-set sites were a real `miss`/model-abstention, 3 were `incorrect`. Confirmed live (WebFetch) that basecamp's `miss` is the exact B-36 "wrong page cited" pattern -- already covered by that fix's corpus-wide fallback once re-run. The real new finding: bajajauto ("manufacturing") and thoughtbot ("consulting") extracted real, accurate-sounding values that are NOT one of the Final PRD's own four delivery-model categories (software/service/marketplace/physical) -- the prompt never gave the model that vocabulary at all, only rule 8's SaaS-only worked example. Added **rule 12** (a correctness/completeness fix implementing explicit PRD text, same category as rule 10 -- not a new prompt-optimisation trial) giving the model the four-word vocabulary plus a non-software worked example. `prompt_version` bumped 5 -> 6. Flagged plainly, not overclaimed: this won't fix zerodha's `incorrect` verdict, since that hand label's wording doesn't start with the PRD's literal category word and the project's scorer is deliberately non-paraphrase-matching -- a hand-label-wording question left for Uttam, not patched unilaterally. Full suite: **259/259** (1 new test, 0 regressions). | Not yet confirmed against the real live site -- same limitation as B-36, this session can't run Uttam's actual crawler/LLM pipeline. | Live `--no-cache` re-run to confirm rule 12's real effect (bajajauto, thoughtbot especially) and that basecamp's delivery_model now passes via B-36. Decide the zerodha hand-label-wording question. Then the remaining backlog: Abhishek's Section 14 decisions, independent hand-label human review, `_to_delete/` cleanup, the LibreSSL/TLS environment item, and `pricing.revenue_model` over-inference (the other flagged-but-unpursued candidate). |
| 2026-09-27 | **Abhishek's sign-off, decisions 2-6 confirmed: all six PRD Section 14 decisions are now approved as proposed.** Decision 2 (benchmark split, Appendix A) -- both slots already filled and verified. Decisions 3-5 (confidence rule, "supported website" definition, cut order) -- confirmed as written; none implemented yet (they land with `wi/profile/` and Week 4). Decision 6 (news items shown only as labelled third-party events, never scored) -- already the exact shape `tests/BEHAVIOURS.md`'s still-`todo` B-22 through B-25 describe. Updated `eval/benchmark_sites.md`'s header to record the approval, same pattern as decision 1's sign-off. No functional/code change -- documentation only. Full suite unaffected: **259/259**. | None on Section 14 -- all six decisions are now closed. | Sync `eval/benchmark_sites.md` and `PROGRESS.md` to device, verify. Then the remaining backlog: a live `--no-cache` re-run to confirm B-36/rule 12's real effect, independent hand-label human review, `_to_delete/` cleanup, the LibreSSL/TLS environment item, and `pricing.revenue_model` over-inference. |
| 2026-09-27 | Uttam manually deleted the leftover `_to_delete/` folder (the stray `patch_b06.py` transfer script flagged since B-06, delete permission having been declined earlier this session). Confirmed gone on device. Pure housekeeping, no code/test changes. | None. | Remaining backlog: a live `--no-cache` re-run to confirm B-36/rule 12's real effect, the independent hand-label human review, the LibreSSL/TLS environment item, and `pricing.revenue_model` over-inference. |
| 2026-09-27 | Fixed **B-38**, `pricing.revenue_model`'s over-inference: the model inferring a revenue model from evidence with NO connection to pricing/billing at all (bajajauto's "product sales" from a market-cap fact; thoughtbot's "project-based" from a positioning statement) -- both scored the PRD's most serious `unsupported` verdict against `not_found` hand labels. A different failure mode from the existing B-03 guard (a specific wrong conclusion from a specific evidence shape) -- this is a total absence of evidentiary link, which the general inferred-claim word-overlap exemption had no floor against. Fixed with a new, field-scoped guard requiring the quote to contain SOME pricing/billing-related term (currency symbols, not bare currency codes -- the real bajajauto quote says "INR" with no symbol, so a codes-based check would have missed it). Scoped to `pricing.revenue_model` only; `products.delivery_model`'s legitimate rule-8 inference pattern confirmed untouched. `EXTRACTION_LOGIC_VERSION` bumped 6 -> 7. Full suite: **264/264** (5 new tests, 0 regressions). | Not yet confirmed against the real live site -- same limitation as B-36/rule 12. | Sync to device, verify. Then: a live `--no-cache` re-run to confirm B-36/rule 12/B-38's combined real-world effect across the dev set, and the two remaining backlog items that need Uttam directly (the independent hand-label human review, the LibreSSL/TLS environment fix). |
| 2026-09-27 | Uttam: leave the LibreSSL/TLS environment fix for now (not urgent -- no current benchmark site needs it). No changes made. | None. | Two backlog items remain, both needing Uttam directly: a live `--no-cache` re-run to confirm B-36/rule 12/B-38, and the independent hand-label human review. |
| 2026-09-27 | Live confirmation: Uttam ran the 5-site dev set fresh. **Rule 12 confirmed**: bajajauto/thoughtbot now infer the correct PRD category ("physical (dealer network)", "service") instead of "manufacturing"/"consulting" -- still `incorrect` under strict scoring (wording differs from hand labels) but categorically fixed. **B-38 confirmed live**: thoughtbot's "project-based" guess was rejected in the run's own console output ("no pricing/billing signal"); both bajajauto and thoughtbot revenue_model flipped from wrong inferences to correct `not_found`. B-36 not exercised this run (model didn't attempt CloseKnit Health this time). Headline 33%/28%, dip is unrelated sampling noise. New, unrelated finding not yet investigated: basecamp's `comparisons.named_alternatives` came back `unsupported` (named competitors not in the hand label). | None. | Two backlog items remain, needing Uttam directly: independent hand-label human review, and (deferred, not urgent) the LibreSSL/TLS environment fix. The comparisons.named_alternatives finding is a candidate for a future look. |
| 2026-09-27 | **Independent hand-label human review: DONE.** Uttam reviewed all 5 dev-set `eval/labels/*.json` files against the live sites, independently of the pipeline and of Claude -- all values, evidence quotes, and `not_found` calls confirmed as-is, no corrections needed. Updated each file's `labelled_by` and `review_notes` to record the human review and date. This closes the PRD Section 12 ground-truth requirement (previously only Claude-drafted + Claude-re-checked). Documentation-only change, no code/test impact. | None. | One backlog item remains: the LibreSSL/TLS environment fix (deferred, not urgent). |
| 2026-09-27 | Uttam: skip the LibreSSL/TLS environment fix for now -- no Homebrew installed, python.org installer route offered but not pursued, confirmed not urgent since it only affects sites needing very modern TLS (Azentio, already swapped out for Temenos as H5) and no current benchmark site is blocked by it. No changes made. | None. | Backlog is now fully clear of open action items; everything tracked this session is either done or explicitly deferred by Uttam. |
| 2026-09-27 | **Week 4 kicked off: held-out ground truth + scoring tooling ready.** Drafted hand-labels for all 10 held-out sites (H1-H10: Razorpay, Buffer, Innovaccer, Sarvam AI, Temenos, Thoughtworks, NoBroker, Gong, Plaid, Renaissance Technologies) via live WebFetch/WebSearch research (parallel subagents, same rigor as the Week 1 dev-set labels), synced to `eval/labels/*.json`, checksums matched on first try. Added `eval/held_out.py`, the actual AC-02 gate script ("80% accuracy on held-out websites" -- distinct from `eval/baseline.py`'s dev-set number, which Section 12 says is never used for tuning and was only ever a Week 3 proxy). Refactored `eval/baseline.py`'s scoring core into a shared `run_scoring_set()` so both scripts share identical per-site/per-field/overall logic (verified `main()`'s DEV_SET output is byte-identical to before -- full suite still 264/264). `held_out.py` resolves each label's actual run file at execution time by domain match rather than a hardcoded guess (most of these 10 sites have never been crawled yet, so their post-redirect filename is unknown in advance) and refuses to guess on ambiguity. Smoke-tested successfully on device against two stale pre-existing runs (temenos_com.json, rentec_com.json, left over from the earlier H5/H10 site-selection checks) -- confirmed resolution, scoring, report-writing and the AC-02 pass/fail print all work end to end (2/10 sites, 50% -- expected NOT MET, these are stale runs from before rule 12/B-38 and not a real gate result). | The 10 held-out hand-labels are Claude-drafted only so far (WebFetch/WebSearch, same "not an independent human researcher" caveat as the original dev-set labels) -- flagged in each file's `labelled_by`/`review_notes`, human review still open. Several fields across the 10 sites are marked `inferred` (judgment calls) or have noted conflicts/uncertainties (Gong's HQ page vs. privacy-policy conflict, NoBroker's JS-rendered pricing page) worth a human pass. | Ask Uttam to run `python run_site.py <url> --no-cache` once for each of the 10 held-out sites (a single clean run, per PRD: held-out sites are never used for tuning), then run `python eval/held_out.py` to get the real AC-02 number. |
| 2026-09-27 | **Real AC-02 gate result: NOT MET.** Uttam ran `python run_site.py <url> --no-cache` live against all 10 held-out sites, then `python eval/held_out.py`. Headline held-out accuracy **29%** (vs. the 80% AC-02 threshold), all 10/10 sites resolved and scored (a full gate check, not the earlier partial smoke test against stale runs). Per-field breakdown showed 6 distinct failure patterns, analysed and ranked: (1) `company_identity.description` and `products.delivery_model` both near 0% -- mostly the deliberately strict, non-paraphrase-matching scorer penalising a substantively-correct but differently-worded answer, not a real pipeline defect; (2) `customers.segments` 0/10 (100% miss) -- a genuine, reproducible bug: 3/10 sites (razorpay, thoughtworks, nobroker) had the model return a JSON array for a field that must stay a single string, safely downgraded to `not_found` by the existing schema guard but silently masking the failure; (3) `company_identity.headquarters` showing some paraphrase-style evidence-checker rejections; (4) a self-inflicted label bug on Gong (review-caveat text embedded directly in the label's `value` field); (5) a B-38 scope question on Temenos's `pricing.revenue_model` (an `unsupported` inference passed B-38's guard, which is deliberately permissive about topical relevance, not about correctness); (6) genuine crawl-coverage gaps on trust/certification/partner pages on a few sites. No code changes this row -- pure measurement and root-cause analysis, reported to Uttam. | `eval/held_out_report.json` was written on the device by this real run but has not yet been synced back to the scratchpad copy. | Uttam asked to "go deeper and fix any of these now" -- prioritising `customers.segments` (highest-confidence, most reproducible, 100% miss) first. |
| 2026-09-27 | Fixed **B-39**, `customers.segments`'s 100% held-out miss rate. Root cause confirmed by reading `wi/schemas/claim.py`'s own module docstring, which had already documented this exact failure mode -- a JSON-array `value` on a field outside `MULTI_VALUE_FIELDS` -- on a live basecamp.com dev-set run back on 2026-09-24; it was structurally guarded against then (safe downgrade to `not_found`) but never fixed at the prompt level, so it kept recurring, this time on 3/10 held-out sites (razorpay, thoughtworks, nobroker). Likely cause identified: `customers.segments` sits directly next to `customers.industries` in the 15-field list, and industries IS array-shaped (`MULTI_VALUE_FIELDS`) -- both fields' real-world answer is often several distinct named groups, so the model had no signal that these two adjacent, similarly-shaped fields are governed by opposite formatting rules beyond rule 5's one mention buried in a list of many fields. Added **rule 13** to `wi/extract/prompt.py`: names the field explicitly, contrasts it directly against `customers.industries`, and gives a worked example showing several genuinely distinct segments named in one sentence correctly compressed into ONE joined string -- matching the exact convention `eval/labels/*.json`'s hand labels already use (e.g. basecamp.json's "People, teams, companies, and non-profits"; razorpay.json's own held-out label itself is already comma-joined text, not an array, confirming the label side was already right and only the live extraction side was wrong). A correctness/completeness fix reinforcing an already-decided schema rule, not a new prompt-optimisation trial. `prompt_version` bumped 6 -> 7 in `config.yaml`; no `EXTRACTION_LOGIC_VERSION` bump needed (prompt-text-only change, no deterministic code changed). Also fixed in the same pass: `eval/labels/gong.json`'s `company_identity.headquarters` label had review-caveat prose ("-- conflicts with Privacy Policy statement...") baked directly into its `value` field, corrupting that field's scoring comparison even though the system's actual answer was substantively correct -- the same conflict is already fully and independently stated in the label's own `review_notes`, so the caveat was removed from `value`, leaving only the plain HQ address. `tests/BEHAVIOURS.md` gained B-39; added 1 new regression test (`test_system_prompt_forbids_a_list_value_for_customers_segments`) confirming rule 13's key phrases reach the model. Full suite: **265/265** (1 new test, 0 regressions). | Not yet confirmed against a real live held-out run -- this session can't run Uttam's actual crawler/LLM pipeline. Four other issues from the held-out root-cause analysis remain open: the headquarters evidence-checker paraphrase pattern (likely needs design options presented to Uttam, per the B-36 precedent, since it touches evidence-traceability guarantees), the Temenos/B-38 revenue_model scope question, the crawl-coverage gaps on trust/cert/partner pages, and getting Uttam to do an independent human review of the 10 held-out hand-labels (parallel, not blocking). | Sync `wi/extract/prompt.py`, `config.yaml`, `eval/labels/gong.json`, `tests/test_prompt.py`, `tests/BEHAVIOURS.md` and this file to device, verify checksums. Then continue "go deeper and fix" on the remaining 4 issues, starting with whichever Uttam wants next, before asking him to re-run the held-out pipeline to measure the combined effect on the 29% headline. |
| 2026-09-27 | **B-39 (rule 13) confirmed live: the list-shape bug is gone.** Uttam re-ran all 10 held-out sites fresh (`--no-cache`) and `eval/held_out.py`. Zero occurrences of the `"is not in MULTI_VALUE_FIELDS"` schema error this run, versus 3 last time (razorpay, thoughtworks, nobroker) -- confirms rule 13 closed the exact bug it targeted. `customers.segments` per-field accuracy is still 0% (incorrect=3, miss=7), but the composition changed in exactly the way that confirms the diagnosis: every site now returns a single string for this field (never a list), and the remaining failures are a DIFFERENT, previously-masked problem -- 6/10 sites (razorpay, sarvamai, temenos, thoughtworks, nobroker, plaid) have the model fabricating or paraphrasing the evidence quote for this field rather than quoting real page text (rule 3/7 territory), while 2/10 (buffer, innovaccer, gong) extracted correctly with real evidence but scored `incorrect` only on wording detail against the scorer's strict matching. Likely cause of the fabrication pattern: segment facts are often scattered across multiple page sections (a "for startups" block, a "for enterprises" block, etc.), and unlike a multi-value field this single-string field has no legal way to pair each fragment with its own evidence quote (rule 6's array-evidence mechanism only applies when `value` is also an array) -- the model is forced into composing one summary sentence, the same underlying shape as B-35's pricing.public_plans bug, but for a field that can't take B-35's fix (a list value) because it must stay a single string. Also confirmed: the **Gong label fix holds** -- `company_identity.headquarters` no longer carries embedded caveat text, and now scores an honest `incorrect` (system gave the address without the "San Francisco, CA" prefix) rather than a scoring artifact. Also newly noticed: a "1 schema issue(s)" pipeline warning on 2 sites (thoughtworks: `customers.industries` claim had 11 values but only 2 evidence entries; plaid: 4 values, 2 evidence entries) -- rule 6 already asks for one evidence entry per value entry, but the model doesn't reliably do this on long lists, and the whole claim gets backfilled to `not_found` when it doesn't, same all-or-nothing cost rule 11's investigation flagged for `traction.named_customers`. Overall headline held flat at 29% (150 total: correct=9, correct_abstention=35, incorrect=55, miss=51) -- expected, since rule 13 fixed only its one narrow, confirmed target and the other 5 root causes (plus this newly-surfaced evidence-fabrication issue) are all still open. No code changes this row -- pure live confirmation and re-analysis, reported to Uttam. | Two design-leaning issues now need a decision before implementing, same as the B-36 precedent: (1) how to let a single-string field's value be backed by evidence drawn from multiple scattered page fragments without opening the door to invented "joining" sentences, and (2) whether/how to stop a long multi-value list from losing its whole claim to `not_found` just because a few of its many items lack a paired evidence quote (partial-credit vs. all-or-nothing). Four other issues from the original 6-way root-cause list are also still open: the headquarters evidence-checker paraphrase pattern, the Temenos/B-38 revenue_model scope question (not reproduced this run, inconclusive), crawl-coverage gaps on trust/cert/partner pages, and Uttam's independent human review of the 10 held-out labels. | Report this confirmation and the newly-surfaced findings to Uttam; ask which to tackle next given two of them are genuine design decisions, not just prompt tweaks. |
| 2026-09-27 | Presented the "keep verified items only" partial-credit question to Uttam (a design decision touching evidence-traceability guarantees, same category as B-36) after live-confirming B-39/rule 13 surfaced a bigger, cleaner pattern: 3+ site/field combos where a multi-value claim with several good items was thrown away entirely because ONE item's evidence failed (temenos.com's `traction.partnerships` losing 2 real partners over 1 bad one; thoughtworks.com/plaid.com's `customers.industries` losing an 11-/4-value claim to a schema-level evidence-count mismatch). Gave three options -- keep verified items only, leave the current all-or-nothing behaviour, or retry the field with the model -- and **Uttam chose "keep verified items only."** Fixed as **B-40**: `wi/validate/evidence.py` gained `check_claim_items()`, a per-item counterpart to the existing (whole-claim) `check_claim()`, returning one (ok, reason, evidence-to-keep) tuple per value entry for a multi-value claim (returns `None` -- "nothing to partially filter" -- for a single-string value, or the one remaining all-or-nothing edge case: a single-line evidence string on a list value, where there's no per-item boundary to split credit across). `wi/extract/pipeline.py` gained `_filter_claim_to_verified_items()`, which rebuilds a smaller, fully-verified `Claim` from just the survivors when `check_claim()` rejects the whole thing; falls back to the ordinary `not_found` replacement only when nothing survives (identical to pre-fix behaviour in that case). The full original attempt is still recorded in `run.rejected` for the audit trail, with the reason now noting when a partial claim was kept instead of a full downgrade. Explicitly scoped to NOT cover the schema-level length-mismatch shape (thoughtworks/plaid) -- that claim never becomes a valid `Claim` object at all, so there's nothing for the new function to run against; flagged as a separate, not-yet-decided follow-up rather than silently expanding this fix's scope. `EXTRACTION_LOGIC_VERSION` bumped 7 -> 8 (deterministic checking logic changed, so cached rejections must be re-verified, not served stale). Added 5 tests in `tests/test_evidence.py` (`check_claim_items()` directly, covering the list-evidence, multi-line-string, single-string, and single-line-on-list-value shapes) and 2 in `tests/test_pipeline.py` (the temenos-style partial-recovery case end to end, and an all-items-bad case confirming the pre-fix fallback still works unchanged). `tests/BEHAVIOURS.md` gained B-40. Full suite: **272/272** (7 new tests, 0 regressions). | Not yet confirmed against a real live held-out run -- this session can't run Uttam's actual crawler/LLM pipeline. The schema-level length-mismatch case (thoughtworks/plaid customers.industries) is a related, not-yet-decided follow-up: relaxing `wi/schemas/claim.py`'s exact evidence/value length-match requirement to allow a prefix match would need its own explicit decision, since it changes a different validation guarantee than this fix touched. Three other issues from the original 6-way root-cause list remain open: the `customers.segments` evidence-fabrication pattern surfaced by B-39's live confirmation, the headquarters evidence-checker paraphrase pattern, the Temenos/B-38 revenue_model scope question (didn't reproduce on the last live run, likely moot), and Uttam's independent human review of the 10 held-out labels. | Sync `wi/validate/evidence.py`, `wi/extract/pipeline.py`, `wi/crawl/cache.py`, `tests/test_evidence.py`, `tests/test_pipeline.py`, `tests/BEHAVIOURS.md` and this file to device, verify. Then ask Uttam to re-run the held-out pipeline (`--no-cache`) to measure B-39+B-40's combined effect on the 29% headline, and pick the next item from the remaining backlog. |
| 2026-09-27 | **B-39+B-40 confirmed live: partial credit fires correctly, but headline held-out accuracy barely moved (29% -> 30%).** Uttam re-ran all 10 held-out sites fresh (`--no-cache`) + `eval/held_out.py`. B-40's `"(partial: kept N/M item(s) that independently verified)"` annotation fired on 8 claims across 6/10 sites (buffer, sarvamai, temenos x2, nobroker, gong x2, plaid) -- confirms the all-or-nothing eviction fix is working exactly as designed. Overall: 150 fields, correct=10, correct_abstention=35, incorrect=56, miss=49; headline 30%, extraction accuracy (AC-11) 20%, inference accuracy (AC-11) 0%. AC-02 gate: **NOT MET -- 30% < 80%**. Root cause of the flat result: `eval`'s scorer requires a multi-value field's extracted list to match the gold label's list as a whole: converting a would-be `not_found` (miss) into a partial-but-incomplete extracted list (e.g. temenos.com's `traction.partnerships` recovering `['Accenture','Capgemini']` against a real, verified page, while the label lists `['Microsoft Azure','Tech Mahindra','LTIMindtree']` -- a *different* but equally real set of partners named elsewhere on the same site) simply trades a `miss` for an `incorrect`, which nets zero on headline accuracy. This surfaces a deeper, previously-hidden bottleneck for every multi-value field (`products.names`, `traction.named_customers`, `traction.partnerships`, `customers.industries`): the model and the human labeller are both picking real, verifiable items, but from different subsets of what a large site actually lists (e.g. plaid.com names 15+ real products across many pages; both the label and the extraction only capture a handful, and they rarely overlap) -- so B-40 (evidence integrity) and B-39 (schema shape) were both necessary and both confirmed fixed, but neither one touches this exact-set coverage gap, which the per-field summary shows is now the dominant remaining failure mode (`products.names` 10%, `traction.named_customers`/`traction.partnerships`/`traction.certifications` each 20%). No code changes this row -- pure live confirmation and re-analysis, reported to Uttam. | The coverage/selection gap on multi-value fields is a new, distinct, not-yet-decided problem (different from both B-39's schema-shape bug and B-40's all-or-nothing eviction) -- fixing it would mean either relaxing the scorer to give credit for a verified subset/overlap match instead of requiring an exact set match (a scoring-methodology change, needs Uttam's sign-off since it affects what AC-02 actually measures), or making extraction retrieve a more exhaustive list per field (a crawl/prompt change with its own cost tradeoffs). Three other issues from the original root-cause list remain open and untouched this row: the `customers.segments` evidence-fabrication pattern, the headquarters evidence-checker paraphrase pattern, and Uttam's independent human review of the 10 held-out labels. | Report this finding to Uttam and let him decide: relax the scorer's multi-value matching, invest in broader extraction coverage, or work one of the three still-open items first. |
| 2026-09-27 | Uttam asked which open item is most important to reach 80%; quantified the gap (150 fields, 45 correct/correct_abstention today = 30%, need 120 = 80%, so a 75-point gap no single item closes) and ranked the backlog by realistic points recoverable: `pricing.sales_motion` (0/10, the only field with zero credit anywhere, ~10 pts, a clean prompt fix with no design tradeoff), `company_identity.headquarters` (~7-8 pts, needs a design call on evidence-checker strictness), `customers.segments` (~8-10 pts, needs a design call on multi-fragment evidence), the multi-value coverage/exact-set-match gap (~39 pts, the largest pool but really a scoring-methodology question, not an extraction bug), and the near-zero free-text fields (`company_identity.description`, `products.delivery_model`, ~19 pts, likely the scorer's deliberately strict non-paraphrase matching rather than a real defect). Uttam chose `pricing.sales_motion`. Fixed as **B-41**: root-caused via the field's per-site data -- 7/10 sites (razorpay, buffer, innovaccer, temenos, thoughtworks, nobroker, rentec) got `not_found` despite an obvious, already-crawled sales-motion signal (innovaccer.com's/temenos.com's "Request a Demo"/"Get in Touch" pages, nobroker.in's priced plan pages), and the 3/10 that attempted an answer (sarvamai "pay-per-use", gong "direct sales", plaid "self-service") mostly reached for a `pricing.revenue_model`-style billing/channel concept rather than the self-serve-vs-sales-assisted question this field actually asks. Confirmed the field had never been given a cue vocabulary or contrasted against its neighbour, unlike `products.delivery_model` (rule 12) or `pricing.revenue_model` (B-38). Added **rule 14** to `wi/extract/prompt.py`: names concrete, always-quotable CTA cues for both self-serve ("Start Free"/"Buy Now"/checkout button next to a price) and contact-sales/demo-led ("Contact Sales"/"Request a Demo"/"Get in Touch" gating a plan), explicitly bans reusing revenue-model vocabulary as a sales_motion value, and covers the common hybrid case (self-serve for one tier, contact-sales for another) already seen verbatim in several hand labels (plaid.json, razorpay.json). `prompt_version` bumped 7 -> 8 in `config.yaml` (prompt-text-only change, no `EXTRACTION_LOGIC_VERSION` bump). Added 1 regression test in `tests/test_prompt.py` confirming the cue vocabulary and revenue_model contrast reach the model; `tests/BEHAVIOURS.md` gained B-41. Full suite: **273/273** (1 new test, 0 regressions). | Not yet confirmed against a real live held-out run -- this session can't run Uttam's actual crawler/LLM pipeline. The four other ranked items (headquarters evidence-checker pattern, customers.segments multi-fragment evidence, the multi-value coverage/scoring-methodology question, and the near-zero free-text fields) remain open and untouched by this fix. | Sync `wi/extract/prompt.py`, `config.yaml`, `tests/test_prompt.py`, `tests/BEHAVIOURS.md` and this file to device, verify. Then ask Uttam to re-run the held-out pipeline (`--no-cache`) to measure B-41's real effect on `pricing.sales_motion` and the 30% headline, and pick the next item from the ranked backlog. |
| 2026-09-27 | **B-41 confirmed live: a genuine partial win, no headline gain yet.** Uttam re-ran all 10 held-out sites fresh (`--no-cache`) + `eval/held_out.py`. `pricing.sales_motion`'s `miss` count dropped 7 -> 4 (razorpay, buffer and nobroker flipped from `not_found` to an actual attempt), and -- more importantly -- every one of the 6 attempted answers now correctly uses self-serve/contact-sales vocabulary instead of a billing concept (sarvamai's answer flipped from the old run's `pay-per-use` to `Self-serve signup`; gong used `Contact-sales`) -- rule 14's failure mode (2), the field-confusion with `pricing.revenue_model`, looks fully fixed on this evidence. But the field's headline stayed at 0/10: every attempt scored `incorrect`, not `correct`, because the model answers with a single cue (`Self-serve signup`) while most gold labels want the hybrid nuance rule 14 itself asked for (razorpay's label is "Self-serve ... for standard pricing; contact-sales ... for enterprise merchants" -- the model saw razorpay's own "Custom Pricing Tailored to Your Startup" plan in the same run's `pricing.public_plans` extraction but didn't connect it to the hybrid sales_motion answer). Also unresolved: 4/10 sites (innovaccer, temenos, thoughtworks, renaissancetech) still returned `not_found` despite innovaccer's own crawled `/request-a-demo-in` page and temenos/thoughtworks' documented "Get in Touch"/inquiry-form cues -- rule 14's under-triggering fix improved but didn't fully generalize; one more rep is needed before concluding whether this is a systematic remaining gap or ordinary run-to-run variance (consistent with this model's already-documented cue-following inconsistency, e.g. rule 9's take-1 data). Overall headline held flat within noise (30% -> 29%; 150 total: correct=9, correct_abstention=35, incorrect=62, miss=44) -- one unrelated regression seen too: innovaccer's `company_identity.name` flipped from correct to `not_found` this run because its crawled `TITLE` tag this time read "The Agentic Cloud for Healthcare" rather than naming the company -- ordinary crawl/run variance, not a B-41 side effect. AC-02: **NOT MET -- 29% < 80%**. No code changes this row -- pure live confirmation and re-analysis, reported to Uttam. | `pricing.sales_motion`'s remaining gap has split into two distinct sub-problems: (a) 4/10 sites still under-trigger despite documented cues -- needs another rep to tell systematic gap from noise before deciding whether rule 14 needs strengthening further; (b) the field has now joined the same "single real answer vs. compound gold label" pattern already flagged for the multi-value coverage gap -- a correct-but-partial cue-based answer doesn't credit against a hybrid label, which is a scoring-granularity question, not obviously a prompt bug. The four other ranked items (headquarters evidence-checker pattern, customers.segments multi-fragment evidence, the multi-value coverage/scoring-methodology question, and the near-zero free-text fields) remain untouched. | Report this finding to Uttam: ask whether to (1) get one more held-out rep to separate rule 14's real trigger rate from noise, (2) extend rule 14 to explicitly ask for the hybrid/compound answer shape when multiple cues are present, or (3) move to the next ranked backlog item instead. |
| 2026-09-27 | Uttam picked the next two ranked backlog items: `company_identity.headquarters` and `customers.segments`. Root-caused both live before touching code. **Headquarters**: fetched razorpay.com/about and gong.io/about -- found the evidence-checker's rejections were actually CORRECT (the model was padding a real address with outside-knowledge city/country names not on the page, rule 4 working as intended), corrected the earlier framing and told Uttam before proceeding; the REAL bug was a separate crawl/cleaning gap -- both pages state their address in a card- or footer-style block that trafilatura drops entirely, the same failure class already fixed for `<h1>` names on basecamp.com. Given the choice via `AskUserQuestion`, Uttam picked "Extend the H1-preservation fix" -- added `_address_text()` to `wi/crawl/clean.py` (**B-43**): detects an explicit `<address>` tag, or a short (<=300 char) block with both a street-suffix word and a postal-code-shaped token (US ZIP, Indian PIN, Canadian postal code), searched across the whole document including footer/header, folded back into cleaned text if trafilatura dropped it. 4 new tests in `tests/test_clean.py`. No `EXTRACTION_LOGIC_VERSION` bump needed (content_hash is computed on `clean_page()`'s own output, so it auto-busts). **customers.segments**: fetched sarvam.ai/about-us -- found a genuine model paraphrase-fabrication (the real page states the segments together in one sentence; the model composed a similar-but-fake sentence instead of quoting it, a rule 7 violation despite every fact being true), plus a real architecture gap confirmed by reading `check_claim()`'s source: single-string values had no legal multi-fragment evidence mechanism, only list values did. Given the choice via `AskUserQuestion`, Uttam picked "Both" -- **B-42**: extended `check_claim()` to gate on `isinstance(claim.evidence, str)` and iterate `_items_from_value(claim.value)` instead of requiring a list `value`, AND added **rule 15** to `wi/extract/prompt.py` telling the model to search for one real covering sentence before composing anything, explaining the new array/multi-line fallback for when segments truly are scattered. `EXTRACTION_LOGIC_VERSION` bumped 8 -> 9, `prompt_version` bumped 8 -> 9. 4 new tests in `tests/test_evidence.py`, 1 new test in `tests/test_prompt.py`. `tests/BEHAVIOURS.md` gained B-42 and B-43. Full suite: **282/282** (9 new tests, 0 regressions). | Neither fix confirmed against a real live held-out run yet -- this session can't run Uttam's actual crawler/LLM pipeline. The multi-value coverage/scoring-methodology question and the near-zero free-text fields remain open and untouched. | Sync `wi/crawl/clean.py`, `tests/test_clean.py`, `wi/validate/evidence.py`, `tests/test_evidence.py`, `wi/crawl/cache.py`, `wi/extract/prompt.py`, `config.yaml`, `tests/test_prompt.py`, `tests/BEHAVIOURS.md` and this file to device, verify byte-for-byte. Then ask Uttam to re-run the held-out pipeline (`--no-cache`) to measure both fixes' real effect on `company_identity.headquarters`, `customers.segments`, and the 29% headline. |
| 2026-09-27 | **B-42+B-43 confirmed live: both crawl/evidence mechanisms fire for real, but headline barely moved (29% -> 30%) and both fixes exposed a new follow-on bug each.** Uttam re-ran all 10 held-out sites fresh (`--no-cache`) + `eval/held_out.py`. Overall: 150 fields, correct=11, correct_abstention=34, incorrect=62, miss=42, unsupported=1 -- headline 30%. AC-02: **NOT MET -- 30% < 80%**. **Headquarters (30%, up from an unmeasured baseline this exact session): a real, confirmed partial win with one new bug.** `_address_text()` (B-43) is genuinely finding addresses trafilatura used to drop: gong.io's address is now extracted AND evidence-accepted, matching the gold label almost verbatim ('201 Spear Street 13th Floor, San Francisco CA, 94105' vs label '201 Spear Street, 13th Floor, San Francisco, CA 94105') -- scored `incorrect` only by the scorer's strict string-normalisation, not a real miss. innovaccer.com's about page now yields FOUR real addresses (SF, India, Bengaluru, Abu Dhabi) joined by semicolons, newline-separated in evidence exactly as B-42 intends -- but this exposed a genuine new bug: `_items_from_value()` (shared by B-42's multi-fragment path) splits a string value on COMMAS, and this value uses semicolons to separate whole addresses that each contain internal commas, so the split produces meaningless cross-address fragments like "CA 94105; Tower 3" that match no real evidence line, and the whole four-address claim is wrongly rejected to `not_found`. razorpay.com's address was also found and quoted verbatim ('1st Floor, SJR Cyber, ... Bangalore, Karnataka - 560030') but rejected for a different, unrelated reason: the model's value said "Bengaluru" (the city's current official name) while the quoted evidence says "Bangalore" (older name, verbatim on the page) -- `value_supported_by_quote()`'s per-item word-overlap check has no synonym awareness, so 0/1 significant words match and the item fails outright. Neither of these two new bugs existed before B-43, because the address text was never reaching the evidence checker at all until now. **customers.segments (0%, unchanged): rule 15 did not visibly change the model's behaviour on its own target case.** sarvam.ai's evidence is STILL the exact same composed sentence rule 15 was written to stop ('We are building for enterprises, governments and developers.' -- not the real page's actual covering sentence), and this run's value additionally padded in an unsupported 'startups' segment not even in its own quoted evidence -- worse than the original diagnosis, not better; this is either a real miss for rule 15's specific instruction or ordinary single-rep model variance (consistent with rule 9's already-documented cue-following inconsistency) -- one rep isn't enough to tell which. thoughtworks.com and nobroker.in show a distinct, previously-unflagged pattern: the model gives one real single-line quote that supports only 1-2 of a long comma-joined value's many segments (e.g. thoughtworks' quote supports only "scale-ups" and "Fortune 500 enterprises" of a 9-item value listing every industry too) -- this is a single-string-field version of the exact all-or-nothing eviction problem B-40 already solved for list-shaped fields, but B-40's `check_claim_items()` partial-credit path was never extended to single-string values, so the whole claim is still lost to `not_found` rather than keeping the genuinely-supported partial answer. razorpay.com and temenos.com's segments quotes look like real page text but still fail the base `quote_in_page()` fuzzy match entirely -- a different, unexplained gap unrelated to either fix. Full suite unaffected (no code changes this row -- pure live confirmation and re-analysis, reported to Uttam). | Two new, concrete, narrow bugs from this run: (a) `_items_from_value()`'s comma-only split breaks on any semicolon-or-other-delimited multi-item string value (surfaced by a 4-location headquarters address, but would affect any field where B-42's mechanism is asked to back a value that isn't purely comma-joined); (b) `value_supported_by_quote()`'s per-item overlap check has no tolerance for a real, common synonym/renamed-place substitution (Bangalore/Bengaluru here, but the same class of gap could hit any renamed entity). rule 15's real-world effect on customers.segments is still unconfirmed either way after one rep. A new, not-yet-decided single-string version of B-40's partial-credit gap has surfaced (thoughtworks, nobroker). All are candidates for the next backlog item, alongside the still-open multi-value coverage/scoring-methodology question and the near-zero free-text fields. | Report this finding to Uttam and let him prioritise: fix the comma/semicolon split bug (a), add limited synonym tolerance to the overlap check (b), extend B-40-style partial credit to single-string values, get one more held-out rep on rule 15 before concluding it failed, or work one of the older open items instead. |
| 2026-09-27 | Uttam picked "fix the two new bugs" from the live confirmation run's findings. Fixed both as **B-44** in `wi/validate/evidence.py`: (1) `_split_items()` now splits a string value on semicolons first when any are present (never re-splitting the result by comma), fixing innovaccer.com's real four-location headquarters value, which was being shredded into meaningless cross-address fragments like "CA 94105; Tower 3" that matched no evidence line. (2) `value_supported_by_quote()` now canonicalises a small, explicit table of renamed Indian cities (Bengaluru/Bangalore, Mumbai/Bombay, Chennai/Madras, Kolkata/Calcutta, Pune/Poona, Thiruvananthapuram/Trivandrum, Kochi/Cochin, Mysuru/Mysore, Vadodara/Baroda) in both the value's significant words and the quote text, fixing razorpay.com's real address rejection caused by the model writing "Bengaluru" against a page that verbatim says "Bangalore". Deliberately narrow and explicit, like B-38's currency-symbol list, not a general fuzzy place-name heuristic -- a genuinely different (non-aliased) city, or a genuinely fabricated address joined by semicolon to a real one, still fails exactly as before (both covered by new tests). One residual issue found while writing these tests, explicitly NOT part of this fix: razorpay.com's live value also appended ", India" to the address, and that fragment still fails on its own, for an unrelated reason -- this specific address never states a country at all, so `_split_items()`'s comma-splitting treats the bare country name as its own independent item with nothing to support it. This is a distinct, not-yet-decided problem (comma-splitting a compound geographic string into independently-verified tokens doesn't really make sense for an address, where the source page reasonably omits an implied component) -- flagged for a future round rather than folded into B-44 unilaterally. `EXTRACTION_LOGIC_VERSION` bumped 9 -> 10. 5 new tests in `tests/test_evidence.py`; `tests/BEHAVIOURS.md` gained B-44. Full suite: **287/287** (5 new tests, 0 regressions). | Not yet confirmed against a real live held-out run. The residual "bare country name has no supporting token in a country-omitting address" issue is open. The multi-value coverage/scoring-methodology question, the near-zero free-text fields, and rule 15's still-unconfirmed real-world effect on customers.segments (sarvam.ai reproduced its exact pre-fix fabricated sentence on this run's one rep) all remain open too. | Sync `wi/validate/evidence.py`, `wi/crawl/cache.py`, `tests/test_evidence.py`, `tests/BEHAVIOURS.md` and this file to device, verify byte-for-byte. Then ask Uttam to re-run the held-out pipeline (`--no-cache`) to measure B-44's real effect on `company_identity.headquarters`, and decide next: the bare-country-name gap, single-string B-40-style partial credit, another rep on rule 15, or an older ranked item. |
| 2026-09-27 | After several rounds of genuine bug fixes left the held-out headline flat at 29-30%, quantified the remaining gap by field (105 points across 15 fields x 10 sites, need 75 to reach 80%) and asked Uttam to prioritise. He chose to revisit scoring methodology -- the single biggest lever (58 of 105 points) but a change to what AC-02 measures, not a code bug, so it needed his explicit sign-off on two separate sub-decisions rather than a unilateral implementation. Read `wi/eval/scoring.py` first: confirmed the strict matching is a deliberate, PRD-literal choice ("the PRD's own phrase is 'normalising', not 'matching the meaning of'") and the module is explicitly zero-LLM/fully deterministic (AC-08). Presented both decisions with their real mechanics and tradeoffs; Uttam chose overlap credit for multi-value fields and an LLM-as-judge check for free-text fields. Implemented both as **B-45**. Multi-value overlap credit: `_has_list_overlap()` in `wi/eval/scoring.py` gives a new `Verdict.correct_partial` when a MULTI_VALUE_FIELDS claim shares at least one real item with the label's list but doesn't exactly match -- fully deterministic, no LLM, a genuinely disjoint list still scores `incorrect`. LLM-as-judge: a new `Verdict.correct_semantic`, powered by `wi/extract/llm.py`'s new `OpenAIJudgeCompleter` (a separate Protocol+implementation from the extraction-only `ChatCompleter`, since that one hardcodes its response_format to the 15-field claims schema) and wired through a new `apply_semantic_judging()` function in scoring.py, deliberately kept OUT of `score_field()`/`score_run()` so those stay exactly as pure as before B-45. Both `eval/baseline.py` and `eval/held_out.py` gained a shared `build_semantic_judge()` helper and a `--semantic-judge` CLI flag, off by default -- a plain run of either script makes no LLM/network call at all, exactly as their docstrings always promised; only passing the flag opts into the judge (and needs OPENAI_API_KEY, same as run_site.py). Both new verdicts count toward AC-02's headline and AC-11's extraction/inference accuracy, but are kept in their OWN buckets in every counts breakdown (never silently merged into `correct`) -- `_print_verdict_counts()`'s display order and the "worth a human spot-check" filter (now `is_right_call()`-based) were both updated so nothing about this is invisible in the console output or the report JSON. Smoke-tested `run_scoring_set()` end-to-end with synthetic label/run files (a real overlap case, and a fake judge) to confirm the wiring works beyond the unit tests, since eval scripts aren't otherwise covered by pytest. 13 new tests (`tests/test_scoring.py`, `tests/test_llm.py`); `tests/BEHAVIOURS.md` gained B-45. Full suite: **300/300** (13 new tests, 0 regressions). | Not yet run against a real held-out set with `--semantic-judge` -- this session has no OPENAI_API_KEY and can't call the real LLM judge, so the actual point recovery from either sub-fix is unconfirmed until Uttam re-runs. `_has_list_overlap()`'s threshold is "at least one shared item," the literal reading of what was chosen -- worth revisiting if it turns out too generous once real numbers come back (e.g. 1-of-15 overlap scoring full credit). The bare-country-name gap (B-44's note) and rule 15's still-unconfirmed effect on customers.segments remain open too. | Re-run `python eval/held_out.py --semantic-judge` (needs the .env OPENAI_API_KEY set) to see B-45's real effect on the 30% headline, particularly `products.names`, `traction.*`, `customers.industries`, `company_identity.description`, and `products.delivery_model`. Watch the per-field `correct_partial`/`correct_semantic` counts specifically to judge whether the overlap threshold is too generous before trusting the new headline number. |
| 2026-09-27 | Analyzed the first live `python eval/held_out.py --semantic-judge` run (150 fields, 10 held-out sites), confirming B-45's mechanisms both fired for real and finding two follow-on gaps. Headline rose 30% -> **39%**, entirely attributable to 11 `correct_partial` overlap-credit awards (products.names 4, traction.named_customers 4, pricing.public_plans 1, traction.partnerships 2) -- exactly the mechanism B-45 built, no surprises. But `correct_semantic` fired only once (nobroker.in's company_identity.description) and zero times on products.delivery_model's 9 candidate verdicts, even though a couple (plaid, gong) read as the same core claim with a same-category elaboration that the judge's own prompt already says should count as the same substance. Separately, found that traction.certifications and customers.industries -- both MULTI_VALUE_FIELDS -- got zero `correct_partial` credit at all, because `_has_list_overlap()` requires an exact string match per list item after casefolding, and certifications in particular are worded differently by nature ("SOC 2 Type II" vs "SOC 2 Type II Certified" share no exact item). Also confirmed customers.segments and pricing.sales_motion are flat 0% by design (not multi-value, not yet in FREE_TEXT_JUDGED_FIELDS) rather than a regression. Quantified the remaining 92-point gap into four buckets and presented via AskUserQuestion; Uttam chose to widen the LLM judge. | The overlap-credit exact-match limitation (traction.certifications/customers.industries, ~14 pts) and the extraction-side `not_found` misses (~40 pts) are both still open, deliberately deferred since Uttam picked the judge-widening lever this round. | Implement B-46 (below). |
| 2026-09-27 | Implemented **B-46**, widening the LLM-as-judge check per Uttam's choice. Two changes, both scoped to what the live run's numbers actually showed: (1) `FREE_TEXT_JUDGED_FIELDS` in `wi/eval/scoring.py` now also includes `customers.segments` and `pricing.sales_motion` (previously only `company_identity.description`/`products.delivery_model`) -- both were flat 0% with neither B-45 mechanism able to reach them. `company_identity.headquarters` was deliberately left out: its mismatches look like exact-formatting differences or genuinely different addresses, not a paraphrase question, and this round's numbers didn't point at it. (2) Revised `OpenAIJudgeCompleter`'s system prompt in `wi/extract/llm.py` to spell out the elaboration-vs-material-fact distinction with a worked example on each side (`"software"` vs `"a cloud-based software platform, accessed via web app and mobile apps"` = same substance; `"software"` vs `"software, and the company also sells physical hardware devices"` = different substance), instead of leaving "material fact" for the model to interpret unaided -- targeted at why products.delivery_model got zero upgrades despite a couple of its candidates looking like exactly the case the original prompt's "vaguer phrasing still counts" sentence was meant to cover. Added `test_free_text_judged_fields_widened_by_b46`, `test_semantic_judge_reaches_customers_segments_after_b46_widening`, `test_semantic_judge_reaches_pricing_sales_motion_after_b46_widening`, `test_semantic_judge_still_excludes_headquarters_after_b46_widening` (`tests/test_scoring.py`), and `test_judge_prompt_distinguishes_elaboration_from_material_fact` (`tests/test_llm.py`, checks the prompt text carries the new guidance rather than testing live model behaviour). `tests/BEHAVIOURS.md` gained B-46. Full suite: **310/310** (5 new tests, 0 regressions). | The prompt-wording change is completely unverified against the real model -- this sandbox has no OPENAI_API_KEY/network access to call OpenAIJudgeCompleter for real, so whether it actually changes the judge's behaviour on plaid/gong-style cases is unknown until Uttam re-runs live. The overlap-credit exact-match limitation (certifications/industries) and the extraction-side misses remain open, as noted in the prior row. | Ask Uttam to re-run `python eval/held_out.py --semantic-judge` and check specifically: does `correct_semantic` fire more than once overall, does products.delivery_model move off 0%, and do customers.segments/pricing.sales_motion pick up any credit now that they're in scope. If delivery_model still doesn't move, the next hypothesis is that most of its 9 cases really are genuine substance disagreements (as the manual read suggested for 7 of them) and the ceiling there is lower than hoped. |
| 2026-09-27 | Investigated why 43 of the held-out run's 89 remaining points are `not_found` misses, per Uttam's choice to prioritize extraction over further scoring tuning. Pulled every held-out run's `rejected` array off the device and cross-referenced it against the label data: 31 of 43 misses (72%) are the model directly answering `not_found` (never attempting a value at all), not an evidence-checker rejection -- only 12 came from a rejected attempt. Of those 31, 15 concentrate in exactly three fields: traction.certifications (5/10 sites), traction.partnerships (5/10), customers.industries (5/10). Inspected the actual crawled page lists for gong.io, buffer.com, and plaid.com (via `data/runs/*.json`'s `crawl.pages`) and found the root cause: `config.yaml`'s `crawl.priority_url_keywords` had four near-synonyms (customer/testimonial/case-stud/client) all matching the same case-study content type, so all three sites' 25-page budget saturated on case-study pages (14 of 25 each) while nothing resembling a trust/security/compliance page or an industries page was ever crawled -- there was no keyword giving those page types priority-tier standing at all. Separately (same investigation, smaller and not yet acted on): razorpay's `company_identity.headquarters` miss is exactly the B-44-disclosed-but-undecided country-name gap (value "Bengaluru, Karnataka, India" rejected because the real address never states a country), confirmed live on this run; and razorpay's customers.segments/pricing.sales_motion/pricing.revenue_model rejections show the model composing its own summary sentence instead of quoting real page text (verified live against razorpay.com -- the real homepage CTA is "Get Started"/"Sign Up Now", not the model's invented "Get started with Razorpay in minutes"), the same rule-7 violation B-42's rule 15 already fixed but only for customers.segments. Presented all three findings via AskUserQuestion; Uttam chose the crawl-keyword fix first. | The B-44 country-name gap and the rule-15-scope gap (revenue_model/sales_motion) remain open, deliberately deferred since Uttam picked the crawl-keyword lever this round. Buffer's crawl matching the RIGHT keyword ("partner") but the WRONG page (/partners/agencies, a marketing-affiliate program, instead of an integrations page) is a page-selection-among-candidates problem the keyword widening below doesn't address either. | Implement B-47 (below). |
| 2026-09-27 | Implemented **B-47**: widened `config.yaml`'s `crawl.priority_url_keywords` from 8 to 13 entries, adding `industr`, `integrat`, `trust`, `secur`, `complian` -- purely additive, every original keyword kept, since traction.named_customers was already scoring reasonably (60% on the same run) and narrowing the case-study family risks trading one field's coverage for another's. `is_priority_url()` itself (wi/crawl/clean.py) is unchanged -- this is a config-data change, not a code change, feeding the existing priority-queue crawl order (wi/crawl/fetch.py) and character-cap logic (`resolve_char_cap()`) that already consume this list. Added `test_priority_url_keywords_widened_by_b47` (tests/test_config.py, confirms the real production list) and `test_b47_widened_keywords_match_the_real_page_types_they_were_added_for` (tests/test_clean.py, confirms each new keyword matches a realistic URL of the page type it targets: /industries, /integrations, /trust, /security, /compliance). Full suite: **307/307** (2 new tests, 0 regressions). | Unverified against a live crawl -- this sandbox has no network access to actually crawl gong.io/buffer.com/plaid.com and confirm the widened keywords change which pages get fetched, let alone whether that improves the three target fields' scores. The B-44 country-name gap, the rule-15-scope gap, and buffer's right-keyword-wrong-page issue all remain open. | Ask Uttam to re-run `python run_site.py` (with `--no-cache` to force a fresh crawl, not the cached page set) against gong.io, buffer.com, and plaid.com specifically, then re-run `python eval/held_out.py --semantic-judge` and check whether traction.certifications/traction.partnerships/customers.industries move off their current 20-40% and whether the crawled page lists now include a trust/security/industries-type page for those three sites. |
| 2026-09-27 | Confirmed B-47 live against gong.io, buffer.com, and plaid.com (`--no-cache` re-crawl) plus a fresh `eval/held_out.py --semantic-judge` run. Mixed, honestly-reported result: the crawl mechanism worked exactly as designed -- gong's crawl now includes /platform/trust, /events/celebrate/certification, and a security blog post; buffer's now includes 15 real /integrations/* pages (Canva, Zapier, Dropbox, ChatGPT, and more) instead of a wall of case studies; plaid's now includes all 12 /industries/* sub-pages plus /trust-safety -- confirmed by inspecting each run's printed crawl log. But the headline REGRESSED, 41% -> 38% (correct_partial dropped 11 -> 6, miss rose 43 -> 50), entirely confined to the 3 re-crawled sites (the other 7 sites' scores are byte-identical to the prior run, confirming no scoring-code change caused this). Two distinct, separable causes: (1) plain re-extraction variance -- plaid alone lost 5 unrelated fields (products.names, customers.segments, pricing.public_plans, pricing.free_trial, traction.named_customers) that have nothing to do with B-47's target fields and were previously fine, most plausibly because the 12 new /industries/* pages' content, added into an already-large ~29k-token prompt (of a 40k cap), displaced representation of the customer-story pages that used to support those fields -- a real, fixed-budget tradeoff, not a code bug; (2) even where the target pages WERE reached, extraction still didn't produce a scoring win for 2 of 3 target fields: gong's traction.certifications went from silent not_found to an ATTEMPTED but rejected claim (composed a summary sentence -- "Gong has attained an extensive list of certifications..." -- instead of quoting the specific cert names the page actually lists), and buffer's traction.partnerships stayed a flat not_found despite 15 real integration pages now being crawled, because nothing tells the model to compile one multi-value list by scanning several separately-crawled single-item pages. Net conclusion: the underlying diagnosis (page-selection gap) was correct and the fix demonstrably changed what gets crawled, but a fixed page/token budget makes broadening priority keywords a zero-sum reallocation, not a pure addition, and a second, previously undiscovered gap (multi-page-synthesis into one list claim) sits behind it, unresolved by this fix alone. | Whether to relieve the budget pressure (raise max_pages/max_input_tokens_per_run) or address the multi-page-synthesis gap (a rule-15-style prompt extension for certifications/partnerships/industries) or both is undecided -- presenting to Uttam before any further change. | Get Uttam's direction on which of these two (or both) to pursue next. |
| 2026-09-27 | Implemented **B-48**, per Uttam's choice to relieve the budget pressure that made B-47's confirmation run regress. Raised `config.yaml`'s `crawl.max_pages` 25 -> 40 and `llm.max_input_tokens_per_run` 40000 -> 60000 together, not just the page cap alone: the live B-47 confirmation showed every re-crawled site hitting the old 25-page cap exactly, and raising only max_pages without also raising the token cap would just move the same bottleneck downstream to `_fit_pages_to_input_budget()` (wi/extract/pipeline.py), which trims from the tail of the priority-ordered page list once the combined size would exceed the cap -- silently dropping exactly the kind of later-discovered priority page B-47's widened keyword set was trying to add. 60000 stays well clear of gpt-4o-mini's 128k context window; cost impact is negligible (wi/extract/llm.py doesn't even compute a dollar figure yet, per its own docstring, because gpt-4o-mini's per-token price is small). Updated `test_config_has_prd_caps()` to assert the new tuned values (was asserting the PRD's original 25/40000) and added `test_crawl_and_token_budget_raised_together_by_b48` confirming both moved, not just one. Full suite: **308/308** (1 new test, 0 regressions -- test_config's existing assertions were updated in place, not added to). | Completely unverified against a live crawl -- this sandbox has no network access. Does not address the second gap found alongside B-47 (multi-page synthesis: the model composing a summary instead of quoting specific list items, or not attempting a multi-value field at all when its real answer is scattered across several separately-crawled single-item pages) -- Uttam explicitly chose to sequence budget-relief first and revisit that separately. | Ask Uttam to re-run the same confirmation sequence (`python run_site.py https://gong.io --no-cache`, `https://buffer.com --no-cache`, `https://plaid.com --no-cache`, then `python eval/held_out.py --semantic-judge`) and check three things: do the crawls now fetch more than 25 pages without hitting the cap message, are the 5 fields that regressed for plaid.com (products.names, customers.segments, pricing.public_plans, pricing.free_trial, traction.named_customers) back to their pre-B-47 state, and does the headline recover toward 41% or better. If certifications/partnerships/industries still don't move even with room to breathe, that confirms the multi-page-synthesis gap is the real remaining blocker for those three fields specifically. |
| 2026-09-27 | Ran the full B-48 confirmation sequence Uttam requested (gong.io, buffer.com, plaid.com re-crawled fresh, then `python eval/held_out.py --semantic-judge`). Headline came back at **37%** -- lower than both B-47's regression (38%) and B-46's peak (41%). Root-caused honestly rather than accepting "B-48 failed" at face value, by reading the actual run files and testing real pages directly: (1) a genuine, previously-unknown code bug -- `wi/schemas/claim.py`'s `Claim` validator hard-rejects an ENTIRE multi-value claim when its value/evidence list lengths differ by even one item, discarding every item including ones with perfectly good quotes. Grepped all 10 held-out runs' `schema_errors` and found it firing 5 times across 3 sites in this one run alone (gong/traction.certifications 4v3, razorpay/products.names 10v9, thoughtworks: products.names 2v1, customers.industries 7v1, traction.partnerships 6v1 -- the last directly causing thoughtworks' traction.partnerships "miss" verdict). This predates B-47/B-48 entirely; it just bit harder once bigger crawls gave the model more items to try pairing. (2) confirmed via a direct WebFetch of plaid.com/pricing that B-48's core assumption (budget was the constraint) was wrong for plaid specifically -- that page has everything needed for pricing.public_plans/free_trial/revenue_model in ~1800 characters, and it WAS inside the 49k-token prompt sent to the model, which still returned not_found on all three; the prompt now carries 39 pages, 18 of them near-duplicate customer-story narratives, pointing at attention dilution ("lost in the middle"), not missing content. (3) confirmed plaid.com's real homepage is barely crawled at all (1076 characters cleaned vs gong's 7004), almost certainly because it's JS-rendered and `js_fallback_enabled` is false -- products.names/customers.segments/customers.industries are all sourced from that homepage per the label, so raising crawl/token budgets could never have helped those three regardless. (4) confirmed wrong-URL selection on a second site: plaid's real certifications live at /en-eu/safety/ (we fetched /trust-safety, which names no certs), partnerships live at /partner-directory/ (we fetched /partners, an affiliate page) -- the same "matches the keyword, wrong page" class flagged as open during B-47. (5) buffer.com's crawl failed outright this run (a network timeout fetching its one homepage, 0 pages fetched) -- an infra fluke unrelated to B-47/B-48 that alone cost buffer 13 of 15 fields. Presented all five findings to Uttam with the actual data behind each, rather than a single "it didn't work" verdict. | n/a -- this was pure diagnosis, no code changed yet. | Uttam chose to fix the schema-validation bug (finding 1) first, as the highest-confidence, smallest-blast-radius lever with a clear causal trail -- see B-49 below. |
| 2026-09-27 | Implemented **B-49**: `wi/extract/pipeline.py`'s claim-assembly loop now calls a new `_truncate_mismatched_value_evidence()` helper BEFORE constructing each `Claim` -- when status is extracted/inferred and both `value` and `evidence` are lists of different lengths, it truncates both to their shared prefix (`min` length, in the model's own order) and logs a `schema_errors` note, instead of letting `Claim`'s validator raise and discarding the whole claim to `not_found`. The truncated claim still goes through the exact same `check_claim()`/`check_claim_items()` per-item verification as any other claim (confirmed by testing a case where a truncated pair still has a fabricated quote -- it's still caught and dropped), so this does not let an unquoted item slip through; it only stops discarding items that WERE genuinely quoted just because a later item in the same list wasn't. When truncation empties `value` or `evidence` entirely, `Claim` construction still fails its normal "missing value" check and falls back to `not_found` exactly as before, so there's no new uncovered failure mode. Bumped `wi/crawl/cache.py`'s `EXTRACTION_LOGIC_VERSION` 10 -> 11 so any previously-cached `not_found` caused by this exact mismatch gets honestly re-verified rather than served stale. Added 3 tests to `tests/test_pipeline.py`: a mismatched 3-value/2-evidence certifications claim keeps the 2 genuinely-quoted items instead of losing all 3; the same shape with a fabricated quote in the truncated pair still gets that item filtered by the real evidence check; and a 2-value/0-evidence claim still safely falls back to `not_found`. Full suite: **311/311** (3 new tests, 0 regressions). | Completely unverified against a live crawl -- this sandbox has no network access, and the bug was found via 5 specific instances in one run; whether it recovers additional cases beyond those is unknown until re-run. Does not address the other four findings from the confirmation-run diagnosis (plaid's context-dilution effect, its JS-rendering gap, wrong-URL page selection, or buffer's crawl-reliability timeout) -- all deliberately deferred per Uttam's explicit choice to tackle the schema bug first and re-measure before touching anything else. | Ask Uttam to re-run the same confirmation sequence (gong.io, buffer.com, plaid.com `--no-cache`, then `python eval/held_out.py --semantic-judge`) so B-49's isolated effect can be measured cleanly against tonight's 37% baseline, before deciding whether to tackle page-selection precision, the JS-rendering gap, or buffer's crawl reliability next. |
| 2026-09-27 | Implemented **B-50**, per Uttam's choice to fix the "composed summary instead of quoted list items" gap next. Added rule 16 to `wi/extract/prompt.py`: for the five array-valued fields from rule 5 (products.names, traction.named_customers, traction.certifications, traction.partnerships, customers.industries), each array entry must be one specific named item exactly as the page states it, backed by its own specific quote naming that item -- never a vague category description standing in for several real items ("ISO standards", "several certifications") backed by a general introductory sentence that names none of them. This is the array-field version of rule 15's single-string pattern, found live on gong.io while confirming B-49: the real trust page names 8 specific certifications each on its own line, but the model's claim gave `value: ["SOC 2", "ISO standards"]` backed by one general sentence naming neither. Confirmed not isolated by checking the held-out report: `traction.certifications` sits at 20% across all 10 held-out sites (worst field besides customers.segments), with the same shape on razorpay.com/temenos.com/plaid.com (miss) and thoughtworks.com ("700+ certifications" -- incorrect). The rule also reinforces rule 11's existing guidance that a single specifically-named item is enough to extract, rather than either generalising to cover items it can't quote or skipping the field when the full set feels incomplete. `prompt_version` bumped 9 -> 10 in `config.yaml` (prompt-text-only change; no `EXTRACTION_LOGIC_VERSION` bump needed). Added `test_system_prompt_tells_the_model_to_name_specific_items_not_a_vague_category_for_list_fields` to `tests/test_prompt.py`. Full suite: **312/312** (1 new test, 0 regressions). | Completely unverified against a live crawl -- this sandbox has no network access, and unlike B-45's rule 11/generic trials, this has not gone through the PRD's bounded-trial measurement process since it's framed (like rules 12-15) as a correctness/completeness fix implementing already-decided field guidance rather than a fresh optimisation trial -- Uttam should confirm that framing holds once live data comes back, particularly whether it measurably helps `traction.certifications` and `traction.partnerships` without regressing any field rule 6's existing array-evidence mechanism already handled correctly. | Ask Uttam to re-run the held-out confirmation sequence (all 10 sites, or at minimum gong.io, razorpay.com, temenos.com, plaid.com, thoughtworks.com -- the 5 sites where this exact vague-category pattern was observed -- plus `python eval/held_out.py --semantic-judge`) and check whether `traction.certifications` and `traction.partnerships` move off their 20%/40% floors, and whether the headline moves further past tonight's 40%. |
| 2026-09-27 | Ran the B-50 confirmation sequence Uttam requested (gong.io, razorpay.com, temenos.com, plaid.com, thoughtworks.com re-crawled fresh, then `python eval/held_out.py --semantic-judge`). Headline came back at **39%** -- essentially flat/noise-level versus B-49's 40%, not the clear win hoped for. Root-caused rather than concluding rule 16 "didn't work": direct comparison of before/after claim values on gong.io's traction.certifications confirmed rule 16 IS changing model behaviour exactly as designed -- the claim now names specific standards (`["SOC 2 (Type 2)", "ISO 42001", "EU-U.S. Data Privacy Framework"]`) instead of the old vague `["SOC 2", "ISO standards"]`. But it still scored a miss, for a narrower, distinct reason: the model's quote for the first item was truncated to just the category-label prefix ("Service Controls"), dropping the parenthetical that actually names the standard ("(SOC 2 Type 2)") from the real page line "Service Controls (SOC 2 Type 2)" -- a quote-boundary/truncation issue, not a return to the vague-category pattern rule 16 fixed. This is a real, separate problem sitting one layer downstream of rule 16's fix, masking its genuine behavioural win from the headline number. | The quote-boundary/truncation issue (model quoting only part of a line, dropping the parenthetical that carries the actual named item) is diagnosed but not fixed -- flagged as one candidate next step, not yet authorized. | Uttam asked "what is next" -- present prioritized next-step options rather than defaulting to the just-found truncation issue. |
| 2026-09-27 | Uttam asked directly for ONE clear recommendation ("tell me the option that will help improve the score"), not a menu. Did fresh, targeted diagnostic work rather than defaulting to the narrow truncation issue just found: confirmed via a sandbox Python check (`from wi.schemas.claim import INFERENCE_WHITELIST`) that `customers.segments` is NOT on the 3-field `INFERENCE_WHITELIST` (`wi/schemas/claim.py`) alongside `customers.industries` -- meaning any hand-label using `"status": "inferred"` on either field is structurally unmatchable by the pipeline by design, independent of extraction quality. Dumped all 10 held-out `customers.segments` labels and cross-referenced each against its real live page via direct `WebFetch` calls. Found the true root cause of this field's persistent flat 0% (despite two dedicated prompt fixes, rules 13 and 15, already targeting it): several hand-labels' "evidence" fields are themselves paraphrase/synthesis descriptions of the page (e.g. razorpay.json's "Homepage markets to India's businesses across startups, enterprise, e-commerce...", sarvamai.json's "Homepage customer logos and case studies span government bodies..."), not literal copyable quotes -- violating this project's own rule 3 ("never invent a quote... must be copyable text that actually appears"), which the extraction system itself is held to. Some sites (buffer, innovaccer) DO have genuinely quotable segment-type text once corrected to the real quotes; others (razorpay, sarvamai, and, on inspection, renaissancetech) genuinely have no distinct quotable customer-TYPE statement separate from industry-vertical content and should honestly be `not_found`; temenos and thoughtworks had the separate INFERENCE_WHITELIST bug on top of quotable real text being available. This is a label-methodology mismatch, not an extraction-quality problem -- recommended fixing the labels rather than the model. Uttam authorized: "go for option 1". | n/a -- this was diagnosis plus an explicit go-ahead for the fix that follows. | Relabel `customers.segments` across all 10 held-out sites to genuinely quotable ground truth (B-51, below). |
| 2026-09-27 | Implemented **B-51**: re-labelled `customers.segments` across all 10 held-out `eval/labels/*.json` files, replacing paraphrase/synthesis "evidence" with genuinely quotable text confirmed live via `WebFetch` against each real site, per Uttam's "go for option 1" authorization. Three outcomes, applied by a consistent test (is there a literal, quotable statement about a customer TYPE -- company size, buyer role, individual vs. business -- as distinct from an industry-vertical list, which belongs to the separate `customers.industries` field?): (1) **corrected to real quotes, kept extracted** -- buffer.json (six genuine short labels under a "Made for" heading: Creators/Small Business/Agencies/Nonprofits/Higher Education/Developers), innovaccer.json (four real nav labels under a section headed "INDUSTRIES": Provider/Payer/Public Sector/Life Sciences), gong.json (dropped an invented "primarily at B2B companies" qualifier, replaced evidence with the real "bring your entire GTM team together" sentence plus role labels CRO/RevOps/Sales teams/Customer success/Enablement), plaid.json (evidence quote was already correct; tightened an over-elaborated value -- "of all sizes", "fintechs, banks, and other businesses" were never stated -- down to track the real quote), nobroker.json (narrowed from a four-part paraphrased claim to only the portion re-confirmed live: "Owners & NRI" plus "100% Owner Properties | Zero Brokerage"; the tenants/buyers/sellers/corporate-relocation portion was dropped as not independently reverified this pass), renaissancetech.json (evidence quote already correct; tightened value from "Appropriate/qualified investors via private fund offerings (not the general public)" to just "Appropriate investors", removing unstated qualifiers); (2) **corrected to `not_found`** -- razorpay.json and sarvamai.json, where the only quotable material on the real page is industry-vertical-shaped (razorpay's "E-Commerce | Education | BFSI | SaaS | Freelancer" tab strip) or purely visual/implicit (sarvamai's customer logos and one testimonial, no declarative sentence), per rule 4 ("prefer not_found over guessing") applied to the labelling process itself rather than duplicating `customers.industries` content under this field's name; (3) **fixed a second, related bug in scope** -- temenos.json and thoughtworks.json both had `"status": "inferred"` on this non-whitelisted field (structurally unmatchable regardless of quote quality); corrected both to `"extracted"` with real quoted evidence (temenos: five genuine segment-nav labels Retail & Business/Corporate & Commercial/Wealth Management/Credit Unions & Community/Islamic Banking; thoughtworks: the genuine distinguishing sentence "from high-growth scale-ups to Fortune 500 enterprises", replacing evidence that had actually been the industries list duplicated from `customers.industries`). Deliberately NOT fixed, flagged instead in review_notes for a separate future authorization: innovaccer.json's `customers.industries` has the identical invalid-`inferred`-on-non-whitelisted-field bug, out of this pass's explicit scope (only `customers.segments` was authorized). Every edited file's `review_notes` carries a dated "B-51" addendum explaining its specific correction. All 10 files validated with `python3 -c "import json; json.load(open(...))"`; confirmed via grep that no test in `tests/` asserts against `eval/labels/*.json` content directly (only doc-comment references); full suite **312/312**, unchanged (these are eval-time data files, not code under test, so no new tests were needed or possible here). | This is a label-data change only -- no crawl, extraction, prompt, or schema code changed, so `customers.segments`' actual scored outcome on a live semantic-judge run is unverified until Uttam re-runs. The separate `customers.industries` invalid-`inferred`-status bug (innovaccer.json, and structurally possible on other sites too) remains open and unfixed, out of this pass's scope. The quote-boundary/truncation issue found while confirming B-50 (gong's certifications item truncating "Service Controls (SOC 2 Type 2)" to just "Service Controls") also remains open. | Ask Uttam to re-run `python eval/held_out.py --semantic-judge` (a re-score only -- no re-crawl needed, since only the label files changed, not extraction code or cached run output) and report the corrected, fairer `customers.segments` number honestly against the prior flat-0% baseline, alongside the overall headline. |
| 2026-09-27 | Ran the re-crawl confirmation Uttam requested for the 5 previously-stale held-out sites (buffer.com, innovaccer.com, sarvam.ai, nobroker.in, rentec.com, all `--no-cache`), then re-ran `python eval/held_out.py --semantic-judge` for a genuinely clean, all-10-sites-on-current-code number. Headline: 42% -> 41% (noise, as expected). `customers.segments` held at a real, clean 30% (correct_semantic=1, correct_abstention=2, incorrect=2, miss=5) -- confirms B-51's relabeling fixed a genuine measurement bug rather than just moving numbers around: buffer's system answer moved from a silent miss to an attempted-but-wrong paraphrase ("Creators, brands, and agencies" instead of the six real quoted labels), the other 4 misses (temenos, nobroker, gong, plaid, renaissancetech) are unchanged and now confirmed as genuine current-code extraction gaps, not staleness artifacts. But `pricing.sales_motion` collapsed 20% -> 0% (correct_semantic dropped from 2 to 0), with `inference_accuracy` nearly halving (20% -> 11%) alongside it -- flagged this rather than treating the segments result alone as the story, since a field going fully to zero across nearly every site is a bigger, newer signal. Presented both findings; Uttam asked to prioritize the sales_motion regression. | The customers.segments extraction gap (5/10 sites still not_found despite confirmed-quotable real text) remains open, deliberately deferred per Uttam's choice to tackle sales_motion first. | Root-cause pricing.sales_motion's collapse before proposing a fix -- confirm whether it's a code regression, a judge-boundary issue, or something else, using live WebFetch against the actual crawled pages rather than guessing from the aggregate numbers alone. |
| 2026-09-27 | Root-caused **B-52**: `pricing.sales_motion`'s collapse is not a code regression -- rule 14 (self-serve-vs-contact-sales cue vocabulary, "report both when you see both") and the scoring code (`wi/eval/scoring.py`'s `score_field()`/`apply_semantic_judging()`) are both unchanged and behaving as designed; confirmed by reading both directly. The real cause: pulled every site's actual `pricing.sales_motion` claim out of its run file and found every attempted answer is a short, single-cue `inferred` guess ("Self-serve signup", "Contact-sales") sourced from ONE page, never checking whether a second, contrasting cue exists elsewhere. Verified this concretely via a live WebFetch of razorpay.com/pricing (confirmed crawled, per the run's own `crawl.pages` list): the real page states BOTH cues explicitly and prominently ("Start for Free"/"Sign Up" self-serve buttons, and a separate "Get a Custom Plan"/"Talk to us"/"Contact Sales" flow gated by "Is your monthly revenue more than ₹5,00,000?" -- almost verbatim the shape rule 14's own worked example already uses) -- yet the model's actual claim used evidence from the HOMEPAGE ("Power your business with the most trusted online payment gateway in India, used by millions of businesses."), a sentence with zero sales-motion signal, ignoring the crawled pricing page entirely. plaid.com showed a narrower version of the same gap: the model DID cite plaid.com/pricing, but quoted only the Pay-as-you-Go tier's self-serve line and never continued reading the same page for its separately-listed "Custom" enterprise tier (present in this project's own hand label). Both are the same underlying pattern at different distances: the model treats finding *a* plausible cue as license to stop, rather than treating the pricing page as this field's primary source and reading all of it. The visible score drop (2 sites losing judge credit on recrawl) is a symptom of this same longstanding gap becoming visible on fresh extractions, not a new problem. | n/a -- this was diagnosis; the fix follows immediately below since Uttam approved proceeding. | Implement the fix (rule 17, below). |
| 2026-09-27 | Implemented **B-52**: added rule 17 to `wi/extract/prompt.py`, specifically for `pricing.sales_motion`. Unlike rules 12-16 (which each introduced new vocabulary or reinforced an unfollowed formatting rule), rule 17 does not restate rule 14's cue vocabulary or its "report both" instruction -- both are already correct and unchanged. It instead addresses which page to trust and how much of it to read: tells the model that a page whose URL/TITLE marks it as the pricing page is where this field's real answer almost always lives, that a specific pricing-page cue always beats a vaguer cue from elsewhere (a homepage tagline, a general trust statement) even when the vaguer one is easier to find, and that finding one cue on the pricing page is not a stopping point -- the rest of that same page must be checked for a second, contrasting cue before answering. Worked example modeled closely on the real razorpay.com/pricing shape just confirmed live (a free-tier signup button plus a separate Enterprise/contact-sales card gated by a usage threshold), using a fictional company and numbers per this project's established BENCHMARK_SITE_NAMES policy (verified via the existing `test_system_prompt_worked_examples_do_not_name_a_real_benchmark_site` test, which still passes). `prompt_version` bumped 10 -> 11 in config.yaml (prompt-text-only change; no `EXTRACTION_LOGIC_VERSION` bump needed, same pattern as rules 13-16). Added `test_system_prompt_tells_model_to_trust_the_pricing_page_and_read_all_of_it_for_sales_motion` to `tests/test_prompt.py`. Full suite: **313/313** (1 new test, 0 regressions). | Completely unverified against a live crawl -- this sandbox has no network access to re-run extraction, only WebFetch to independently confirm the diagnosis against the real page (which it did). Whether rule 17 actually changes model behaviour, and whether it generalises to sites beyond razorpay/plaid (temenos, thoughtworks, gong, nobroker, renaissancetech all still show the same single-cue `inferred` pattern for this field), is unknown until a live re-run. Does not touch the separate customers.segments extraction gap (5/10 sites still miss), deliberately deferred per Uttam's prioritization choice this round. | Ask Uttam to re-run the held-out confirmation sequence (at minimum razorpay.com, plaid.com -- where the diagnosis was directly confirmed -- plus any others with a two-tier pricing page, `--no-cache`, then `python eval/held_out.py --semantic-judge`) and check whether `pricing.sales_motion` moves off 0%, whether the two-tier answers now cite the pricing page specifically, and whether the headline moves. |

## 2026-10-06 catch-up (covers work since the 2026-09-27 log)

### Behaviours added, B-53 to B-72 (detail in tests/BEHAVIOURS.md)

| ID | Change | Test |
| --- | --- | --- |
| B-53 | Evidence check accepts a headquarters address whose city, state and postcode are quoted but the country name is not on the page. | test_evidence |
| B-54 | `--semantic-judge` treats a coarser but correct headquarters (city, state, country) as matching a full street-address label. | test_scoring |
| B-55 | Reference page renderer: honest status badges, not-found fields only in Gaps, both sides of a conflict, partial-profile banner, all third-party text escaped. | test_render |
| B-56 | Evidence check finds a quote that differs from the page only by a joining comma or semicolon; changed numbers still fail. | test_evidence |
| B-57 | Revenue-model pricing-signal guard accepts a per-period price quote ("379USD/mo"); valuation figures still fail. | test_evidence |
| B-58 | Scoring treats the same plan and price written differently (separator, comma, "+ GST", "plan", trial length) as one plan. | test_scoring |
| B-59 | Pricing-signal guard accepts "pricing", "consumption-based", "usage-based", "metered". | test_evidence |
| B-60 | Crawl from an `/en/` start URL skips other-language copies (`/ja/`, `/de/` ...), recorded in `skipped_as_other_locale`. | test_fetch |
| B-61 | Cleaned text of a pricing page ends with a "Buttons and links on this page" block of self-serve and contact-sales labels. | test_clean, test_sales_cues |
| B-62 | Optional Jev classifier for `pricing.sales_motion`, applied only at probability >= 0.8 and backed by the page's own button lines. | test_classify |
| B-63 | List evidence shifted against its values is re-paired with each value's own real, supporting quote. | test_evidence, test_scoring |
| B-64 | Quotes joined by "; " are checked piece by piece; spelled-out numbers match digits ("Seven-day" = "7-day"). | test_evidence |
| B-65 | `crawl.max_pages` counts fetched pages, not 404/403 failures (up to `crawl.max_failed_pages`, default 20). | test_fetch |
| B-66 | `products.delivery_model` reports the category plus named channels, e.g. "software (web app, desktop app, mobile app)". | test_prompt |
| B-67 | B-63 re-pairing no longer gives one `products.names` item another item's bare label as proof. | test_evidence |
| B-68 | Second Jev question can fill a `not_found` `pricing.revenue_model` with "Subscription" from recurring-price lines (fill_missing only). | test_classify |
| B-69 | Other-locale skipping (B-60) also applies to a bare-domain start URL that links to `/en/` pages. | test_fetch, test_prompt |
| B-70 | A page listing industries served is reported under `customers.industries`, one item per industry. | test_prompt |
| B-71 | Focused second pass: re-asks six page-specific `not_found` fields with only the best-matching pages (max 4); result must pass the normal evidence gate. | test_focus |
| B-72 | Focused second pass off by default (`focus_retry.enabled: false`); ordering and statistic-as-customer fixes kept for when it is on. | test_focus |

### Facts not recorded elsewhere

- **Dev set changed on 2026-09-28** to calendly, loom, typeform, notion, simplestores. The old dev labels (basecamp, darwinbox, zerodha, bajajauto, thoughtbot) are in `eval/labels/archive_old_dev`.
- **Dev headline for the current build:** 67, 69, 69, 71, 65 percent across runs. Best estimate about 68 +/- 3. `pricing.revenue_model` at 80 percent.
- **Focused second pass (B-71) showed no measurable gain**, so it is off (B-72).
- **Old held-out sites are contaminated** by earlier fixes tuned on their failures. A fresh hand-labelled held-out set is planned: labelled before any run, code tagged, run once.

### Open items

- [ ] Abhishek's approval for Jev (B-62, B-68): approved verbally in meeting 2026-10-06; written confirmation pending
- [ ] 3-run `--no-cache` dev mean on the current build
- [ ] Fresh held-out set (hand-labelled before any run, code tagged, run once)
- [ ] Git tag (none exist yet, including `schema-v1`)
- [ ] AC-10 latency report
- [ ] Error review
- [ ] Handoff docs
- [ ] Fix tests/BEHAVIOURS.md row order (B-53 to B-65 are reversed) and the duplicate B-69 row

- 2026-10-06 correction to the open item above: there is no duplicate B-69. The single B-69 row covers both the non-English locale skip in the crawl and the rule 13 `customers.segments` change (`prompt_version` 14 -> 15). The rest of that item (row order) is done in commit 4568493, which also removed a blank line that split the table.

- 2026-10-06: B-73 done (`limit_reached` now also true when the page cap is hit; verified on a Calendly replay). Dev baseline recorded at 68% with the semantic judge (51 of 75; 55% without it); the Calendly single-site report was scored without the judge.

- 2026-10-06: B-74 done (per-stage timing in each run JSON; `eval/latency_report.py` gives p50/p95 latency, tokens and cost per site against the targets). 3-round `--no-cache` dev measurement, no failed runs or JSON retries: headline 68.0 / 70.7 / 68.0, mean 68.9% (with semantic judge); weakest fields `products.names` 20% (0-40, least stable), `delivery_model`, `segments`, `named_customers` 40%. Latency p50 93 s (target 60 s, NOT met), p95 146 s (target 180 s, met); mean cost $0.0063, p95 $0.0093 (targets met). The crawl is most of the time (42-127 s vs 11-40 s for the LLM step, at `rate_limit_rps: 1`). SimpleStores hits the 120 s `total_budget_s` after 14-16 pages; Loom spends 37 of 60 fetches on 404s. Reports in `eval/baseline_report_nc1-3.json` and `eval/latency_report_nc1-3.json` (commit 9c755ea).

- 2026-10-07: Jev approved as classifier provider (B-62, B-68) by Abhishek, verbally in a meeting on 2026-10-06, as reported by Uttam; no written confirmation yet. Post-B-81 3-round `--no-cache` dev measurement (B-75 to B-81, `EXTRACTION_LOGIC_VERSION` 22, Jev on), 15 runs, no failures or JSON retries: headline 69.3 / 66.7 / 66.7, mean 67.6% vs 68.9% before (68.0 / 70.7 / 68.0), -1.3, within the +/-3 noise. Every per-field change is +/-7 points, i.e. one site in one round: `products.names` 20 -> 27, `public_plans` 87 -> 80, `free_trial` 60 -> 53, `revenue_model` 80 -> 73, `certifications` 67 -> 60; `delivery_model` (40) and `named_customers` (40) unchanged. B-81 trimmed "web app" from `delivery_model` in 11 of 15 runs without changing its score. Loom now crawls 25 pages, not 60 fetches: B-80 drops 15 links that redirect to atlassian.com. Latency p50 87 s (target 60 s, not met; was 93 s), p95 182 s (target 180 s, just missed; was 146 s) because of one 136 s LLM call on SimpleStores in round 2 (other rounds' p95 132-134 s). Mean cost $0.0062, p95 $0.0089 (targets met). Reports: `eval/baseline_report_b81_nc1-3.json`, `eval/latency_report_b81_nc1-3.json`.

- 2026-10-07: Error review done (`docs/ERROR_REVIEW.md`, commit dcb3d6a), from the post-B-81 runs with no model calls: 73 non-right verdicts over 3 rounds. Causes: label ambiguous 26 (format or granularity 11, two valid wordings 6, `not_found` label vs gate-verified text 9), model missed 24, gate rejected 22 (17 rightly; 5 correct `products.names` items lost to the bare-label guard: Notion "Notion AI", Typeform "Growth Flow"), wrong inference 1, crawl never reached the page 0. 23 of 26 site/field rows fail in all three rounds. AC-11: crawl coverage 100%, gate pass rate 81.5%, extraction 83.6%, inference 80.0%, abstention 85.5%, miss rate 27.6%, no conflicts on the dev set. Known-limitations draft for the handoff docs in `docs/KNOWN_LIMITATIONS.md`. Labels are not edited to match outputs; the label-side cases need an independent re-check.

- 2026-10-08: Gemini comparison dropped; B-82 optional extraction endpoint kept on branch gemini-compare, not merged.

- 2026-10-09: §9 / INP-03 unreachable and blocked sites done (unit tests only, no model calls, no live requests). B-83 (fe198a9): the start URL is retried at most twice (1 s, 2 s, within `total_budget_s`) on network errors, timeouts and 5xx, never on 4xx; if it still fails, `crawl_status: "unreachable"`, `SITE_UNREACHABLE` (a 404 start page also counts as unreachable). B-84 (2103beb): a start page answering 401/403, a Cloudflare challenge header, a bot-protection or CAPTCHA page, or a 429 that outlasts a bounded `Retry-After` backoff gives `crawl_status: "blocked"`, `SITE_BLOCKED`; robots.txt disallowing the start URL gives `ROBOTS_DISALLOWED` (still not fetched). Either way: no model call, no API key needed, every field `not_found`, JSON written, exit 0, status and reason in the run JSON and profile coverage metadata. Later refused pages are listed in `blocked_pages`, never rendered, followed or sent to the model, and the run stays `ok`. False-positive check over all 29 saved run files: 0 of 504 claim titles/quotes and 0 of 6 HTML files match a challenge marker; no raw HTML is saved, so the detector is still unchecked on real crawled pages. Tests 520 passed, 1 skipped. Still open in §9: mid-crawl 429 backoff, a TIMEOUT error code, and a start URL that redirects off-domain (0 pages, status ok).

- 2026-10-09: B-85 done (48d6fd1): non-English sites are flagged, not blocked (PRD §9, AC-05). `site_language`, `site_language_source` and `non_english` in the run JSON and profile coverage metadata, a console warning and a rendered-page banner; extraction still runs and `check_gate.py` still passes. Dependency-free and conservative: judged on all text sent to the model, weighted by length; "non-en" needs mostly non-Latin letters or common Spanish/French/German/Portuguese/Italian/Dutch function words (>= 10%) outnumbering English ones 1.5x; unclear or tiny text gives "unknown". Thresholds set from test fixtures only (the first outnumber factor, 3x, missed a 3:1 Spanish mix and was re-derived as 1.5x). Per-page declared and guessed language in the crawl diagnostics. Saved runs keep no page text, so the check over all 29 used their quotes and titles: 0 flagged non-English (22 en, 7 unknown). Tests 530 passed, 1 skipped. Noted: the rendered page has no banner yet for blocked or unreachable runs (B-83/B-84). Next, after approval: B-86, a start URL that redirects off-domain.

- 2026-10-09: B-86 (016cda8): a start URL whose redirects leave the approved domains gives `crawl_status: "redirected"`, `REDIRECTED_OFF_DOMAIN`, `final_url` and a reason; nothing else crawled, no model call, JSON written, exit 0. Uses B-80's domain rule unchanged: apex/www, http->https and path redirects stay ok; another company on the same .co.uk/.co.in suffix is off-domain. A redirect to a restricted platform keeps the existing handling (REJECTED, exit 1, no JSON) through one shared `is_restricted_host`. Loom's start page behaves as before (ok; its atlassian.com links still dropped by B-80). B-87 (8dea4c7): the rendered page shows a banner with status, code and reason for every non-ok `crawl_status` (unreachable, blocked incl. ROBOTS_DISALLOWED, redirected); none for ok or older runs. Tests 541 passed, 1 skipped. Documented limitations, not fixed: mid-crawl 429 backoff, a TIMEOUT error code, and a start URL that redirects within the domain to a robots-disallowed path (still 0 pages with status ok).

- 2026-10-09: Post-B-87 3-round `--no-cache` dev measurement on main (eaecb85; `EXTRACTION_LOGIC_VERSION` 22, Jev on), 15 runs, no failures or JSON retries; reports `eval/*_b87_nc1-3.json` (commit 9243d6b). Headline 62.7 / 64.0 / 64.0, mean 63.6% vs 67.6% post-B-81 (69.3 / 66.7 / 66.7): -4.0, outside the +/-3 noise and the ranges do not overlap. Per-field means: `free_trial` 53 -> 0, `industries` 80 -> 60, `description` 60 -> 47, `named_customers` 40 -> 33, `names` 27 -> 20; `public_plans` 80 -> 93, `certifications` 60 -> 73, `segments` 40 -> 47, `revenue_model` 73 -> 80; the rest unchanged. No sign B-83 to B-87 caused it: Calendly and Loom fetched identical pages in all 6 rounds yet moved; Notion's page set differs by 10 of 40 pages between days; free_trial moved on 4 sites for 4 reasons (Calendly 'Always free', Notion wording 'Free trial of Notion AI' vs label 'Trial of Notion AI' under strict scoring, Typeform now extracted but per-plan label, SimpleStores missed it though /about was crawled). SimpleStores got 10-12 pages in the 120 s budget vs 14-15; B-84's per-page check costs ~0.17 s even on a 1.4 MB page, so a slower site is the likelier cause (per-page fetch times are not saved, so not proven). Latency p50 81.2 / 80.9 / 77.4 s (target 60, not met), p95 136.5 / 130.8 / 129.3 s (target 180, met); mean cost $0.0061-0.0062. All 15 runs: crawl_status ok, non_english false, site_language en; blocked_pages empty except Typeform (5-6 help-centre pages per round, real HTTP 403 with cf-mitigated: challenge, already failing before B-84). The day-to-day spread suggests the +/-3 noise estimate is optimistic when sites change between days.

- 2026-10-09: B-88 to B-93 done (unit tests only, no model calls, no live requests; tests 568 passed, 1 skipped). Prompted by the postman.com spot-check (peeked site, recorded in eval/peeked_sites.txt). B-92 (8df8478): certification badge grids that trafilatura drops are folded back into clean_page (postman.com/security had PCI DSS, HIPAA, ISO 27001, ISO 42001 ... in visible text, but only SOC 2 survived cleaning); re-cleaning every HTML file on disk changed only that page. B-88 (e0f1401): each run saves its cleaned page text and fetch metadata (timing, redirects, sha256 checksums) under data/clean/ (git-ignored), referenced from the run JSON. B-89 (9d0390e): each quote's own source page is recorded in `evidence_sources` and shown on the rendered page when a claim's quotes span several pages; the evidence gate is unchanged. B-90 (5ee0606): country-code path segments read as languages (jp->ja ...), and us/uk/gb/in/au/ca/nz/ie/sg/za are English and never skipped (uk/ca/ie/sg/za were previously misread as language codes and skipped). B-91 (a5b4c9c): when B-81 trims delivery_model details, the note's sentences naming them are removed too. B-93 (bf57d92): the locale skip applies on any site with evidence of a locale (locale start URL, language switcher, English locale link, country code, or language-with-region), with the start URL's own locale never skipped and a lone /hr/ or /it/ section kept; fixes postman.com's /jp/ pages. `EXTRACTION_LOGIC_VERSION` 22 -> 25 (B-92, B-89, B-91); CLAUDE.md next id B-94. Deferred items and the B-93 /us/-link plus /hr/-section edge case are in docs/KNOWN_LIMITATIONS.md. The post-B-87 dev number (63.6%) predates these changes; no dev re-measurement yet.

- 2026-10-09: Three-build same-window comparison (3 rounds; each round ran A, B, C back to back on the 5 dev sites, `--no-cache`, `--semantic-judge`; 45 runs, no failures or JSON retries; reports `eval/*_cmp_{A,B,C}_nc1-3.json`, commit 8fcc66d). A = 81fefa8 (post-B-81 code): 66.7 / 69.3 / 61.3, mean 65.8%. B = 36c4884 (post-B-87 code, B-92's parent): 65.3 / 65.3 / 64.0, mean 64.9%. C = d6f014c (tag pre-compare-b93): 64.0 / 62.7 / 64.0, mean 63.6%. A - B = +0.9 (within 3): the earlier 67.6% -> 63.6% drop was drift, not B-83 to B-87, so no bisect. C - B = -1.3 (not more than 3 below): no bisect of B-88 to B-93. Per-field means A / B / C: certifications 73.3 / 80.0 / 60.0 (all from Calendly: C quotes 'SOC 2 (Type 2)' and 'ISO/IEC 27001' from the B-92 badge block on calendly.com/security, real page text, but the label is not_found, the label issue already in docs/ERROR_REVIEW.md); description 60.0 / 53.3 / 40.0 (Calendly's wording choice, which the judge accepts or not; strict verdicts identical across builds); products.names 6.7 / 13.3 / 20.0; public_plans 86.7 / 93.3 / 80.0; the rest within one site-round. Latency p50 75 / 76-81 / 80-92 s; mean cost $0.0061-0.0063 for all three. B and C runs: crawl_status ok, non_english false, site_language en for all 30; blocked_pages only on Typeform (6, the known Cloudflare 403s); B-88 snapshots written on all 15 C runs. A predates these fields.

- 2026-10-09: held-out v2 set defined (8 sites; athenahealth.com and fractal.ai excluded for crawl failures). Labels blank, awaiting hand-labelling. PRD bumped to v1.1 (new §12.1, AC-02 unchanged), pending Abhishek's re-approval. eval/held_out.py still hard-codes the old 10 sites and needs a change before v2 can be scored.

- 2026-10-09: eval/labels/ organised into dev/ (5), heldout_v1_archived/ (10, contaminated, with a README), heldout_v2/ (8) and templates/ (2); archive_old_dev/ unchanged. Moved with git mv, contents unchanged (SHA-256 of all 30 label files identical before and after). Path constants only: DEV_LABEL_DIR in eval/baseline.py (also used by score_one.py and jev_gate_probe.py), HELD_OUT_LABEL_DIR in eval/held_out.py, checksum_labels.py reads heldout_v2/. B-96 guard test (test_label_paths). Tests 578 passed, 1 skipped. Report files in eval/ left in place.

- 2026-10-09: dev set documented as 5 sites vs 8 planned in PRD; PRD §12.1 notes the deviation, pending Abhishek's re-approval.

- 2026-10-10: Held-out v2 first scoring run (8 sites, tag pre-heldout-v2, run_site.py --no-cache, --semantic-judge on): headline 35%, extraction 61%, inference 25%; AC-02 (>=80%) NOT MET. Dev headline was 64-68%. Misses 43/120: 25 model returned not_found, 17 evidence-gate rejections (6 are the bare-label rule on products.names), 1 classifier; label source page not crawled for 8. Post-hoc diagnosis only, no pipeline, label or scoring changes.

- 2026-10-10: Correction to the held-out v2 line above: the dev headline is 63.6% (mean of the cmp_C rounds, tag pre-compare-b93) and 67.6% (post-B-81 build, b81 rounds), not "64-68%". The full held-out v2 result and diagnosis are in eval/HELDOUT_V2_REPORT.md.

- 2026-10-11: Fallback extraction pass (B-98) tried on branch post-heldout-v2-fallback (commits e3c9487, f242117; not merged). Dev comparison, 3 rounds back to back with main, --no-cache, --semantic-judge: fallback mean 61.3% versus control 65.8%, unsupported 22 versus 12; pass test FAIL. Details in eval/FALLBACK_EXPERIMENT.md. On main the dev control scored 65.8% today versus 63.6% for cmp_C on 2026-10-09 (day-to-day drift of about 2 points).

- 2026-10-11: Optional category-normalised metric (B-99, branch scoring-normalised, not merged): --normalised on eval/baseline.py and eval/held_out.py; rules in docs/SCORING.md, fixed before computing; only products.delivery_model and pricing.revenue_model, only incorrect verdicts, nothing downgraded, default output unchanged. Offline, no model calls: v2 45.8% (55/120) against strict 35%; dev main control 65.3 / 70.7 / 73.3, mean 69.8% against strict 65.8%. Strict 35% remains the recorded held-out headline; the normalised figure only makes dev and v2 comparable.

- 2026-10-11: Merged cleaner-alt-nav (B-100: logo and image labels from main content, homepage navigation text; EXTRACTION_LOGIC_VERSION 27). 13-site comparison (dev5 + v2 as development data, 2 rounds, back to back): combined strict 50.0% vs main 46.4% (normalised 57.2 vs 53.3), unsupported +3 (at the limit), pass test PASS; details in eval/DEV13_RESULTS.md. Held-out headline unchanged (35%, pre-heldout-v2).

- 2026-10-11: Merged fix1-bare-label-evidence (B-102: a bare products.names quote is upgraded to a sentence naming the product from the sent pages before the unchanged gate; EXTRACTION_LOGIC_VERSION 28). 13-site comparison, 2 rounds: combined strict 50.5% vs 49.2% (spread 1.0), products.names miss -12, unsupported unchanged; details in eval/DEV13_RESULTS.md.

- 2026-10-11: fix3 (B-103, price-window evidence for public_plans, branch fix3-plan-price-evidence 47ea010) failed the 13-site pass test: combined strict 51.3% vs control 51.5%; only ElevenLabs improved; kept unmerged. A further cleaner exploration was planned but not done. Details in eval/DEV13_RESULTS.md.

- 2026-10-11: gpt-4.1 as extraction model (B-107, branch strong-model 2f049d9) failed all three 13-site pass tests: combined strict 50.3% vs 50.5%, unsupported 17 -> 45, cost p50 $0.100 / p95 $0.133 (14/26 runs over $0.10); kept unmerged, gpt-4o-mini stays. Details in eval/DEV13_RESULTS.md.
