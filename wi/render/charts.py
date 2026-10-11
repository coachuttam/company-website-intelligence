"""Inline SVG charts for the profile page (B-109). Read-only and stdlib-only, like page.py: no
JavaScript, no external library, no model call. Charts (a) and (b) read the run JSON only; chart
(c) reads the news report that page.py already loads from data/news/<slug>.json.

(a) Field coverage: how many of the frozen fields are Sourced, Inferred, Conflicting or Not found.
    It is coverage, not accuracy: it says nothing about whether a value is right.
(b) Pages used: each page cited as evidence, with how many fields it evidences.
(c) News timeline: news items placed on the lookback window (90 days by default) ending on the
    retrieval date. When the report has no item, there is no chart (page.py shows the reason).

The data functions (coverage_counts, page_field_counts, news_timeline) are separate from the SVG
so they can be tested on their own. Every text in the SVG is HTML-escaped (third-party text), and
each status is written out as a label, not shown by colour alone. Colours come from the page's
CSS variables, so the charts follow light, dark and print.
"""
from __future__ import annotations

import html
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# (status, label, css class) in display order; the classes match page.py's badge colours.
COVERAGE_ORDER = [
    ("extracted", "Sourced", "sourced"),
    ("inferred", "Inferred", "inferred"),
    ("conflicting", "Conflicting", "conflicting"),
    ("not_found", "Not found", "notfound"),
]
EVIDENCING = ("extracted", "inferred", "conflicting")
MAX_PAGE_BARS = 12

CHART_CSS = """
figure.chart { margin: 16px 0 0; }
figure.chart figcaption { font-size: 13px; color: var(--muted); margin-bottom: 6px; }
svg.chart { display: block; width: 100%; height: auto; overflow: visible; }
svg.chart text { fill: var(--ink); font-size: 12px; font-family: inherit; }
svg.chart text.muted { fill: var(--muted); }
svg.chart .axis { stroke: var(--line); stroke-width: 1; }
svg.chart .bar { fill: var(--accent); }
svg.chart .dot { fill: var(--accent); stroke: var(--surface); stroke-width: 1.5; }
svg.chart .seg.sourced { fill: var(--sourced-ink); }
svg.chart .seg.inferred { fill: var(--inferred-ink); }
svg.chart .seg.conflicting { fill: var(--conflicting-ink); }
svg.chart .seg.notfound { fill: var(--notfound-ink); opacity: 0.55; }
svg.chart .seg-label { fill: var(--surface); font-weight: 600; }
.legend { list-style: none; margin: 6px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px 14px; font-size: 13px; }
.legend .sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }
.legend .sw.sourced { background: var(--sourced-ink); }
.legend .sw.inferred { background: var(--inferred-ink); }
.legend .sw.conflicting { background: var(--conflicting-ink); }
.legend .sw.notfound { background: var(--notfound-ink); opacity: 0.55; }
"""


def _e(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _n(x: float) -> str:
    """Compact SVG number (one decimal place at most)."""
    return ("%.1f" % x).rstrip("0").rstrip(".")


# ---------- (a) field coverage ----------

def coverage_counts(run: Dict[str, Any]) -> Dict[str, int]:
    """Count the run's claims per status (one claim per field). Any unknown status counts as
    not_found, matching the page's badge."""
    counts = {status: 0 for status, _, _ in COVERAGE_ORDER}
    for claim in run.get("claims") or []:
        status = claim.get("status")
        counts[status if status in counts else "not_found"] += 1
    return counts


def coverage_svg(counts: Dict[str, int]) -> str:
    total = sum(counts.values())
    if total == 0:
        return ""
    width, height = 640.0, 28.0
    x = 0.0
    segs: List[str] = []
    legend: List[str] = []
    for status, label, cls in COVERAGE_ORDER:
        n = counts.get(status, 0)
        legend.append('<li><span class="sw ' + cls + '" aria-hidden="true"></span>' + _e(label)
                      + ": " + str(n) + "</li>")
        if not n:
            continue
        w = width * n / total
        segs.append('<rect class="seg ' + cls + '" x="' + _n(x) + '" y="0" width="' + _n(w) + '" height="'
                    + _n(height) + '"><title>' + _e(label) + ": " + str(n) + " of " + str(total) + "</title></rect>")
        if w >= 70:
            segs.append('<text class="seg-label" x="' + _n(x + 8) + '" y="18">' + _e(label) + " " + str(n) + "</text>")
        x += w
    summary = ", ".join(_e(label) + " " + str(counts.get(s, 0)) for s, label, _ in COVERAGE_ORDER)
    return (
        '<figure class="chart" id="coverage-chart"><figcaption>Field coverage (not accuracy): '
        + str(total) + " fields by status</figcaption>"
        + '<svg class="chart" viewBox="0 0 640 28" role="img" aria-label="Field coverage: ' + summary + '">'
        + "".join(segs) + "</svg>"
        + '<ul class="legend">' + "".join(legend) + "</ul></figure>"
    )


# ---------- (b) pages used ----------

def page_field_counts(run: Dict[str, Any]) -> List[Tuple[str, int]]:
    """(page URL, number of distinct fields it evidences), most first, then by URL. A page counts
    for a field when it is the claim's cited page or a per-quote source (B-89). not_found claims
    evidence nothing, so they are left out."""
    sources = run.get("evidence_sources") or {}
    fields_by_url: Dict[str, set] = {}
    for claim in run.get("claims") or []:
        if claim.get("status") not in EVIDENCING:
            continue
        urls = set()
        if claim.get("source_url"):
            urls.add(str(claim["source_url"]))
        for entry in sources.get(str(claim.get("claim_id"))) or []:
            urls.update(str(u) for u in entry.get("urls") or [] if u)
        for url in urls:
            fields_by_url.setdefault(url, set()).add(str(claim.get("field")))
    return sorted(((u, len(f)) for u, f in fields_by_url.items()), key=lambda p: (-p[1], p[0]))


def _short_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    text = path if parsed.netloc else url
    return text if len(text) <= 46 else "..." + text[-43:]


def pages_svg(pairs: List[Tuple[str, int]], pages_scanned: Any = None) -> str:
    if not pairs:
        return '<p class="muted">No page is cited as evidence.</p>'
    shown = pairs[:MAX_PAGE_BARS]
    top = max(n for _, n in shown)
    label_w, bar_x, bar_max, row = 300.0, 310.0, 280.0, 22.0
    rows: List[str] = []
    for i, (url, n) in enumerate(shown):
        y = i * row
        w = bar_max * n / top
        word = "field" if n == 1 else "fields"
        rows.append(
            '<g><title>' + _e(url) + ": " + str(n) + " " + word + "</title>"
            + '<text x="' + _n(label_w) + '" y="' + _n(y + 15) + '" text-anchor="end">' + _e(_short_url(url)) + "</text>"
            + '<rect class="bar" x="' + _n(bar_x) + '" y="' + _n(y + 4) + '" width="' + _n(w) + '" height="14"></rect>'
            + '<text x="' + _n(bar_x + w + 6) + '" y="' + _n(y + 15) + '">' + str(n) + "</text></g>"
        )
    height = row * len(shown)
    scanned = (" of " + _e(pages_scanned) + " pages scanned") if pages_scanned is not None else ""
    more = ""
    if len(pairs) > len(shown):
        more = '<p class="muted">' + str(len(pairs) - len(shown)) + " more pages, each evidencing fewer fields, are not drawn.</p>"
    return (
        '<figure class="chart" id="pages-chart"><figcaption>' + str(len(pairs)) + " pages used as evidence"
        + scanned + "; bar = number of fields each page evidences</figcaption>"
        + '<svg class="chart" viewBox="0 0 640 ' + _n(height) + '" role="img" aria-label="'
        + str(len(pairs)) + ' pages used as evidence, with the number of fields each evidences">'
        + "".join(rows) + "</svg></figure>" + more
    )


# ---------- (c) news timeline ----------

def _date(value: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def news_timeline(news: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Place news items on the lookback window ending at retrieved_at. Returns None when there is
    nothing to draw (status not ok, no item, or no usable retrieval date). Points are
    (date, day offset from the window start, items on that date, headlines); `outside` counts
    items with no date or a date outside the window, which are not drawn."""
    items = news.get("items") or []
    end = _date(news.get("retrieved_at"))
    if news.get("status") != "ok" or not items or end is None:
        return None
    days = int(news.get("lookback_days") or 90)
    start = end - timedelta(days=days)
    by_date: Dict[date, List[str]] = {}
    outside = 0
    for it in items:
        d = _date(it.get("published_at"))
        if d is None or d < start or d > end:
            outside += 1
            continue
        by_date.setdefault(d, []).append(str(it.get("headline") or ""))
    points = [(d, (d - start).days, len(h), h) for d, h in sorted(by_date.items())]
    return {"start": start, "end": end, "days": days, "points": points, "outside": outside}


def news_timeline_svg(timeline: Optional[Dict[str, Any]]) -> str:
    if not timeline:
        return ""
    left, right, axis_y = 20.0, 620.0, 70.0
    span = right - left
    days = timeline["days"]
    parts: List[str] = ['<line class="axis" x1="' + _n(left) + '" y1="' + _n(axis_y) + '" x2="' + _n(right)
                        + '" y2="' + _n(axis_y) + '"></line>']
    for offset in sorted(set(list(range(0, days, 30)) + [days])):
        x = left + span * offset / days
        tick = timeline["start"] + timedelta(days=offset)
        anchor = "start" if offset == 0 else ("end" if offset == days else "middle")
        parts.append('<line class="axis" x1="' + _n(x) + '" y1="' + _n(axis_y) + '" x2="' + _n(x) + '" y2="'
                     + _n(axis_y + 5) + '"></line><text class="muted" x="' + _n(x) + '" y="' + _n(axis_y + 18)
                     + '" text-anchor="' + anchor + '">' + _e(tick.isoformat()) + "</text>")
    for d, offset, count, headlines in timeline["points"]:
        x = left + span * offset / days
        tip = d.isoformat() + ": " + "; ".join(headlines)
        dots = "".join('<circle class="dot" cx="' + _n(x) + '" cy="' + _n(axis_y - 8 - 9 * k) + '" r="4"></circle>'
                       for k in range(min(count, 5)))
        label = ('<text x="' + _n(x) + '" y="' + _n(axis_y - 8 - 9 * min(count, 5) - 2) + '" text-anchor="middle">'
                 + str(count) + "</text>") if count > 1 else ""
        parts.append("<g><title>" + _e(tip) + "</title>" + dots + label + "</g>")
    drawn = sum(p[2] for p in timeline["points"])
    note = ""
    if timeline["outside"]:
        note = '<p class="muted">' + str(timeline["outside"]) + " items with no date or a date outside the window are not drawn.</p>"
    return (
        '<figure class="chart" id="news-timeline"><figcaption>' + str(drawn) + " items on a " + str(days)
        + "-day axis, " + _e(timeline["start"].isoformat()) + " to " + _e(timeline["end"].isoformat())
        + " (one dot per item; a number marks several on one day)</figcaption>"
        + '<svg class="chart" viewBox="0 0 640 96" role="img" aria-label="News timeline: ' + str(drawn)
        + " items between " + _e(timeline["start"].isoformat()) + " and " + _e(timeline["end"].isoformat()) + '">'
        + "".join(parts) + "</svg></figure>" + note
    )
