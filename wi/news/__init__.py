"""P1 latest-news snapshot, built to the cut line (B-104; PRD Section 8, AC-12 partial).

In scope: the company's OWN newsroom and feeds (company_announcement items), found on its own domain,
parsed with feedparser, kept within a 90-day lookback, de-duplicated, capped at 10, and tagged with a
rule-based event type. No model call, no GDELT, no third-party article fetching. Written to its own
file (data/news/<slug>.json) with its own latency/cost record, never merged into the 15 scored fields
or the run/profile JSON, and never scored. A news failure never blocks the website profile.
"""
