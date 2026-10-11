"""Reference profile page (Final PRD, Section 6, Week 4): turns one saved run file into a single
self-contained HTML page. Read-only, no LLM call, no network -- it only reads JSON that
`run_site.py` already wrote to data/runs/. The PRD's own framing applies: this proves the schema
can drive a product surface; it is not a polished dashboard and not a Prajna integration.

Input: the dict `run_site.py` writes (keys used: `profile`, `claims`, `announcements`,
`limit_reached`, `crawl`, `schema_version`). The `profile` block (wi/profile/builder.py) holds
the facts grouped under headings, each entry carrying only value/status/claim_id; the exact
quote, source URL and retrieval date live in the `claims` ledger, so this module joins the two
by claim_id to build each fact's evidence drawer.

What each PRD Section 6 item maps to:
1. Header: company name, domain, "Website-sourced profile" label (plus a one-line reminder that a
   company website is a self-reported source).
2. Trust and coverage strip: straight from `profile.coverage`.
3-8. One section per profile group, in PRD order. A group with no populated fact is omitted
   entirely rather than rendered as an empty card.
9. Gaps and conflicts: every not_found and conflicting field lives here and nowhere else.
10. Evidence ledger: every claim in the ledger, each with its source drawer.
Every displayed fact carries a status badge: Sourced (extracted), Inferred, or Conflicting.

Deliberate omission: the PRD's item 6 ("Positioning and claimed differentiators") has no field in
the frozen 15-field schema-v1, so there is nothing real to show -- the section is left out rather
than filled with invented content.

Safety: every value, quote, URL and title comes from a third-party website, so all text is
HTML-escaped, and a source URL only becomes a link if it starts with http:// or https:// (a
`javascript:` URL is shown as plain text). The page uses no JavaScript (evidence drawers are
native <details> elements) and loads nothing external, so it renders offline. This module imports
only the standard library on purpose (see tests/test_render.py, which enforces it).

B-108 (presentable report): a print stylesheet (light colours whatever the screen theme, A4, no
facts split across pages), a cover block shown only in print (company name, domain, retrieval date,
"Website-sourced profile"), and `render_pdf_file`, which prints the same page to
data/pages/<slug>.pdf through wi/render/pdf.py (Playwright, optional). In the PDF the evidence
drawers are open, since a printed <details> cannot be clicked. B-109: the inline SVG charts from
wi/render/charts.py (field coverage, pages used, news timeline).
"""
from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from wi.render import charts

NL = chr(10)  # newline, built here so this file needs no backslash escapes anywhere

STATUS_LABEL = {
    "extracted": "Sourced",
    "inferred": "Inferred",
    "conflicting": "Conflicting",
    "not_found": "Not found",
}
STATUS_CLASS = {
    "extracted": "sourced",
    "inferred": "inferred",
    "conflicting": "conflicting",
    "not_found": "notfound",
}

# (profile group key, section heading, anchor id) in PRD Section 6 order.
SECTIONS = [
    ("company_identity", "Company overview", "overview"),
    ("products_services", "Products and services", "products"),
    ("customers_positioning", "Customers and industries", "customers"),
    ("pricing_commercial", "Pricing and commercial signals", "pricing"),
    ("evidence_traction", "Customers, partnerships, certifications and claims", "traction"),
    ("company_comparisons", "Comparisons", "comparisons"),
]

FIELD_LABELS = {
    "name": "Company name",
    "description": "Description",
    "headquarters": "Headquarters",
    "names": "Products",
    "delivery_model": "Delivery model",
    "segments": "Customer segments",
    "industries": "Industries",
    "public_plans": "Public plans",
    "sales_motion": "Sales motion",
    "free_trial": "Free trial",
    "revenue_model": "Revenue model",
    "named_customers": "Named customers",
    "certifications": "Certifications",
    "partnerships": "Partnerships",
    "named_alternatives": "Named alternatives",
}

CSS = """
:root {
  --bg: #f6f6f3; --surface: #ffffff; --ink: #1d2227; --muted: #5b6670; --line: #dcdfe2;
  --accent: #1f4e79;
  --sourced-bg: #e3f1e6; --sourced-ink: #1e5a2d;
  --inferred-bg: #fbefd3; --inferred-ink: #7a4e00;
  --conflicting-bg: #f9dcdc; --conflicting-ink: #8a1f1f;
  --notfound-bg: #e9ebed; --notfound-ink: #4a545c;
  --banner-bg: #fbefd3; --banner-ink: #5c3b00;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #14181c; --surface: #1c2227; --ink: #e6e9ec; --muted: #9aa5ae; --line: #323a41;
    --accent: #8fb8de;
    --sourced-bg: #1e3a27; --sourced-ink: #a6dbb3;
    --inferred-bg: #44330f; --inferred-ink: #f0cf8c;
    --conflicting-bg: #4a2222; --conflicting-ink: #f4b4b4;
    --notfound-bg: #2a3036; --notfound-ink: #b3bdc5;
    --banner-bg: #44330f; --banner-ink: #f0cf8c;
  }
}
:root[data-theme="dark"] {
  --bg: #14181c; --surface: #1c2227; --ink: #e6e9ec; --muted: #9aa5ae; --line: #323a41;
  --accent: #8fb8de;
  --sourced-bg: #1e3a27; --sourced-ink: #a6dbb3;
  --inferred-bg: #44330f; --inferred-ink: #f0cf8c;
  --conflicting-bg: #4a2222; --conflicting-ink: #f4b4b4;
  --notfound-bg: #2a3036; --notfound-ink: #b3bdc5;
  --banner-bg: #44330f; --banner-ink: #f0cf8c;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--ink);
  font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}
main { max-width: 880px; margin: 0 auto; padding: 24px 16px 64px; }
header h1 { margin: 0 0 4px; font-size: 28px; line-height: 1.2; text-wrap: balance; }
.sub { margin: 0; color: var(--muted); }
.tag {
  display: inline-block; margin-left: 8px; padding: 1px 8px; border: 1px solid var(--line);
  border-radius: 999px; font-size: 12px; color: var(--muted); vertical-align: middle;
}
.note { margin: 10px 0 0; color: var(--muted); font-size: 13px; }
.banner {
  margin: 16px 0 0; padding: 10px 14px; border-radius: 6px;
  background: var(--banner-bg); color: var(--banner-ink); font-size: 14px;
}
.strip {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 1px;
  margin: 20px 0 8px; background: var(--line); border: 1px solid var(--line); border-radius: 8px;
  overflow: hidden;
}
.strip div { background: var(--surface); padding: 10px 12px; }
.strip dt { font-size: 11px; letter-spacing: 0.06em; text-transform: uppercase; color: var(--muted); }
.strip dd { margin: 2px 0 0; font-size: 20px; font-weight: 600; font-variant-numeric: tabular-nums; }
section { margin-top: 32px; }
h2 { margin: 0 0 12px; font-size: 18px; padding-bottom: 6px; border-bottom: 1px solid var(--line); }
h3 { margin: 0; font-size: 13px; font-weight: 600; color: var(--muted); }
.fact { padding: 12px 0; border-bottom: 1px solid var(--line); }
.fact:last-child { border-bottom: 0; }
.fact-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.value { margin: 4px 0 0; max-width: 65ch; }
.chips { list-style: none; margin: 6px 0 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.chips li { padding: 2px 10px; border: 1px solid var(--line); border-radius: 999px; background: var(--surface); }
.badge {
  display: inline-block; padding: 0 8px; border-radius: 4px; font-size: 12px; font-weight: 600;
  line-height: 20px;
}
.badge.sourced { background: var(--sourced-bg); color: var(--sourced-ink); }
.badge.inferred { background: var(--inferred-bg); color: var(--inferred-ink); }
.badge.conflicting { background: var(--conflicting-bg); color: var(--conflicting-ink); }
.badge.notfound { background: var(--notfound-bg); color: var(--notfound-ink); }
details.drawer { margin-top: 6px; font-size: 14px; }
details.drawer > summary { cursor: pointer; color: var(--accent); }
details.drawer > summary:focus-visible, a:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.drawer-body { margin: 6px 0 0; padding: 8px 12px; background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
figure.quote { margin: 0 0 8px; }
figure.quote strong { display: block; font-size: 13px; }
blockquote { margin: 2px 0 0; padding-left: 10px; border-left: 3px solid var(--line); color: var(--ink); overflow-wrap: anywhere; }
.meta, .muted { margin: 4px 0 0; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
a { color: var(--accent); }
.gap { padding: 8px 0; border-bottom: 1px solid var(--line); display: flex; gap: 8px; flex-wrap: wrap; align-items: baseline; }
.gap:last-child { border-bottom: 0; }
.ledger details.item { border-bottom: 1px solid var(--line); padding: 6px 0; }
.ledger summary { cursor: pointer; display: flex; gap: 8px; flex-wrap: wrap; align-items: baseline; }
.ledger code { font-size: 13px; }
.preview { color: var(--muted); overflow-wrap: anywhere; }
footer { margin-top: 40px; color: var(--muted); font-size: 12px; }
.cover { display: none; }
@page { size: A4; margin: 16mm 14mm; }
@media print {
  :root, :root:not([data-theme="light"]), :root[data-theme="dark"] {
    --bg: #ffffff; --surface: #ffffff; --ink: #1d2227; --muted: #4f5a63; --line: #c9ced3;
    --accent: #1f4e79;
    --sourced-bg: #e3f1e6; --sourced-ink: #1e5a2d;
    --inferred-bg: #fbefd3; --inferred-ink: #7a4e00;
    --conflicting-bg: #f9dcdc; --conflicting-ink: #8a1f1f;
    --notfound-bg: #e9ebed; --notfound-ink: #4a545c;
    --banner-bg: #fbefd3; --banner-ink: #5c3b00;
  }
  body { font-size: 11pt; background: #ffffff; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  main { max-width: none; padding: 0; }
  .cover {
    display: flex; flex-direction: column; justify-content: center; min-height: 240mm;
    break-after: page; page-break-after: always;
  }
  .cover .kicker { margin: 0; font-size: 12pt; letter-spacing: 0.08em; text-transform: uppercase; color: var(--muted); }
  .cover .name { margin: 8px 0 4px; font-size: 32pt; font-weight: 700; line-height: 1.15; }
  .cover .domain { margin: 0; font-size: 14pt; }
  .cover .retrieved { margin: 18px 0 0; font-size: 12pt; }
  .cover .note { max-width: 60ch; }
  section { break-before: auto; }
  h2, h3 { break-after: avoid; page-break-after: avoid; }
  .fact, .gap, figure, .strip, .ledger details.item { break-inside: avoid; page-break-inside: avoid; }
  details.drawer > summary, .ledger summary { list-style: none; }
  a { color: var(--ink); text-decoration: none; }
  footer { margin-top: 24px; }
}
""" + charts.CHART_CSS


def esc(value: Any) -> str:
    """HTML-escape any value (including quotes, so it is safe in attributes too)."""
    return html.escape("" if value is None else str(value), quote=True)


def _label(field: str) -> str:
    short = field.split(".")[-1]
    return FIELD_LABELS.get(short, short.replace("_", " ").capitalize())


def _badge(status: Optional[str]) -> str:
    key = status if status in STATUS_LABEL else "not_found"
    return '<span class="badge ' + STATUS_CLASS[key] + '">' + STATUS_LABEL.get(status or "", "Not found") + "</span>"


def _link(url: Any) -> str:
    """A real link only for http(s) URLs; anything else (e.g. javascript:) stays inert text."""
    text = "" if url is None else str(url)
    if text.lower().startswith(("http://", "https://")):
        return '<a href="' + esc(text) + '" rel="noopener noreferrer" target="_blank">' + esc(text) + "</a>"
    return esc(text)


def _items(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v not in (None, "")]
    return [str(value)]


def _render_value(value: Any) -> str:
    if isinstance(value, list):
        items = _items(value)
        return '<ul class="chips">' + "".join("<li>" + esc(v) + "</li>" for v in items) + "</ul>"
    return '<p class="value">' + esc(value) + "</p>"


def _evidence_pairs(claim: Dict[str, Any]) -> List[Tuple[Optional[str], str]]:
    """(value-it-supports or None, quote) pairs. A list claim with one quote per value pairs them
    up; a multi-line quote string is shown as separate fragments."""
    evidence = claim.get("evidence")
    value = claim.get("value")
    if isinstance(evidence, list):
        quotes = [str(q) for q in evidence if q]
        if isinstance(value, list) and len(value) == len(evidence):
            return [(str(v), str(q)) for v, q in zip(value, evidence) if q]
        return [(None, q) for q in quotes]
    if isinstance(evidence, str) and evidence.strip():
        fragments = [line.strip() for line in evidence.split(NL) if line.strip()]
        return [(None, f) for f in fragments]
    return []


def _drawer(claim: Optional[Dict[str, Any]], summary: str = "Evidence") -> str:
    if claim is None:
        return (
            '<details class="drawer"><summary>' + esc(summary) + "</summary>"
            '<div class="drawer-body"><p class="muted">No ledger entry was found for this claim.</p></div></details>'
        )
    parts: List[str] = []
    if claim.get("status") == "inferred":
        parts.append(
            '<p class="muted">Inferred: the company does not state this directly. '
            "The quote below is what the inference rests on.</p>"
        )
    pairs = _evidence_pairs(claim)
    if not pairs:
        parts.append('<p class="muted">No quote recorded.</p>')
    # B-89: when the quotes come from several pages, each quote shows its own source.
    per_quote = {str(e.get("quote")): e.get("urls") or [] for e in (claim.get("_quote_sources") or [])}
    for value, quote in pairs:
        lead = "<strong>" + esc(value) + "</strong>" if value else ""
        urls = per_quote.get(quote)
        own = ('<figcaption class="meta">From: ' + ", ".join(_link(u) for u in urls) + "</figcaption>"
               if urls else "")
        parts.append('<figure class="quote">' + lead + "<blockquote>" + esc(quote) + "</blockquote>"
                     + own + "</figure>")
    meta: List[str] = []
    if claim.get("source_url"):
        label = "Cited page: " if per_quote else "Source: "
        meta.append(label + _link(claim["source_url"]))
    if claim.get("page_title"):
        meta.append(esc(claim["page_title"]))
    if claim.get("retrieved_at"):
        meta.append("Retrieved " + esc(claim["retrieved_at"]))
    if meta:
        parts.append('<p class="meta">' + " &middot; ".join(meta) + "</p>")
    if claim.get("notes"):
        parts.append('<p class="muted">Note: ' + esc(claim["notes"]) + "</p>")
    return (
        '<details class="drawer"><summary>' + esc(summary) + '</summary><div class="drawer-body">'
        + "".join(parts) + "</div></details>"
    )


def _fact(label: str, entry: Dict[str, Any], claim: Optional[Dict[str, Any]]) -> str:
    return (
        '<div class="fact"><div class="fact-head"><h3>' + esc(label) + "</h3>"
        + _badge(entry.get("status")) + "</div>"
        + _render_value(entry.get("value")) + _drawer(claim) + "</div>"
    )


def _announcement(a: Dict[str, Any]) -> str:
    bits = [esc(a.get("category")), esc(a.get("date"))]
    head = " &middot; ".join(b for b in bits if b)
    claim_like = {
        "evidence": a.get("evidence"), "value": None, "status": "extracted",
        "source_url": a.get("source_url"), "page_title": a.get("page_title"),
        "retrieved_at": a.get("retrieved_at"),
    }
    return (
        '<div class="fact"><div class="fact-head"><h3>' + head + "</h3>" + _badge("extracted") + "</div>"
        + '<p class="value">' + esc(a.get("text")) + "</p>" + _drawer(claim_like) + "</div>"
    )


NEWS_TITLE = "Latest news (company's own feed, not verified)"


def _news_section(news: Dict[str, Any]) -> str:
    """B-105: the separate news section, from data/news/<slug>.json (wi/news, B-104). Third-party
    and company feeds alike are shown as reported items, never as verified facts."""
    status = news.get("status")
    items = news.get("items") or []
    intro = ('<p class="note">From the company\'s own news or blog feed, last '
             + esc(news.get("lookback_days") or 90) + " days, retrieved " + esc(news.get("retrieved_at"))
             + ". Not part of the profile above, not verified, and not scored. Event types are rule-based.</p>")
    if status != "ok" or not items:
        reason = news.get("reason") or "no item found"
        return _section(NEWS_TITLE, "news", intro + '<p class="muted">' + esc(status or "not_found")
                        + ": " + esc(reason) + "</p>")
    rows = []
    for it in items:
        url = str(it.get("url") or "")
        headline = esc(it.get("headline"))
        if url.lower().startswith(("http://", "https://")):
            headline = ('<a href="' + esc(url) + '" rel="noopener noreferrer" target="_blank">' + headline + "</a>")
        rows.append(
            "<li>" + esc(it.get("published_at")) + " &middot; " + headline
            + ' <span class="muted">&middot; ' + esc(it.get("publisher")) + " &middot; "
            + esc(it.get("source_class")) + " &middot; event type (rule-based): "
            + esc(it.get("event_type") or "other") + "</span></li>")
    timeline = charts.news_timeline_svg(charts.news_timeline(news))   # B-109
    return _section(NEWS_TITLE, "news", intro + timeline + "<ul>" + "".join(rows) + "</ul>")


def _domain(run: Dict[str, Any]) -> str:
    pages = (run.get("crawl") or {}).get("pages") or []
    if pages and pages[0].get("url"):
        host = urlparse(str(pages[0]["url"])).netloc
        if host:
            return host[4:] if host.startswith("www.") else host
    claims = run.get("claims") or []
    if claims and ":" in str(claims[0].get("claim_id", "")):
        return str(claims[0]["claim_id"]).split(":")[0]
    return ""


def _percent(rate: Any) -> str:
    if isinstance(rate, (int, float)):
        return str(round(rate * 100)) + "%"
    return "n/a"


def _strip(coverage: Dict[str, Any]) -> str:
    total = coverage.get("total_fields")
    populated = coverage.get("fields_populated")
    populated_text = str(populated) + " of " + str(total) if total is not None else str(populated)
    cells = [
        ("Pages scanned", coverage.get("pages_scanned")),
        ("Fields populated", populated_text),
        ("Evidence support", _percent(coverage.get("evidence_support_rate"))),
        ("Inferred", coverage.get("fields_inferred")),
        ("Conflicts", coverage.get("fields_conflicting")),
        ("Not found", coverage.get("fields_not_found")),
        ("Last retrieved", coverage.get("last_retrieved_at") or "n/a"),
    ]
    body = "".join("<div><dt>" + esc(k) + "</dt><dd>" + esc(v if v is not None else "n/a") + "</dd></div>" for k, v in cells)
    return '<dl class="strip">' + body + "</dl>"


def _section(title: str, anchor: str, body: str) -> str:
    return '<section id="' + anchor + '"><h2>' + esc(title) + "</h2>" + body + "</section>"


def _gaps(gaps: List[Dict[str, Any]], lookup: Dict[str, Dict[str, Any]]) -> str:
    if not gaps:
        return '<p class="muted">No gaps: every core field has a value.</p>'
    rows: List[str] = []
    for entry in gaps:
        claim = lookup.get(str(entry.get("claim_id")))
        label = _label(str(entry.get("field", "")))
        if entry.get("status") == "conflicting":
            rows.append(
                '<div class="fact"><div class="fact-head"><h3>' + esc(label) + "</h3>" + _badge("conflicting")
                + '</div><p class="muted">The site gives different answers on different pages. '
                "Neither is picked; both are shown with their quotes.</p>"
                + _render_value((claim or entry).get("value")) + _drawer(claim, "Both sources") + "</div>"
            )
            continue
        checked = ""
        cov = (claim or {}).get("coverage") or {}
        if cov.get("pages_checked") is not None:
            checked = '<span class="muted">Checked ' + esc(cov["pages_checked"]) + " pages, nothing found.</span>"
        rows.append('<div class="gap"><h3>' + esc(label) + "</h3>" + _badge("not_found") + checked + "</div>")
    return "".join(rows)


def _ledger(claims: List[Dict[str, Any]]) -> str:
    items: List[str] = []
    for claim in claims:
        value = claim.get("value")
        preview = ", ".join(_items(value)) if value is not None else ""
        if len(preview) > 90:
            preview = preview[:87] + "..."
        items.append(
            '<details class="item"><summary><code>' + esc(claim.get("field")) + "</code>"
            + _badge(claim.get("status")) + '<span class="preview">' + esc(preview) + "</span></summary>"
            + _drawer(claim, "Source") + "</details>"
        )
    return '<div class="ledger">' + "".join(items) + "</div>"


def _cover(name: str, domain: str, retrieved: Any) -> str:
    """B-108: the print-only cover block (hidden on screen by CSS)."""
    return (
        '<div class="cover"><p class="kicker">Website-sourced profile</p>'
        '<p class="name">' + esc(name) + '</p><p class="domain">' + esc(domain) + "</p>"
        '<p class="retrieved">Retrieved ' + esc(retrieved or "n/a") + "</p>"
        '<p class="note">A company website is a self-reported source. Facts in this report are what the '
        "company states about itself and are not independently verified.</p></div>"
    )


def render_profile_html(run: Dict[str, Any], source_name: str = "", news: Optional[Dict[str, Any]] = None,
                        open_drawers: bool = False) -> str:
    """Render one run dict (the JSON run_site.py writes) to a complete HTML document string.
    `news` (B-105): the run's news report, shown as a separate section at the bottom when given;
    without it the page is exactly as before. `open_drawers` (B-108, used for the PDF): evidence
    drawers start open."""
    profile = run.get("profile") or {}
    claims = run.get("claims") or []
    # B-89: attach each claim's per-quote sources (run-level evidence_sources) for the drawer.
    sources = run.get("evidence_sources") or {}
    lookup = {str(c.get("claim_id")): {**c, "_quote_sources": sources.get(str(c.get("claim_id")))}
              for c in claims}

    domain = _domain(run)
    name_entry = (profile.get("company_identity") or {}).get("name") or {}
    name = name_entry.get("value") or domain or "Company"
    if isinstance(name, list):
        name = ", ".join(_items(name))

    head = (
        "<header><h1>" + esc(name) + '<span class="tag">Website-sourced profile</span></h1>'
        '<p class="sub">' + esc(domain) + "</p>"
        '<p class="note">A company website is a self-reported source. Facts below are what the company '
        "states about itself and are not independently verified.</p></header>"
    )
    banner = ""
    status = run.get("crawl_status")
    if status and status != "ok":
        # B-87: a run whose site could not be read (B-83 unreachable, B-84 blocked, B-86 redirected)
        # says so first, instead of showing an empty profile with no reason.
        headline = {
            "unreachable": "Site unreachable",
            "blocked": "Site blocked the crawler",
            "redirected": "Site redirects to another domain",
        }.get(status, "Site could not be read")
        detail = run.get("crawl_status_reason") or ""
        if status == "redirected" and run.get("final_url") and run.get("final_url") not in detail:
            detail = (detail + " " if detail else "") + "Final URL: " + str(run.get("final_url"))
        banner += (
            '<p class="banner" role="status">' + esc(headline) + " ("
            + esc(run.get("crawl_error_code") or status) + "). "
            + (esc(detail) + " " if detail else "")
            + "No facts were extracted from this site.</p>"
        )
    if run.get("limit_reached"):
        banner += (
            '<p class="banner" role="status">Partial profile: a crawl or token limit was reached, '
            "so some pages may not have been read.</p>"
        )
    if run.get("non_english"):
        # B-85 (PRD Section 9, AC-05): flag only; the facts below were still extracted.
        banner += (
            '<p class="banner" role="status">Non-English site (detected language: '
            + esc(run.get("site_language") or "non-en")
            + "). Facts were still extracted, but this site is outside the English-language "
            "supported-website definition, so expect gaps.</p>"
        )

    sections: List[str] = []
    for key, title, anchor in SECTIONS:
        group = profile.get(key) or {}
        facts: List[str] = []
        for short, entry in group.items():
            if short == "announcements" or not isinstance(entry, dict):
                continue
            facts.append(_fact(_label(short), entry, lookup.get(str(entry.get("claim_id")))))
        if key == "evidence_traction":
            anns = group.get("announcements") or []
            if anns:
                facts.append('<h3 class="muted">Dated company-reported announcements</h3>')
                facts.extend(_announcement(a) for a in anns)
        if facts:
            sections.append(_section(title, anchor, "".join(facts)))

    sections.append(_section("Gaps and conflicts", "gaps", _gaps(profile.get("gaps_conflicts") or [], lookup)))
    if claims:
        coverage = profile.get("coverage") or {}
        sections.append(_section("Pages used as evidence", "pages",
                                 charts.pages_svg(charts.page_field_counts(run), coverage.get("pages_scanned"))))
    sections.append(_section("Evidence ledger", "ledger", _ledger(claims)))
    if news is not None:
        sections.append(_news_section(news))

    foot = (
        "<footer>Rendered from saved JSON"
        + (" (" + esc(source_name) + ")" if source_name else "")
        + ", schema " + esc(run.get("schema_version") or "unknown")
        + ". No model call was made to build this page.</footer>"
    )
    coverage = profile.get("coverage") or {}
    page = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>" + esc(name) + " - Website-sourced profile</title><style>" + CSS + "</style></head><body><main>"
        + _cover(str(name), domain, coverage.get("last_retrieved_at")) + head + banner + _strip(coverage)
        + charts.coverage_svg(charts.coverage_counts(run)) + "".join(sections) + foot
        + "</main></body></html>"
    )
    if open_drawers:
        # The literal below is only ever written by _drawer: third-party text is escaped (quotes too).
        page = page.replace('<details class="drawer">', '<details class="drawer" open>')
    return page


def _load(run_path: Any) -> Tuple[Path, Dict[str, Any], Optional[Dict[str, Any]]]:
    src = Path(run_path)
    run = json.loads(src.read_text(encoding="utf-8"))
    news = None
    news_path = src.parent.parent / "news" / src.name
    if news_path.is_file():
        try:
            news = json.loads(news_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            news = None   # an unreadable news file never stops the profile page
    return src, run, news


def render_file(run_path: Any, out_path: Any = None) -> Path:
    """Read a run JSON file and write its HTML page. Default output: data/pages/<stem>.html next
    to the run's data/ folder (created if missing). Returns the written path. B-105: when
    data/news/<same name>.json exists next to the run's data/ folder, its news section is added."""
    src, run, news = _load(run_path)
    if out_path is None:
        out = src.parent.parent / "pages" / (src.stem + ".html")
    else:
        out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_profile_html(run, source_name=src.name, news=news), encoding="utf-8")
    return out


def render_pdf_file(run_path: Any, out_path: Any = None, writer: Any = None) -> Tuple[Path, int]:
    """B-108: print the same page (news included, drawers open) to a PDF. Default output:
    data/pages/<stem>.pdf. `writer(html, path) -> page count` defaults to wi/render/pdf.py
    (Playwright); tests pass their own. Returns (path, page count)."""
    src, run, news = _load(run_path)
    out = Path(out_path) if out_path is not None else src.parent.parent / "pages" / (src.stem + ".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    if writer is None:
        from wi.render.pdf import write_pdf
        writer = write_pdf
    pages = writer(render_profile_html(run, source_name=src.name, news=news, open_drawers=True), out)
    return out, pages
