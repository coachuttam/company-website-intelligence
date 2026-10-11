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
