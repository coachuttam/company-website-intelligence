"""Tests for wi.crawl.cache and its wiring into wi.extract.pipeline.extract_claims
(CST-01 / B-17 / B-21). Fully offline: a temp directory stands in for data/runs/cache.
"""
from __future__ import annotations

import json
import time

import wi.crawl.cache as cache_module
from wi.crawl.cache import RunCache, run_fingerprint
from wi.crawl.clean import CleanPage
from wi.extract.pipeline import extract_claims
from wi.extract.fields import FIELDS

from tests.test_pipeline import CONFIG, FakeCompleter, _all_not_found_claims

PAGE = CleanPage(
    url="https://example.com/",
    title="Example",
    text="Example Co is project management without all the nonsense. "
         "Start a 30-day free trial today.",
)


def test_run_fingerprint_is_stable_for_identical_input():
    assert run_fingerprint("https://example.com/", [PAGE], CONFIG) == \
        run_fingerprint("https://example.com/", [PAGE], CONFIG)


def test_run_fingerprint_changes_when_page_text_changes():
    changed = CleanPage(url=PAGE.url, title=PAGE.title, text=PAGE.text + " New sentence.")
    assert run_fingerprint("https://example.com/", [PAGE], CONFIG) != \
        run_fingerprint("https://example.com/", [changed], CONFIG)


def test_run_fingerprint_changes_when_model_changes():
    other_config = {"llm": {"small_model": "a-different-model"}}
    assert run_fingerprint("https://example.com/", [PAGE], CONFIG) != \
        run_fingerprint("https://example.com/", [PAGE], other_config)


def test_run_fingerprint_changes_when_extraction_logic_version_changes(monkeypatch):
    # The real bug this guards against: a fix to pipeline.py's claim assembly or evidence.py's
    # quote/value checks changes what the checker does with identical input, but nothing about
    # that input (content, prompt, schema, model) changes -- so without folding this version in,
    # a previously-cached site would keep serving its pre-fix result forever (see this module's
    # docstring on EXTRACTION_LOGIC_VERSION, found via two dev-set cache entries missing a field
    # added by a later fix).
    before = run_fingerprint("https://example.com/", [PAGE], CONFIG)
    monkeypatch.setattr(cache_module, "EXTRACTION_LOGIC_VERSION",
                         cache_module.EXTRACTION_LOGIC_VERSION + 1)
    after = run_fingerprint("https://example.com/", [PAGE], CONFIG)
    assert before != after


def test_bumping_extraction_logic_version_makes_a_previously_cached_entry_unreachable(tmp_path, monkeypatch):
    cache = RunCache(cache_dir=tmp_path)
    old_fingerprint = run_fingerprint("https://example.com/", [PAGE], CONFIG)
    cache.set(old_fingerprint, {"claims": [], "rejected": [], "schema_errors": []})
    assert cache.get(old_fingerprint) is not None  # sanity check before the bump

    monkeypatch.setattr(cache_module, "EXTRACTION_LOGIC_VERSION",
                         cache_module.EXTRACTION_LOGIC_VERSION + 1)
    new_fingerprint = run_fingerprint("https://example.com/", [PAGE], CONFIG)

    assert new_fingerprint != old_fingerprint
    assert cache.get(new_fingerprint) is None  # a fresh extraction is forced, not a stale hit


def test_run_fingerprint_ignores_page_order():
    page2 = CleanPage(url="https://example.com/about", title="About", text="About us.")
    assert run_fingerprint("https://example.com/", [PAGE, page2], CONFIG) == \
        run_fingerprint("https://example.com/", [page2, PAGE], CONFIG)


def test_cache_get_is_none_for_a_never_written_fingerprint(tmp_path):
    cache = RunCache(cache_dir=tmp_path)
    assert cache.get("nope") is None


def test_cache_round_trips_a_payload(tmp_path):
    cache = RunCache(cache_dir=tmp_path)
    cache.set("abc123", {"claims": [], "rejected": [], "schema_errors": []})
    assert cache.get("abc123") == {"claims": [], "rejected": [], "schema_errors": []}


def test_cache_treats_an_expired_file_as_a_miss(tmp_path):
    cache = RunCache(cache_dir=tmp_path, max_age_days=30)
    cache.set("old", {"claims": []})
    path = tmp_path / "old.json"
    old_time = time.time() - 31 * 86400  # 31 days ago, past the 30-day max_age
    import os
    os.utime(path, (old_time, old_time))
    assert cache.get("old") is None


def test_cache_treats_a_corrupt_file_as_a_miss_not_a_crash(tmp_path):
    cache = RunCache(cache_dir=tmp_path)
    path = tmp_path / "broken.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json", encoding="utf-8")
    assert cache.get("broken") is None


# --- Integration with extract_claims (the actual B-17 behaviour) ------------------------

def test_unchanged_rerun_makes_zero_model_calls(tmp_path):
    claims = _all_not_found_claims()
    completer = FakeCompleter({"claims": claims})
    cache = RunCache(cache_dir=tmp_path)

    first = extract_claims("https://example.com/", [PAGE], CONFIG, completer,
                            retrieved_at="2026-09-22", cache=cache)
    assert completer.calls == 1
    assert first.cache_status == "miss"

    second = extract_claims("https://example.com/", [PAGE], CONFIG, completer,
                             retrieved_at="2026-09-22", cache=cache)
    assert completer.calls == 1  # NOT 2 -- the second run must not call the model at all
    assert second.cache_status == "hit"
    assert second.usage.total_tokens == 0


def test_three_runs_on_unchanged_content_are_structurally_identical(tmp_path):
    # B-21: same fields, statuses and claim count across 3 runs.
    claims = _all_not_found_claims()
    claims[0] = {**claims[0], "field": "company_identity.name", "status": "extracted",
                 "value": "Example Co", "source_url": "https://example.com/",
                 "evidence": "Example Co is project management without all the nonsense.",
                 "confidence": 0.9}
    completer = FakeCompleter({"claims": claims})
    cache = RunCache(cache_dir=tmp_path)

    runs = [
        extract_claims("https://example.com/", [PAGE], CONFIG, completer,
                        retrieved_at="2026-09-22", cache=cache)
        for _ in range(3)
    ]

    assert completer.calls == 1  # only the first run ever touches the model
    shapes = [[(c.field, c.status, c.value) for c in r.claims] for r in runs]
    assert shapes[0] == shapes[1] == shapes[2]


def test_changed_page_content_busts_the_cache(tmp_path):
    claims = _all_not_found_claims()
    completer = FakeCompleter({"claims": claims})
    cache = RunCache(cache_dir=tmp_path)

    extract_claims("https://example.com/", [PAGE], CONFIG, completer,
                    retrieved_at="2026-09-22", cache=cache)
    assert completer.calls == 1

    changed_page = CleanPage(url=PAGE.url, title=PAGE.title, text=PAGE.text + " Now with more text.")
    extract_claims("https://example.com/", [changed_page], CONFIG, completer,
                    retrieved_at="2026-09-22", cache=cache)
    assert completer.calls == 2  # content changed -- must re-extract, not serve the stale cache


def test_no_cache_argument_behaves_exactly_as_before(tmp_path):
    # Backward compatibility: omitting `cache` must reproduce the old always-call behaviour.
    claims = _all_not_found_claims()
    completer = FakeCompleter({"claims": claims})

    extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")
    extract_claims("https://example.com/", [PAGE], CONFIG, completer, retrieved_at="2026-09-22")
    assert completer.calls == 2
