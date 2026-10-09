# Company Website Intelligence Prototype

Given one public company website URL, this produces a structured, evidence-backed profile of what the company states on its own website: 15 fixed fields, each with a source URL, an exact quote and a retrieval date, or an honest `not_found`.
A company website is a **self-reported source**. Claims are never presented as independently verified.

Spec: `docs/PRD.MD`. Behaviour log: `tests/BEHAVIOURS.md`. Progress log: `PROGRESS.md`.

## Status at a glance

- **Accuracy is below target.** The dev-set headline is **67.6%** (mean of 3 `--no-cache` rounds scored with the semantic judge: 69.3, 66.7, 66.7; `eval/baseline_report_b81_nc1-3.json`). The previous build measured 68.9% (`eval/baseline_report_nc1-3.json`). Run-to-run noise is about ±3 points. The PRD target (AC-02) is **80% on held-out sites**. It is **not met on the dev set**, and the **held-out result is pending** (see "Evaluation limits").
- **Latency misses the p50 target** in the post-B-81 rounds: p50 70 to 88 s per round against 60 s; p95 132 to 134 s in two rounds and 231 s in the third (one slow model call), against 180 s. Mean variable cost was $0.0061 to $0.0062 per site against $0.10 (`eval/latency_report_b81_nc1-3.json`).
- **Jev** (TypeSafe, the optional `pricing.sales_motion` / `pricing.revenue_model` classifier) is on in `config.yaml`. It was approved verbally by Abhishek in a meeting on 2026-10-06; written confirmation is pending.
- A Gemini extraction comparison was prepared and then dropped. Its code (B-82, an optional extraction endpoint) sits **unmerged on the `gemini-compare` branch**; `main` uses `gpt-4o-mini`.
- Drafts: `docs/ERROR_REVIEW.md` (every dev-set error and its cause) and `docs/KNOWN_LIMITATIONS.md`. Both are marked **DRAFT** until the held-out run is done.

## Setup

Checked on Python 3.9.6 (macOS), on a fresh clone.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt -r requirements-llm.txt
cp .env.example .env                         # then fill in the keys you have (names below)
```

`requirements-dev.txt` includes `requirements.txt`. `requirements-llm.txt` installs the `openai` client; it is needed for real runs **and for the tests** (9 LLM-client tests fail without it). Playwright, used only by the optional JS-page fallback, is not installed by these files (see `requirements-optional.txt`); without it the fallback is skipped.

### Environment variables (`.env`)

Only the names are listed here. Never commit `.env` or print its values.

| Variable | Used for | Without it |
| --- | --- | --- |
| `OPENAI_API_KEY` | Extraction (`run_site.py`) and the optional semantic judge (`--semantic-judge`) | A run whose site was crawled normally stops before extraction with exit code 1 and writes no JSON. Runs whose site is unreachable, blocked or redirected need no key (see below). Scoring falls back to no judge. |
| `JEV_API_KEY` | The optional Jev classifier | Jev skips itself; the extraction result is used unchanged, and the run JSON's `classifier` section says why. |

`.env.example` also lists `ANTHROPIC_API_KEY` and `GOOGLE_API_KEY`; nothing on `main` reads them.

## Run the tests

```bash
python -m pytest -q
```

The tests mock all crawl and model calls, and need no API key. On a fresh clone 2 tests are skipped: one needs Python 3.10+, and one needs a saved run in `data/runs/` (which git ignores).

## Run one site (needs `OPENAI_API_KEY` and network; not checked here)

```bash
python run_site.py https://www.example.com/              # uses the run cache when nothing changed
python run_site.py https://www.example.com/ --no-cache   # a fresh model call; use this for any measurement
```

This crawls the site (same domain only, robots.txt respected, at most 40 pages, depth 2, 120 s, 1 request per second; `config.yaml`), cleans each page, makes one extraction call to `gpt-4o-mini`, checks every claim's quote against the page it cites, and writes `data/runs/<domain>.json`.

**Exit codes:** 0 when a run JSON was written, including unreachable, blocked and redirected sites; 1 when the URL is rejected before any crawl (`INVALID_URL`, `RESTRICTED_PLATFORM`, also for a start URL that redirects to a restricted platform) or when `OPENAI_API_KEY` is missing for a normally crawled site. Checked here: an invalid URL and a LinkedIn URL both print `REJECTED (...)` and exit 1.

### The run JSON (`data/runs/<domain>.json`)

| Key | What it holds |
| --- | --- |
| `claims` | The evidence ledger: one claim per field, `extracted`, `inferred`, `conflicting` or `not_found` (with `coverage`: the pages actually sent to the model). |
| `profile` | The canonical profile, grouped by section, with `coverage` (pages scanned, fields populated, inferred, conflicting, plus the status and language metadata below) and `gaps_conflicts`. |
| `crawl_status` | `ok`, `unreachable`, `blocked` or `redirected`, decided by the start page. |
| `crawl_error_code` | `SITE_UNREACHABLE` (unreachable, after up to 2 retries for network errors, timeouts and 5xx); `SITE_BLOCKED` (401/403, a bot-protection or CAPTCHA page, or a 429 that outlasts a short backoff); `ROBOTS_DISALLOWED` (robots.txt disallows the start URL); `REDIRECTED_OFF_DOMAIN` (the start URL redirects to another domain). `null` when ok. |
| `crawl_status_reason`, `final_url` | A plain-language reason; `final_url` is set for `redirected`. |
| `site_language`, `site_language_source`, `non_english` | Language flag (PRD Section 9): `en`, `unknown`, a declared code such as `es`, or `non-en`. `non_english` is true only when the text clearly is not English. Flag only: extraction still runs. |
| `limit_reached` | True when the crawl hit its time budget or page cap, or the input-token budget dropped pages (`dropped_pages`). |
| `crawl` | Crawl diagnostics: every page fetched with its status, skipped robots/duplicate/locale/login links, pages refused mid-crawl (`blocked_pages`), redirects dropped (`dropped_after_redirect`), per-page language. |
| `rejected`, `schema_errors` | Claims the evidence check rejected, and why; notes from the claim checks. |
| `classifier`, `focus_retry` | Jev's decisions (or why it skipped); the focused second pass (off by default). |
| `usage`, `timing`, `cache_status` | Tokens and estimated cost, seconds per stage, whether the extraction came from the run cache. |

When `crawl_status` is not `ok`, no model is called, every field is `not_found` with 0 pages checked, and the JSON is still written (exit 0).

## Check and render a saved run (offline; checked here)

```bash
python eval/check_gate.py data/runs/<domain>.json    # schema-valid, every populated claim has evidence; exit 0 = PASS
python -m wi.render data/runs/<domain>.json          # writes data/pages/<domain>.html; no model call
```

The rendered page shows each fact with its status and quote, all `not_found` fields under Gaps, and a banner when the run is partial (`limit_reached`), non-English, or `crawl_status` is not `ok` (with its code and reason).

## Evaluation

The scripts below make no model call unless `--semantic-judge` is passed, and need the runs to exist in `data/runs/` first.

```bash
python eval/baseline.py                  # the 5 dev sites, strict scoring        (checked here)
python eval/score_one.py calendly        # one dev site                           (checked here)
python eval/latency_report.py            # p50/p95 latency, tokens, cost per site (checked here)
python eval/baseline.py --semantic-judge # adds the judge; needs OPENAI_API_KEY   (not checked here)
```

These scripts **overwrite committed report files** (`eval/baseline_report.json`, `eval/score_one_<site>_report.json`, `eval/latency_report.json`). Copy a report you want to keep to a new name, or restore with `git checkout -- eval/<file>`.

### Reproducing the dev benchmark (needs keys and network; not checked here)

1. Run each dev site fresh: `python run_site.py <url> --no-cache` for `https://calendly.com/`, `https://www.loom.com/`, `https://www.typeform.com/`, `https://www.notion.com/`, `https://simplestores.in/`.
2. Score with the judge: `python eval/baseline.py --semantic-judge`, then copy `eval/baseline_report.json` to `eval/baseline_report_<name>_nc<round>.json`.
3. `python eval/latency_report.py`, then copy `eval/latency_report.json` the same way.
4. Repeat 3 times and compare the mean with the committed reports; a difference of 3 points or less is within noise.

### Evaluation limits

- **The dev set is saturated.** Calendly, Loom, Typeform, Notion and SimpleStores were used to build and tune the pipeline, so the dev headline overstates performance on unseen sites.
- **The old 10-site held-out set is contaminated.** After it was first run and scored, fixes B-39 to B-54 were made using its failures, and B-51 re-labelled `customers.segments` in all 10 of its label files. A score on those sites is not a held-out measurement. `eval/held_out.py` exists but was not run for this README.
- **The dev labels were made by hand from the sites' screenshots and pages** (`labeling_metadata` in each `eval/labels/*.json`) and may have gaps; `docs/ERROR_REVIEW.md` attributes about a third of dev errors to the labels.
- **The fresh held-out set is still to be labelled.** It must be labelled by hand before any run, exclude the sites in `eval/peeked_sites.txt`, and be run once on tagged code. No git tag exists yet.

## Project layout

| Path | Purpose |
| --- | --- |
| `run_site.py` | One URL in, one run JSON out |
| `config.yaml` | Caps, limits, model, prices, targets, Jev settings, `prompt_version` |
| `wi/crawl/` | URL validation, fetch and crawl (robots, redirects, retries, blocked/unreachable status), cleaning, run cache, language flag |
| `wi/extract/` | Prompt, model client, extraction pipeline, focused second pass |
| `wi/validate/evidence.py` | The evidence gate: quote on the cited page and value supported by it |
| `wi/classify/` | Optional Jev decisions for `pricing.sales_motion` and `pricing.revenue_model` |
| `wi/profile/`, `wi/render/` | Canonical profile; read-only reference page (no model call) |
| `wi/eval/`, `eval/` | Scoring, latency report, gate check, dev and held-out scripts, labels, saved reports |
| `tests/` | Offline tests; `tests/BEHAVIOURS.md` lists every behaviour and its test |
| `docs/` | PRD, error review (DRAFT), known limitations (DRAFT) |
| `data/runs/`, `data/pages/` | Run outputs and rendered pages (not committed) |

## Rules

1. Never invent missing information. Return `not_found` with coverage.
2. Every `extracted` or `inferred` claim needs a source URL, an exact quote from that page and a retrieval date; the quote is checked by code, not by the model. Never loosen the evidence gate to raise accuracy.
3. Changed logic in `wi/extract/pipeline.py` or `wi/validate/evidence.py`: bump `EXTRACTION_LOGIC_VERSION` in `wi/crawl/cache.py`. Changed prompt: bump `prompt_version` in `config.yaml`. Both invalidate the run cache.
4. Every behaviour change needs a test and a row in `tests/BEHAVIOURS.md`.
5. Use `--no-cache` for any measurement, and judge a change on 3 or more runs.
6. Do not tune on the dev set any further, never edit a label to match an output, and run the fresh held-out set once, on tagged code.
7. The 15-field schema is frozen.
