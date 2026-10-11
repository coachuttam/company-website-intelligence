# P1 news spike (cut line only): company-own news snapshot

**Scope.** PRD Section 8, built only to the cut line, as an exception: the Section 8 Week 3 gate is
arguably not met, with AC-02 at 35%.
- **In:** the company's own newsroom and feeds on its own domain, parsed with feedparser.
- **Limits:** 90-day lookback, at most 10 de-duplicated items, a rule-based event type.
- **Record:** its own latency and cost record.
- **Out:** GDELT, third-party article fetching, and any model call.

**How to run.** Off by default:
- `run_site.py <url> --news`, or
- `python -m wi.news data/runs/<slug>.json`

Either writes `data/news/<slug>.json` (git-ignored). The run and profile JSON are never changed, and
nothing is scored.

## Small evaluation (5 development sites, 2026-10-11, no model calls)

| Site | Status | Items | Feeds read | URLs fetched / tried | Latency |
| --- | --- | ---: | ---: | --- | ---: |
| snowflake.com | ok | 10 | 1 | 5 / 11 | 13.7 s |
| notion.com | not_found (no company feed) | 0 | 0 | 2 / 11 | 11.8 s |
| cashfree.com | ok | 10 | 2 | 4 / 11 | 13.9 s |
| mercury.com | not_found (no company feed) | 0 | 0 | 2 / 11 | 11.5 s |
| chargebee.com | ok | 9 | 2 | 5 / 11 | 14.8 s |

## AC-12, reported as partial

| AC-12 metric | Result | Note |
| --- | --- | --- |
| Entity-match precision | Not informative | Every item comes from the company's own domain, so it is about the company by construction. Third-party news, where the metric matters, is out of scope. |
| Duplicate rate | 0 of 39 in-lookback entries | |
| Source-access rate | 18 of 55 URLs tried (33%) | The rest were 404s, 401/403s and bot-challenge pages, never retried. All 29 kept items had feed text as evidence. |
| News latency | p50 13.7 s, max 14.8 s (n = 5) | |
| Cost | $0 | 0 model calls |

## What the quick look found (15 items)

- **Blog feeds, not newsroom feeds.** Most of the feeds found are blog feeds, so most items are
  articles (guides, explainers), not material announcements. They are company-published, but
  "company_announcement" overstates them.
- **The rule-based event type misfires on articles.** For example, a payment "settlement cycle"
  explainer is labelled legal_regulatory.
- **Two sites have no company feed** (Notion and Mercury).

A next step, not done, would separate newsroom/press feeds from blog feeds before classifying.

## Corroboration, cut line 1 (B-106, 2026-10-11)

**What it does.** For each qualifying company item, one GDELT DOC 2.0 headline search covers ±7 days
around the item's date. Matching is by rules on the headline only:
- **No article fetching, no model calls.**
- **Statuses:** `possible_coverage`, `not_corroborated` or `not_checked`, never "corroborated" or
  "verified".

**Rules, fixed before any result was seen:**
- **Qualifying items (step 0):** the feed URL path contains news, newsroom, press, press-releases or
  media, OR the rule-based event type is not "other".
- **Match:** the company name as a whole phrase (outside the domain text), plus the company's domain
  or a product name, in the third-party headline.
- **Independence:** the headline is not on the company's domain or a press wire, and is dated within
  ±7 days.
- **Limits:** at most 5 GDELT queries and 120 s per company, one GDELT request every 5 s. A 429 or
  timeout gives `not_checked` and is not retried.

**Result on the same 5 sites (no model calls, $0):**

| Site | Items | Qualified | GDELT queries (failed) | Candidates seen / matched | Statuses |
| --- | ---: | ---: | --- | --- | --- |
| snowflake.com | 10 | 0 | 0 | 0 / 0 | 10 not_checked |
| cashfree.com | 10 | 1 | 1 (1 timeout) | 0 / 0 | 10 not_checked |
| chargebee.com | 9 | 4 | 4 (3 HTTP 429) | 0 / 0 | 1 not_corroborated, 8 not_checked |
| notion.com | 0 | – | – | – | no company feed |
| mercury.com | 0 | – | – | – | no company feed |

- **Latency:** p50 11.9 s, max 70.4 s (n = 5).
- **What it shows:**
  - Only 5 of 29 items qualified, and all 5 are blog articles whose rule-based event type was not
    "other". No feed was a newsroom/press feed.
  - GDELT answered once (0 articles); the other 4 queries timed out or were rate-limited.
  - No candidate headline was found, so entity-match precision cannot be measured on this sample.
- **AC-12 is still partial.**
- **What a useful result would need (not done):**
  - sites with a real newsroom/press feed;
  - a slower GDELT pace, or a scheduled run;
  - the article-fetching stage (cut line 2) before anything could be called corroborated.
