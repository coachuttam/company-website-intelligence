#!/usr/bin/env python3
"""Day 5 baseline entry point: one company URL in, one data/runs/<site>.json out.

Usage:
    python run_site.py https://basecamp.com/

Then check the gate:
    python eval/check_gate.py data/runs/basecamp.json

Add --no-cache to force a genuine fresh LLM call even when a site's page content, prompt,
schema and model all match a previous run's cached result:
    python run_site.py https://basecamp.com/ --no-cache

Added 2026-09-27, needed by the rule-9-take-2 measurement itself: `wi.crawl.cache.RunCache`'s
whole-site content fingerprint means a re-run of the SAME site under an UNCHANGED prompt_version
is a cache hit that returns the literal prior result with 0 model calls (by design -- see that
module's docstring, this is what CST-01 asks for). That is exactly right for normal, cost-saving
re-runs, but it silently defeats the specific purpose of running the same trial prompt several
times in a row to gauge the model's own run-to-run sampling variance (llm.temperature is 0.1, not
0) -- a "third run" that is actually a cache hit isn't a third independent sample at all, it's the
same one being re-reported. `--no-cache` passes `cache=None` through to `extract_claims()`, which
already supports it (skips both the cache read and the cache write for that call).

This is the thin script that wires together everything built so far:
wi.crawl.url (validate) -> wi.crawl.fetch (crawl, robots.txt) ->
wi.crawl.clean (boilerplate removal) -> wi.extract.pipeline (LLM + evidence
gate) -> a JSON file eval/check_gate.py can score.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from wi.config import load_config
from wi.crawl.cache import RunCache
from wi.crawl.clean import clean_page, resolve_char_cap
from wi.crawl.page_labels import homepage_url
from wi.crawl.fetch import crawl_diagnostics, crawl_site
from wi.crawl.js_fallback import render_with_playwright
from wi.crawl.language import declared_language, site_language, text_language
from wi.crawl.snapshot import build_snapshot, write_snapshot
from wi.crawl.url import RESTRICTED_MESSAGE, validate_company_url
from wi.eval.latency import PhaseTimer
from wi.extract.llm import OpenAIChatCompleter
from wi.classify.decisions import apply_classifier
from wi.extract.focus import focus_retry
from wi.extract.pipeline import diagnostics_from_run, extract_claims
from wi.extract.pricing import estimate_cost_usd
from wi.profile.builder import build_profile

ROOT = Path(__file__).resolve().parent


def main(raw_url: str, use_cache: bool = True) -> int:
    # B-74 (AC-10): wall-clock seconds per stage plus the end-to-end total, written to the run
    # JSON's "timing" key; eval/latency_report.py turns those into p50/p95 per website.
    timer = PhaseTimer()
    load_dotenv(ROOT / ".env")
    config = load_config()

    validated = validate_company_url(raw_url)
    if validated.status != "ok":
        print(f"REJECTED ({validated.error_code}): {validated.message}")
        return 1

    print(f"Crawling {validated.url} ...")
    # js_renderer stays None (fallback inert) unless the user opted in via config.yaml AND
    # playwright is actually installed -- render_with_playwright itself degrades to None
    # rather than erroring if it isn't, but there's no reason to even try the import path
    # when the config says the feature is off.
    js_renderer = render_with_playwright if config["crawl"].get("js_fallback_enabled", False) else None
    with timer.phase("crawl"):
        crawl_result = crawl_site(validated.url, validated.approved_domains, config,
                                   js_renderer=js_renderer)
    js_rendered_count = sum(1 for p in crawl_result.pages if p.js_rendered)
    unsupported_count = sum(1 for p in crawl_result.pages if p.error_code == "UNSUPPORTED_CONTENT_TYPE")
    print(f"  fetched {len(crawl_result.pages)} page(s), "
          f"{len(crawl_result.skipped_by_robots)} skipped by robots.txt, "
          f"{len(crawl_result.skipped_as_duplicate)} duplicate(s) dropped"
          + (f", {len(crawl_result.skipped_as_other_locale)} other-language link(s) skipped"
             if crawl_result.skipped_as_other_locale else "")
          + (f", {len(crawl_result.skipped_as_auth)} login/sign-in link(s) skipped"
             if crawl_result.skipped_as_auth else "")
          + (f", {len(crawl_result.dropped_after_redirect)} dropped after a redirect left scope"
             if crawl_result.dropped_after_redirect else "")
          + (f", {unsupported_count} non-HTML (PDF/image/etc.) skipped" if unsupported_count else "")
          + (f", {js_rendered_count} JS-rendered" if js_rendered_count else "")
          + (", budget exhausted" if crawl_result.budget_exhausted else "")
          + (", page cap reached" if crawl_result.page_cap_reached else "")
          + (f", {len(crawl_result.blocked_pages)} page(s) refused us (not used)"
             if crawl_result.blocked_pages else ""))

    # B-86: a start URL that redirects to a restricted platform gets the existing restricted-
    # platform handling, exactly as if that address had been given: rejected, exit 1, no JSON.
    if crawl_result.crawl_error_code == "RESTRICTED_PLATFORM":
        print(f"REJECTED (RESTRICTED_PLATFORM): {RESTRICTED_MESSAGE} "
              f"(the start URL redirects to {crawl_result.final_url})")
        return 1

    ok_pages = [p for p in crawl_result.pages if p.status == "ok" and p.html]
    if not ok_pages:
        print("  no pages fetched successfully -- nothing to extract.")
        # Added 2026-09-26: this branch used to give no clue *why* every fetch failed --
        # a genuine HTTP/network error (403, timeout, DNS) and "the site just has no
        # crawlable content" looked identical from the printed summary alone. Print the
        # actual per-page error so a real failure (bot detection, rate limiting, an
        # outage) isn't mistaken for a code regression, or vice versa.
        for p in crawl_result.pages:
            if p.status != "ok":
                print(f"    - {p.url}: {p.error_code or 'ERROR'} - {p.error}")

    with timer.phase("clean"):
        # B-100: the homepage is the only page given the navigation block; one per-run set keeps each
        # image label on its first page only, in the pipeline's page order (the crawl result's order).
        home = homepage_url(p.url for p in ok_pages)
        seen_labels: set = set()
        clean_pages = [
            clean_page(p.url, p.html, resolve_char_cap(p.url, config), homepage=(p.url == home),
                       seen_labels=seen_labels)
            for p in ok_pages
        ]
    default_cap = config["crawl"]["max_clean_chars"]
    for cp in clean_pages:
        flags = []
        if resolve_char_cap(cp.url, config) != default_cap:
            flags.append("priority page, higher cap")
        if cp.truncated:
            flags.append("truncated")
        flag = f" ({', '.join(flags)})" if flags else ""
        print(f"  cleaned {cp.url}: {len(cp.text)} chars{flag}")

    # B-83/B-84 (PRD Section 9 / INP-03): an unreachable or blocked site gets an honest, empty result -- every
    # field not_found with 0 pages checked, no model call, no API key needed -- and the JSON below
    # is still written with crawl_status and its reason, so the failure is recorded, not lost.
    if crawl_result.crawl_status != "ok":
        print(f"  crawl_status: {crawl_result.crawl_status} ({crawl_result.crawl_error_code}): "
              f"{crawl_result.crawl_status_reason}")
        print("  nothing extracted: every field is not_found, no model call made.")
        retrieved_at = date.today().isoformat()
        run = extract_claims(validated.url, [], config, completer=None, retrieved_at=retrieved_at)
        run.cache_status = "not_run"
        skipped = f"crawl_status {crawl_result.crawl_status}; no model call"
        focus_report = {"enabled": False, "skipped": skipped}
        classifier_report = {"provider": (config.get("classifier") or {}).get("provider", "none"),
                             "enabled": False, "skipped": skipped}
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("OPENAI_API_KEY is not set (check your .env). Cannot call the LLM.")
            return 1

        print(f"Extracting claims with {config['llm']['small_model']} ...")
        # temperature added 2026-09-24 to cut down run-to-run variance -- see wi/extract/llm.py's
        # OpenAIChatCompleter docstring. Falls back to 0.1 if an older config.yaml doesn't have
        # this key yet, so this isn't a breaking change for configs written before today.
        temperature = config.get("llm", {}).get("temperature", 0.1)
        completer = OpenAIChatCompleter(api_key=api_key, temperature=temperature)
        cache_cfg = config.get("cache", {})
        cache = RunCache(cache_dir=ROOT / "data" / "runs" / "cache",
                          max_age_days=cache_cfg.get("max_age_days", 30)) if use_cache else None
        if not use_cache:
            print("  (--no-cache: forcing a fresh LLM call, ignoring and not writing any cached result)")
        # Computed once and passed to both extract_claims() and build_profile() below (Week 3,
        # 2026-09-27) so the ledger's per-claim retrieved_at and the profile's coverage-strip
        # "as of" date can never disagree just because each function called date.today() separately
        # across a midnight boundary -- a real, if rare, way for the two outputs to silently drift.
        retrieved_at = date.today().isoformat()
        with timer.phase("extract"):
            run = extract_claims(validated.url, clean_pages, config, completer, cache=cache,
                                  retrieved_at=retrieved_at)

        # B-71 (2026-10-06): focused second pass for fields the full run left not_found (industries,
        # certifications, named customers, partnerships, named alternatives, headquarters): the same
        # extraction on only the best-matching pages, same evidence gate. Off unless
        # config.yaml's focus_retry.enabled; any failure leaves the first-pass result unchanged.
        with timer.phase("second_pass"):
            focus_report = focus_retry(run, clean_pages, config, completer, retrieved_at, cache=cache)
        if focus_report.get("enabled") and focus_report.get("fields"):
            for e in focus_report["fields"]:
                print(f"  second pass: {e['field']} -> "
                      f"{'ADOPTED' if e.get('adopted') else 'not adopted'}: {e.get('reason')}")
            if focus_report.get("error"):
                print(f"  second pass error (first-pass result kept): {focus_report['error']}")

        # B-62 (2026-10-06): optional Jev decision for pricing.sales_motion, off unless config.yaml's
        # classifier.provider is "jev". Runs after extraction (and after the run cache was written), so
        # extraction results and cache keys are unchanged either way.
        with timer.phase("classifier"):
            classifier_report = apply_classifier(run, clean_pages, config, retrieved_at)
        if classifier_report.get("enabled"):
            for d in classifier_report["decisions"]:
                print(f"  classifier (jev): {d.get('choice', '-')} "
                      f"p={d.get('probability', '-')} -> "
                      f"{'APPLIED' if d.get('applied') else 'not applied'}: {d.get('reason')}")
            if classifier_report.get("error"):
                print(f"  classifier error (extraction result kept): {classifier_report['error']}")

    print(f"  cache: {run.cache_status}")
    if run.dropped_pages:
        print(f"  {len(run.dropped_pages)} page(s) dropped by the input-budget guard "
              f"(llm.max_input_tokens_per_run) before the LLM call, never sent:")
        for url in run.dropped_pages:
            print(f"    - {url}")
    cost_usd = None
    if run.usage:
        print(f"  {run.usage.total_tokens} tokens "
              f"({run.usage.prompt_tokens} prompt + {run.usage.completion_tokens} completion), "
              f"{run.usage.elapsed_s:.1f}s")
        # Added 2026-09-28 (Abhishek asked for a cost-benefit breakdown): estimate_cost_usd()
        # is pure list-price math (wi/extract/pricing.py) against config.yaml's
        # llm.pricing_usd_per_1m_tokens -- see that file's docstring for what this does and
        # does not account for. Compared against targets.cost_mean_usd (Section 13 of the PRD)
        # so the number means something on sight, not just a bare dollar figure.
        pricing = config.get("llm", {}).get("pricing_usd_per_1m_tokens", {})
        cost_usd = estimate_cost_usd(run.usage.prompt_tokens, run.usage.completion_tokens,
                                      config["llm"]["small_model"], pricing)
        target_mean = config.get("targets", {}).get("cost_mean_usd")
        if cost_usd is None:
            print(f"  estimated cost: unknown -- no listed price for "
                  f"{config['llm']['small_model']!r} in config.yaml's llm.pricing_usd_per_1m_tokens")
        elif target_mean:
            vs_target = "under" if cost_usd <= target_mean else "OVER"
            print(f"  estimated cost: ${cost_usd:.4f} ({vs_target} the "
                  f"${target_mean:.2f} targets.cost_mean_usd)")
        else:
            print(f"  estimated cost: ${cost_usd:.4f}")
    if run.schema_errors:
        print(f"  {len(run.schema_errors)} schema issue(s):")
        for e in run.schema_errors:
            print(f"    - {e}")
    if run.rejected:
        print(f"  {len(run.rejected)} claim(s) failed the evidence check and were "
              f"downgraded to not_found:")
        for r in run.rejected:
            evidence_preview = repr(r.attempted_evidence)
            if len(evidence_preview) > 160:
                evidence_preview = evidence_preview[:157] + "...'"
            print(f"    - {r.field}: {r.reason} (claimed: {r.attempted_value!r})")
            print(f"        evidence tried: {evidence_preview}")
            print(f"        source_url claimed: {r.source_url!r}")

    # B-07/OUT-04 (2026-09-27): dated company-reported announcements, entirely separate from
    # the 15-field ledger above -- see wi/schemas/announcement.py.
    if run.announcements:
        print(f"  {len(run.announcements)} dated company-reported announcement(s) found "
              f"(never counted as a core field):")
        for a in run.announcements:
            print(f"    - [{a.category}] {a.text} ({a.date}) -- {a.source_url}")
    if run.rejected_announcements:
        print(f"  {len(run.rejected_announcements)} announcement(s) failed validation/evidence "
              f"and were dropped:")
        for r in run.rejected_announcements:
            print(f"    - {r.reason} (claimed: {r.attempted_text!r})")

    # B-85 (PRD Section 9 "Non-English site: attempt extraction and flag the language", AC-05):
    # judged on every page of text actually sent to the model, weighted by length, plus the start
    # page's <html lang>. Flag only -- it changes nothing that was crawled, sent or extracted.
    dropped = set(run.dropped_pages)
    sent_pages = [cp for cp in clean_pages if cp.url not in dropped]
    html_by_url = {p.url: p.html for p in ok_pages}
    language = site_language([f"{cp.title or ''}\n{cp.text}" for cp in sent_pages],
                             start_html=ok_pages[0].html if ok_pages else None)
    page_languages = [
        {"url": cp.url, "declared_lang": declared_language(html_by_url.get(cp.url)),
         "guessed_lang": text_language(cp.text)["guess"], "sent_to_model": cp.url not in dropped}
        for cp in clean_pages
    ]
    if language["non_english"]:
        print(f"  WARNING: the site's text looks non-English (site_language: "
              f"{language['site_language']}). Extraction ran, but the site is outside the "
              f"English-language supported-website definition (AC-05); expect gaps.")

    # Week 3 (2026-09-27): the canonical profile (OUT-01's second, product-facing output,
    # derived from the already-validated claims -- see wi/profile/builder.py) is written
    # alongside the ledger, not instead of it. `limit_reached` (B-19/CST-03) is true if either
    # hard limit was actually hit: the crawl's time budget (crawl_result.budget_exhausted), its
    # page cap (crawl_result.page_cap_reached, B-73) or the LLM input-token budget guard
    # (run.dropped_pages, already computed above).
    profile_doc = build_profile(
        run, pages_scanned=len(clean_pages), retrieved_at=retrieved_at,
        crawl_budget_exhausted=crawl_result.budget_exhausted or crawl_result.page_cap_reached,
        crawl_status=crawl_result.crawl_status, crawl_error_code=crawl_result.crawl_error_code,
        crawl_status_reason=crawl_result.crawl_status_reason,
        site_language=language["site_language"],
        site_language_source=language["site_language_source"],
        non_english=language["non_english"],
    )
    if profile_doc["limit_reached"]:
        print("  limit_reached: true (a hard crawl or token-budget cap was hit this run)")

    timing = timer.as_dict()
    print(f"  time: {timing['total_s']:.1f}s total ("
          + ", ".join(f"{k[:-2]} {v:.1f}s" for k, v in timing.items() if k != "total_s") + ")")

    out_dir = ROOT / "data" / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = (validated.approved_domains[0] if validated.approved_domains else "site").replace(".", "_")

    # B-88: a record of what was fetched and what the model was shown (cleaned text, fetch timing,
    # checksums), under data/clean/ (git-ignored). Records only; nothing above depends on it.
    snapshot_ref = write_snapshot(ROOT, slug, build_snapshot(
        validated.url, retrieved_at, crawl_result.pages, clean_pages, [cp.url for cp in sent_pages]))
    print(f"  snapshot: {snapshot_ref['path']} ({snapshot_ref['pages']} page(s))")
    out_path = out_dir / f"{slug}.json"
    out_path.write_text(
        json.dumps({
            # "claims" stays a top-level key for backward compatibility -- eval/check_gate.py
            # and every existing run.json consumer reads data["claims"] directly. The full
            # ledger is also inside profile_doc["claims"] (identical content); duplicating it
            # here avoids a breaking change to the gate script for a Week 3 addition.
            "claims": [c.model_dump(mode="json") for c in run.claims],
            "announcements": profile_doc["announcements"],  # B-07/OUT-04, same duplication
                                                              # reasoning as "claims" above
            "cache_status": run.cache_status,
            "dropped_pages": run.dropped_pages,
            "profile": profile_doc["profile"],
            "schema_version": profile_doc["schema_version"],
            "limit_reached": profile_doc["limit_reached"],
            # B-83/B-84/B-86 (PRD Section 9 / INP-03): "ok"; "unreachable" (SITE_UNREACHABLE);
            # "blocked" (SITE_BLOCKED, or ROBOTS_DISALLOWED for a disallowed start URL); or
            # "redirected" (REDIRECTED_OFF_DOMAIN, with final_url).
            "crawl_status": profile_doc["crawl_status"],
            "crawl_error_code": profile_doc["crawl_error_code"],
            "crawl_status_reason": profile_doc["crawl_status_reason"],
            "final_url": crawl_result.final_url,   # B-86: set when crawl_status is "redirected"
            # B-85: "en", "unknown", a declared non-English code such as "es", or "non-en".
            "site_language": profile_doc["site_language"],
            "site_language_source": profile_doc["site_language_source"],
            "non_english": profile_doc["non_english"],
            # Added 2026-09-27 (crawl-coverage-misses investigation, see PROGRESS.md): this was
            # all already computed above and already printed to the console once, but never
            # written here -- meaning it was lost the moment the terminal scrolled past it. Purely
            # additive keys, safe for every existing consumer (eval/check_gate.py and
            # eval/baseline.py only ever read data["claims"]).
            "crawl": {**crawl_diagnostics(crawl_result),
                      # B-85: diagnostics only -- declared and guessed language per cleaned page,
                      # and the measurements behind the site-level flag.
                      "page_languages": page_languages,
                      "language_measured": {**language["measured"],
                                            "declared_lang": language["declared_lang"]}},
            "focus_retry": focus_report,       # B-71; {"enabled": false} when off
            "classifier": classifier_report,   # B-62; {"provider": "none", ...} when off
            **diagnostics_from_run(run),
            # Added 2026-09-28 alongside the cost estimate above: usage was already computed
            # and already printed once to the console, but (like crawl/rejected/schema_errors
            # before it, see the "crawl" key's own comment above) never written here -- so it
            # was lost the moment the terminal scrolled past it. None when the LLM was never
            # called (0 pages fetched) or the run came from cache.
            "usage": {
                "prompt_tokens": run.usage.prompt_tokens,
                "completion_tokens": run.usage.completion_tokens,
                "total_tokens": run.usage.total_tokens,
                "elapsed_s": run.usage.elapsed_s,
                "estimated_cost_usd": cost_usd,
            } if run.usage else None,
            "timing": timing,                   # B-74 (AC-10), see the PhaseTimer above
            "clean_snapshot": snapshot_ref,     # B-88: path and sha256 of the page-text snapshot
        }, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {out_path}")
    print(f"Next: python eval/check_gate.py {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    no_cache = "--no-cache" in args
    positional = [a for a in args if a != "--no-cache"]
    if len(positional) != 1:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(positional[0], use_cache=not no_cache))
