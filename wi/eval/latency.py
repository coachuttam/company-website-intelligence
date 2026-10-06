"""AC-10 / CST-02 (B-74): per-website latency, token and cost reporting.

Two pieces, both pure apart from the clock:

  - PhaseTimer: run_site.py wraps each stage of one run (crawl, clean, extract, second pass,
    classifier) so the run JSON records where the wall-clock time went, plus the end-to-end
    total. Before B-74 the only timing on disk was usage.elapsed_s, which covers the LLM call
    alone -- a crawl of 40 pages at 1 request/second never showed up anywhere, so p50/p95
    latency per website (AC-10) could not be computed from the run files.
  - latency_report(): reads a set of run JSONs and reports p50/p95 total latency, tokens and
    estimated cost per website, against config.yaml's targets (PRD Section 13).

A run that came from the run cache (cache_status "hit") is left out of the statistics and
listed as skipped: it made no model call, so its latency and cost are not a real measurement
(CLAUDE.md: use --no-cache for any real measurement). A run written before B-74 has no
"timing" key and is skipped the same way rather than guessed at.

Percentiles use linear interpolation between the closest ranks (numpy's default), so with a
5- or 10-site set p95 sits just under the slowest site rather than being exactly it.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Callable, Dict, Iterator, List, Optional, Tuple


class PhaseTimer:
    """Records seconds per named phase and the total since the timer was created. `clock` is
    injectable so tests do not depend on real time."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._start = clock()
        self._phases: Dict[str, float] = {}

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        began = self._clock()
        try:
            yield
        finally:
            self._phases[name] = self._phases.get(name, 0.0) + (self._clock() - began)

    def as_dict(self) -> Dict[str, float]:
        out = {f"{name}_s": round(seconds, 3) for name, seconds in self._phases.items()}
        out["total_s"] = round(self._clock() - self._start, 3)
        return out


def percentile(values: List[float], q: float) -> Optional[float]:
    """q in [0, 100]. Linear interpolation between closest ranks; None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q / 100.0
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (pos - lower)


def run_record(name: str, data: dict) -> Tuple[Optional[dict], Optional[str]]:
    """One website's numbers from its run JSON, or (None, reason) when it can't be measured."""
    if data.get("cache_status") == "hit":
        return None, "cache hit (no model call, not a real measurement; re-run with --no-cache)"
    timing = data.get("timing")
    if not timing or "total_s" not in timing:
        return None, "no timing recorded (run predates B-74)"

    usage = data.get("usage") or {}
    classifier = data.get("classifier") or {}
    llm_cost = usage.get("estimated_cost_usd")
    jev_cost = classifier.get("estimated_cost_usd") or 0.0
    return {
        "site": name,
        "total_s": timing["total_s"],
        "phases": {k: v for k, v in timing.items() if k != "total_s"},
        "llm_tokens": usage.get("total_tokens", 0),
        "jev_tokens": (classifier.get("input_tokens") or 0) + (classifier.get("output_tokens") or 0),
        # None when the LLM price is unknown: a missing price must not read as a free run.
        "cost_usd": None if llm_cost is None else round(llm_cost + jev_cost, 6),
        "pages": len((data.get("crawl") or {}).get("pages", [])),
    }, None


def latency_report(runs: List[Tuple[str, dict]], targets: Optional[dict] = None) -> dict:
    """`runs` is a list of (site name, run JSON dict). `targets` is config.yaml's `targets`."""
    targets = targets or {}
    measured, skipped = [], []
    for name, data in runs:
        record, reason = run_record(name, data)
        if record is None:
            skipped.append({"site": name, "reason": reason})
        else:
            measured.append(record)

    latencies = [r["total_s"] for r in measured]
    costs = [r["cost_usd"] for r in measured if r["cost_usd"] is not None]
    tokens = [r["llm_tokens"] for r in measured]
    summary = {
        "sites_measured": len(measured),
        "latency_p50_s": percentile(latencies, 50),
        "latency_p95_s": percentile(latencies, 95),
        "llm_tokens_p50": percentile(tokens, 50),
        "llm_tokens_p95": percentile(tokens, 95),
        "cost_mean_usd": (sum(costs) / len(costs)) if costs else None,
        "cost_p95_usd": percentile(costs, 95),
        "sites_with_unknown_cost": sum(1 for r in measured if r["cost_usd"] is None),
    }
    checks = {}
    for key in ("latency_p50_s", "latency_p95_s", "cost_mean_usd", "cost_p95_usd"):
        if targets.get(key) is not None and summary[key] is not None:
            checks[key] = {"value": summary[key], "target": targets[key],
                           "met": summary[key] <= targets[key]}
    return {"sites": measured, "skipped": skipped, "summary": summary, "targets": checks}
