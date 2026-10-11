"""Collect the news snapshot for one company (B-104). Never raises: any failure gives a report with
status "unavailable" and the reason, so the website profile is never blocked (R-NEWS-006, B-24)."""
from __future__ import annotations

import json
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

from wi.news.classify import event_type
from wi.news.dedupe import dedupe
from wi.news.entity import Company, belongs_to, company_from_run
from wi.news.http import Fetcher
from wi.news.schema import LOOKBACK_DAYS, MAX_ITEMS, TOTAL_BUDGET_S, NewsItem, NewsReport
from wi.news.sources.newsroom import discover_and_read


def _record(started: float, clock, **counts) -> dict:
    return {"latency_s": round(clock() - started, 3), "model_calls": 0, "prompt_tokens": 0,
            "completion_tokens": 0, "estimated_cost_usd": 0.0, **counts}


def collect(company: Company, fetcher: Optional[Fetcher] = None, today: Optional[date] = None,
            clock: Callable[[], float] = time.monotonic, lookback_days: int = LOOKBACK_DAYS) -> NewsReport:
    today = today or date.today()
    started = clock()
    base = dict(company_id=company.company_id, company_name=company.name, domain=company.domain,
                retrieved_at=today.isoformat(), lookback_days=lookback_days)
    try:
        fetcher = fetcher or Fetcher()
        entries, log = discover_and_read(company, fetcher, lambda: clock() - started < TOTAL_BUDGET_S)
        cutoff = today - timedelta(days=lookback_days)
        own = [e for e in entries if e.link and belongs_to(e.link, company.domain)]
        undated = sum(1 for e in own if e.published is None)
        recent = [e for e in own if e.published is not None and cutoff <= e.published <= today]
        unique, collapsed = dedupe(recent)
        unique = sorted(unique, key=lambda e: (e.published, e.link), reverse=True)[:MAX_ITEMS]
        items = []
        for i, e in enumerate(unique, 1):
            evidence = e.summary or None
            items.append(NewsItem(
                news_id=f"news_{i:03d}", company_id=company.company_id, source_class="company_announcement",
                publisher=e.feed_title or company.name, url=e.link, headline=e.title,
                published_at=e.published.isoformat(), retrieved_at=today.isoformat(), evidence=evidence,
                event_type=event_type(e.title, e.summary),
                relevance_status="matched" if evidence else "inaccessible",
                note=None if evidence else "feed gives a headline only; article not fetched (cut line)"))
        counts = dict(feeds_ok=sum(1 for x in log if x["kind"] == "feed" and x["status"] == "ok"),
                      entries_seen=len(entries), off_domain_entries=len(entries) - len(own),
                      undated_entries=undated, in_lookback=len(recent), duplicates_collapsed=collapsed,
                      items_kept=len(items))
        status = "ok" if items else "not_found"
        reason = None if items else ("no company feed found" if counts["feeds_ok"] == 0
                                     else f"no dated company item in the last {lookback_days} days")
        return NewsReport(**base, status=status, reason=reason, items=items, sources=log,
                          record=_record(started, clock, **counts))
    except Exception as e:   # non-blocking by design
        return NewsReport(**base, status="unavailable", reason=f"{type(e).__name__}: {e}",
                          record=_record(started, clock))


def collect_for_run(run_path: Path, out_dir: Path, fetcher: Optional[Fetcher] = None,
                    today: Optional[date] = None) -> tuple:
    """(report, written path or None). Reads a saved run JSON; writes <out_dir>/<slug>.json."""
    run = json.loads(Path(run_path).read_text(encoding="utf-8"))
    company = company_from_run(run)
    if company is None:
        return None, None
    report = collect(company, fetcher=fetcher, today=today)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / Path(run_path).name
    out.write_text(json.dumps(report.model_dump(mode="json"), indent=2), encoding="utf-8")
    return report, out
