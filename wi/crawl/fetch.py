"""Static page fetching, robots.txt compliance, and same-domain link discovery
(PRD Section 7, EXT-01/EXT-02). No JavaScript rendering here -- this is the
httpx-only baseline. The Playwright fallback (CRL-04 -- corrected 2026-09-26; a
previous version of this docstring mis-cited "EXT-05", which is actually the
unrelated "keep provider/model configurable" requirement) lives in
wi/crawl/js_fallback.py, used only when this path shows insufficient content.

Crawl ordering / page-discovery relevance (Week 2, decided 2026-09-25, closes the CRL-01
gap -- "principal relevant pages are found on at least 80% of development websites without
uncontrolled crawling"): crawl_site() used to be strictly FIFO -- pages were fetched in
whatever order links were discovered in, breadth-first by depth only. That meant on any site
where max_pages is a binding constraint (a real marketing site with a blog, docs, or dozens
of low-value pages), a pricing or customers page could simply never get fetched just because
it happened to sit later in the HTML (a footer link, say) or one level deeper than pages of
no real interest -- even though the homepage linked to it. The only "priority" concept that
existed anywhere in the codebase, is_priority_url() in wi/crawl/clean.py, only ever affected
the character cap used during *cleaning*, never which pages got *crawled* or in what order.

The queue is now a priority queue (heapq), not a plain list, ordered by
(priority_rank, depth, discovery_order):
  - priority_rank: 0 for a URL matching config.yaml's crawl.priority_url_keywords (reusing
    is_priority_url() from wi/crawl/clean.py -- one source of truth, not a second list to
    keep in sync), 1 otherwise.
  - depth: shallower pages still win within the same priority tier, so this stays a
    controlled, homepage-outward crawl, not a free-for-all re-ordering.
  - discovery_order: a plain insertion counter, so ties are deterministic (document order)
    instead of depending on heap/dict iteration order.
This only changes the ORDER pages are dequeued in. max_pages, max_depth, total_budget_s,
rate_limit_rps and robots.txt compliance are all unchanged -- when there's room to fetch
everything discovered, behaviour is identical to before. A config with no
priority_url_keywords set (or an empty list) falls back to today's plain breadth-first order,
so this is backward compatible with any config.yaml written before this change.

Duplicate-page dedup (Week 2, decided 2026-09-26, closes CLN-01 / B-15): crawl_site()'s `seen`
set used to compare raw discovered URL strings, so "/products" and "/products/" -- the exact
kind of duplicate CLN-01 names -- were two different strings and both got queued and fetched
as separate pages. Two fixes, matching CLN-01's own wording ("normalised URL and content
hash"):
  1. _normalize_url() now collapses a trailing slash before a URL ever reaches `seen`, applied
     consistently to both start_url and every discovered link, so the URL-level duplicate is
     never even queued twice.
  2. Because two DIFFERENT normalised URLs can still serve byte-identical content (a mirror
     path, a print-friendly copy), crawl_site() also hashes each fetched page's body
     (content_hash(), shared with the run cache in wi/crawl/cache.py) and drops a page whose
     hash matches one already kept, recording it in CrawlResult.skipped_as_duplicate rather
     than silently discarding it.
Neither check touches max_pages, max_depth or robots.txt handling; a duplicate page still
costs one fetch (we can't know it's a duplicate before fetching it) but no longer counts
against the pages budget or reaches the pipeline twice.

JS-only page fallback (Week 2, decided 2026-09-26, closes CRL-04 / B-16): crawl_site() takes
an optional `js_renderer` callable. When one is given and a fetched page's own static content
is too thin (wi.crawl.js_fallback.needs_fallback -- the same "insufficient content" trigger
CRL-04 names), the renderer is called and, if it succeeds, its HTML replaces the static
fetch's for that page, with FetchResult.js_rendered=True as the flag CRL-04 also asks for.
No `js_renderer` (the default) means the fallback is fully inert -- reproducing the exact old
static-only behaviour, and never importing or requiring Playwright to be installed.

Other-language copies (decided 2026-10-06, B-60, found live on snowflake.com): the start URL
https://www.snowflake.com/en/ links to /ja/, /ko/, /pt_br/, /de/, /fr/, /es/ and /it/ copies of
/pricing-options. Those matched the priority keywords, so they jumped the queue and took 7 of
the 40 page slots, plus their tokens, for no new facts -- and the PRD's "supported website" is
English-language. When the START URL itself begins with an English locale segment (/en, /en-us,
/en_gb ...), the site is evidently organised by locale prefix, so any discovered link whose first
path segment is a NON-English language code is skipped and recorded in
CrawlResult.skipped_as_other_locale. Deliberately conservative: a start URL with no locale prefix
changes nothing (a top-level /it/ or /hr/ there could be IT or HR content, not Italian or
Croatian), and English variants (/en-gb) are kept. Config: crawl.skip_other_locales (default
true) turns it off.

B-69 (2026-10-06): the same copies were still fetched when the start URL was the bare domain
(https://www.snowflake.com/ -- the form people actually type): 10 of its 40 pages were /ja/ /ko/
/pt_br/ /de/ /fr/ /es/ /it/ copies of the pricing and customers pages, and the crawl never reached
an about or partners page. A site now also counts as organised by an English locale prefix when the
START PAGE ITSELF links to at least one /en... URL; from then on non-English locale links are
skipped exactly as above. A start page with no /en links changes nothing.
"""
from __future__ import annotations

import hashlib
import heapq
import itertools
import re
import time
import urllib.robotparser
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx
from bs4 import BeautifulSoup

from wi.crawl.clean import _title, is_priority_url, main_text
from wi.crawl.js_fallback import DEFAULT_MIN_TEXT_CHARS, DEFAULT_TIMEOUT_S, needs_fallback

USER_AGENT = "CompanyWebsiteIntelBot/0.1 (+https://samkhya.ai/bot)"


@dataclass
class FetchResult:
    url: str
    status: str                 # "ok" | "error"
    status_code: Optional[int] = None
    html: Optional[str] = None
    elapsed_s: float = 0.0
    error: Optional[str] = None
    error_code: Optional[str] = None    # e.g. "REDIRECT_LIMIT_EXCEEDED" (B-12); None for other
                                         # HTTP errors -- see fetch_page's docstring
    truncated: bool = False
    js_rendered: bool = False   # True when the JS fallback replaced the static fetch (B-16)
    content_hash: Optional[str] = None  # sha256 of the fetched body, set on success; crawl_site
                                         # replaces it with the cleaned-text hash (B-75) for dedup
    # B-76: the URL that was asked for, when redirects ended somewhere else. `url` is then the
    # final resolved URL (PRD Section 9: "Record the final resolved URL as the source").
    requested_url: Optional[str] = None
    # The final address exactly as the server gave it (trailing slash kept): the base relative
    # links resolve against. `url` drops the trailing slash, which would move "board" on
    # /company/team/ up a level to /company/board.
    link_base: Optional[str] = None


@dataclass
class CrawlResult:
    start_url: str
    pages: List[FetchResult] = field(default_factory=list)
    skipped_by_robots: List[str] = field(default_factory=list)
    # URLs whose content duplicated a page already in `pages` (CLN-01's content-hash half --
    # the normalised-URL half is handled earlier, by never queuing the duplicate URL at all;
    # this catches the remaining case where two DIFFERENT normalised URLs serve identical
    # content, e.g. a mirror path or a print-friendly copy of the same page).
    skipped_as_duplicate: List[str] = field(default_factory=list)
    # Links not queued because they point at another-language copy of the site (B-60).
    skipped_as_other_locale: List[str] = field(default_factory=list)
    # Links not queued because they point at a login / sign-in / SSO page (B-78).
    skipped_as_auth: List[str] = field(default_factory=list)
    budget_exhausted: bool = False  # the total time budget (crawl.total_budget_s) ran out
    # B-73: the crawl stopped at crawl.max_pages with URLs still queued, so some discovered pages
    # were never fetched. Separate from budget_exhausted, which only ever meant the time budget.
    page_cap_reached: bool = False


def crawl_diagnostics(result: CrawlResult) -> dict:
    """Everything run_site.py prints about a crawl (which pages were fetched or failed and
    why, what got skipped and how), reshaped for persisting into the run's output JSON.

    Added 2026-09-27 during the crawl-coverage-misses investigation (see PROGRESS.md): this
    information already existed on every CrawlResult, but run_site.py only ever printed it to
    the console and never wrote it to data/runs/<slug>.json -- so a "miss" in eval/baseline.py
    could mean the page genuinely was never crawled, the crawl fetched it but errored (bot
    block, timeout, unsupported content type), or the crawl succeeded and the model simply
    didn't report the field, and telling those apart required either watching the console at
    the exact moment of a fresh run or re-running the site from scratch. Persisting this makes
    every past and future run individually diagnosable after the fact, the same reasoning
    B-30/B-34 already applied to a claim's own source_url and the run-level cache fingerprint."""
    return {
        "pages": [
            {
                "url": p.url,
                "status": p.status,
                "status_code": p.status_code,
                "error": p.error,
                "error_code": p.error_code,
                "truncated": p.truncated,
                "js_rendered": p.js_rendered,
                "requested_url": p.requested_url,  # B-76, None unless redirected
            }
            for p in result.pages
        ],
        "skipped_by_robots": result.skipped_by_robots,
        "skipped_as_duplicate": result.skipped_as_duplicate,
        "skipped_as_other_locale": result.skipped_as_other_locale,
        "skipped_as_auth": result.skipped_as_auth,  # B-78
        "budget_exhausted": result.budget_exhausted,
        "page_cap_reached": result.page_cap_reached,  # B-73
    }


def content_hash(html: str) -> str:
    """sha256 of the fetched body. Shared with wi/crawl/cache.py so the crawl's own
    duplicate-content check and the run cache's fingerprint are computed the same way --
    one source of truth, not two hashes that could drift apart."""
    return hashlib.sha256(html.encode("utf-8", errors="replace")).hexdigest()


class RobotsGate:
    """Wraps urllib.robotparser per-domain, fetched once and cached for the run.

    Known limitation: Python's robotparser matches rules in file order for the
    matching user-agent group, not by longest-path specificity (the real-world
    convention, and the one that mattered when we reviewed a benchmark site
    whose Allow was meant to carve an exception out of a broader Disallow).
    Most robots.txt files don't depend on that ordering, but any site added to
    eval/benchmark_sites.md should still be spot-checked by a human, not just
    this parser.
    """

    def __init__(self, client: httpx.Client):
        self._client = client
        self._parsers: Dict[str, urllib.robotparser.RobotFileParser] = {}

    def _parser_for(self, url: str) -> urllib.robotparser.RobotFileParser:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._parsers:
            rp = urllib.robotparser.RobotFileParser()
            robots_url = urljoin(origin, "/robots.txt")
            try:
                resp = self._client.get(robots_url, timeout=10)
                # A 200 is parsed; any other status (404, 403, 5xx) is treated as
                # allow-all, per the standard robots.txt convention.
                rp.parse(resp.text.splitlines() if resp.status_code == 200 else [])
            except httpx.HTTPError:
                rp.parse([])
            self._parsers[origin] = rp
        return self._parsers[origin]

    def can_fetch(self, url: str) -> bool:
        return self._parser_for(url).can_fetch(USER_AGENT, url)

    def crawl_delay(self, url: str) -> Optional[float]:
        delay = self._parser_for(url).crawl_delay(USER_AGENT)
        return float(delay) if delay else None


def dedup_hash(url: str, html: str) -> str:
    """B-75: the hash crawl_site() uses to spot a page it already has. Two fetches of one page
    (a redirect target reached from several URLs, an http and an https link) carry different
    nonces and tokens in their raw HTML, so a raw-HTML hash never matched them: on freshworks.com
    nine URLs that redirect to four pages were all kept. The page's <title> plus its main cleaned
    text (wi/crawl/clean.py main_text, before any cap) is the same for both. A page with no text
    at all (an empty JS shell) falls back to the raw-HTML hash, so two different empty shells are
    not merged into one."""
    text = main_text(url, html)
    if not text.strip():
        return content_hash(html)
    return content_hash(f"{_title(html) or ''}\n{text}")


# B-78: login / sign-in / single-sign-on addresses. A host whose first label is one of these
# (login.example.com) or a path with one of these as a whole segment (/signin, /sso/start) is an
# account screen, never company information. Whole segments only, so /authors or /logins-guide
# are kept.
_AUTH_HOST_LABELS = frozenset({"login", "signin", "sso", "auth"})
_AUTH_PATH_SEGMENTS = frozenset({"login", "log-in", "signin", "sign-in", "sso", "auth", "oauth",
                                 "logout", "log-out"})


def is_auth_url(url: str) -> bool:
    """True for a login / sign-in / SSO page (B-78), which the crawl skips before fetching."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if host.split(".", 1)[0] in _AUTH_HOST_LABELS:
        return True
    return any(seg in _AUTH_PATH_SEGMENTS for seg in parts.path.lower().split("/") if seg)


def _same_domain(url: str, approved_domains: List[str]) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in approved_domains)


def normalize_url(url: str) -> str:
    """Normalises a URL for dedup purposes (CLN-01): strips fragment and query, and collapses
    a trailing slash so '/products' and '/products/' are treated as the same page. The bare
    root path '/' is left alone. Applied both to discovered links and to the crawl's own
    start_url so every comparison in crawl_site's `seen` set uses the same form.

    Promoted from a private `_normalize_url` (decided 2026-09-26) so wi/extract/pipeline.py can
    reuse the exact same normalisation when matching a claim's `source_url` back to the crawled
    page it came from -- one source of truth for "what counts as the same URL", not two
    functions that could drift apart. `_normalize_url` stays as an alias below so the existing
    direct-import tests in tests/test_fetch.py don't need to change.
    """
    parts = urlsplit(url)
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    return urlunsplit((parts.scheme, parts.netloc, path, "", ""))


_normalize_url = normalize_url  # backward-compatible alias, see normalize_url's docstring


# ISO 639-1 language codes. A first path segment counts as a locale only if its language part is
# in this set, so ordinary two-letter segments such as /us, /ai or /go are never mistaken for one.
_LANGUAGE_CODES = frozenset(
    "aa ab af ak am an ar as av ay az ba be bg bh bi bm bn bo br bs ca ce ch co cr cs cu cv cy da "
    "de dv dz ee el en eo es et eu fa ff fi fj fo fr fy ga gd gl gn gu gv ha he hi ho hr ht hu hy "
    "hz ia id ie ig ii ik io is it iu ja jv ka kg ki kj kk kl km kn ko kr ks ku kv kw ky la lb lg "
    "li ln lo lt lu lv mg mh mi mk ml mn mr ms mt my na nb nd ne ng nl nn no nr nv ny oc oj om or "
    "os pa pi pl ps pt qu rm rn ro ru rw sa sc sd se sg si sk sl sm sn so sq sr ss st su sv sw ta "
    "te tg th ti tk tl tn to tr ts tt tw ty ug uk ur uz ve vi vo wa wo xh yi yo za zh zu".split()
)
_LOCALE_SEGMENT = re.compile(r"^([a-z]{2})(?:[-_][a-z0-9]{2,4})?$", re.IGNORECASE)


def locale_language(url: str) -> Optional[str]:
    """The language code of the URL's first path segment when that segment is a locale such as
    'en', 'ja', 'pt_br' or 'zh-CN' (lowercased language part only); None when the first segment
    is not a locale. See the module docstring's B-60 section."""
    segments = [s for s in urlsplit(url).path.split("/") if s]
    if not segments:
        return None
    m = _LOCALE_SEGMENT.match(segments[0])
    if m and m.group(1).lower() in _LANGUAGE_CODES:
        return m.group(1).lower()
    return None


def is_other_locale_url(url: str, start_url: str) -> bool:
    """True when start_url sits under an English locale prefix and `url` sits under a different,
    non-English one (B-60). False in every other case, including when start_url has no locale."""
    if locale_language(start_url) != "en":
        return False
    lang = locale_language(url)
    return lang is not None and lang != "en"


def is_non_english_locale_url(url: str) -> bool:
    """True when `url` sits under a non-English locale prefix (/ja/, /pt_br/, ...). Used once a
    site is known to be organised by English locale prefix (B-60, B-69)."""
    lang = locale_language(url)
    return lang is not None and lang != "en"


def extract_links(html: str, base_url: str, approved_domains: List[str]) -> List[str]:
    """Same-domain links only, in document order, de-duplicated, fragments and query stripped,
    trailing slash collapsed (see _normalize_url)."""
    soup = BeautifulSoup(html, "lxml")
    links: List[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https"):
            continue
        normalised = _normalize_url(absolute)
        if _same_domain(normalised, approved_domains):
            links.append(normalised)

    seen = set()
    out = []
    for link in links:
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out


def _is_crawlable_content_type(content_type: str) -> bool:
    """True for a response this crawler can meaningfully treat as an HTML/text page.

    Added 2026-09-26 after a real bajajauto.com run: its owner's-manual pages link straight
    to CDN-hosted PDFs (cdn.bajajauto.com/.../owners-manual-pdf/*.pdf). Before this check,
    fetch_page had no idea those weren't HTML -- it decoded the PDF's raw bytes as text,
    clean_page ran BeautifulSoup over the resulting garbage, and the "cleaned" output (mostly
    binary noise, still capped at 16,000 chars each) got counted as real page content. On
    that one run, 13 such PDFs ate more than half the 25-page crawl budget AND pushed the
    LLM prompt to 158,814 tokens against gpt-4o-mini's 128,000 limit, crashing the whole run
    with an unhandled openai.BadRequestError and no output file at all.

    Deliberately a blocklist-by-default-allow, not the reverse: an empty or missing
    content-type header (some misconfigured servers, and every existing test fixture that
    builds an httpx.Response without setting one) is treated as crawlable, matching the
    crawler's old behaviour. "text/plain" is allowed too -- some real sites mislabel HTML
    that way, and rejecting it would have no benefit. Only content whose main type isn't
    text/* and isn't (x)html/xml -- PDFs, images, archives, office documents, video, audio --
    is treated as unsupported.
    """
    if not content_type:
        return True
    main_type = content_type.split(";", 1)[0].strip().lower()
    if main_type.startswith("text/"):
        return True
    return main_type in ("application/xhtml+xml", "application/xml")


def fetch_page(client: httpx.Client, url: str, max_raw_bytes: int, timeout_s: float) -> FetchResult:
    """One GET, capped at max_raw_bytes (streamed, not loaded whole then truncated).

    Redirect-cap reporting (Week 2, decided 2026-09-26, closes B-12): the client is
    constructed elsewhere with max_redirects=config.crawl.max_redirects, so httpx itself
    already raises httpx.TooManyRedirects once a chain exceeds the cap -- that part worked
    before. What didn't: this function's own `except httpx.HTTPError` caught it same as any
    other network failure, so a capped-out redirect chain and, say, a DNS failure were both
    reported as an identical generic status="error" with no way to tell them apart. B-12 asks
    for the cap specifically to be reported, so TooManyRedirects (a subclass of HTTPError) is
    now caught first and given its own error_code, while every other HTTPError still falls
    through to the unchanged generic path below it.

    Content-type gate (decided 2026-09-26, see _is_crawlable_content_type): a non-HTML/text
    response (a linked PDF, image, etc.) is reported as status="error" with error_code
    "UNSUPPORTED_CONTENT_TYPE" before any bytes are read, the same way a redirect-limit or
    HTTP error is reported -- it still costs one fetch against the page budget (we can't know
    the content-type before making the request) but is never decoded as text or handed to the
    HTML cleaner.
    """
    start = time.monotonic()
    try:
        with client.stream("GET", url, timeout=timeout_s, headers={"User-Agent": USER_AGENT}) as resp:
            if resp.status_code >= 400:
                return FetchResult(url=url, status="error", status_code=resp.status_code,
                                    elapsed_s=time.monotonic() - start,
                                    error=f"HTTP {resp.status_code}")
            content_type = resp.headers.get("content-type", "")
            if not _is_crawlable_content_type(content_type):
                return FetchResult(url=url, status="error", status_code=resp.status_code,
                                    error_code="UNSUPPORTED_CONTENT_TYPE",
                                    elapsed_s=time.monotonic() - start,
                                    error=f"Unsupported content-type: {content_type!r}")
            chunks: List[bytes] = []
            total = 0
            truncated = False
            for chunk in resp.iter_bytes():
                total += len(chunk)
                if total > max_raw_bytes:
                    truncated = True
                    break
                chunks.append(chunk)
            body = b"".join(chunks)
            html = body.decode(resp.encoding or "utf-8", errors="replace")
            # B-76: after redirects, the page's source is where the chain ended, not where it
            # started. Normalised the same way as every other URL in the crawl.
            final_url = normalize_url(str(resp.url))
            return FetchResult(url=final_url, status="ok", status_code=resp.status_code,
                                html=html, elapsed_s=time.monotonic() - start,
                                truncated=truncated, content_hash=content_hash(html),
                                requested_url=url if final_url != url else None,
                                link_base=str(resp.url))
    except httpx.TooManyRedirects as e:
        return FetchResult(url=url, status="error", error_code="REDIRECT_LIMIT_EXCEEDED",
                            elapsed_s=time.monotonic() - start,
                            error=f"Redirect limit exceeded: {e}")
    except httpx.HTTPError as e:
        return FetchResult(url=url, status="error", elapsed_s=time.monotonic() - start, error=str(e))


def _priority_rank(url: str, keywords: List[str]) -> int:
    """0 if this URL should be fetched ahead of same-depth non-matching pages, else 1. See
    the module docstring for why (Week 2 page-discovery / CRL-01)."""
    return 0 if keywords and is_priority_url(url, keywords) else 1


def crawl_site(start_url: str, approved_domains: List[str], config: dict,
               client: Optional[httpx.Client] = None,
               js_renderer: Optional[Callable[[str, float], Optional[str]]] = None) -> CrawlResult:
    """Breadth-first crawl within config['crawl'] limits, with pages matching
    crawl.priority_url_keywords fetched ahead of other pages at the same depth (see module
    docstring). Falls back to plain breadth-first order when priority_url_keywords is
    missing or empty.

    `client` is injectable so tests can pass an httpx.Client(transport=MockTransport(...))
    instead of hitting the network. `js_renderer` is injectable the same way, for the CRL-04
    JS-only fallback (see module docstring) -- tests pass a fake renderer, run_site.py passes
    wi.crawl.js_fallback.render_with_playwright when crawl.js_fallback_enabled is true.
    """
    cfg = config["crawl"]
    keywords = cfg.get("priority_url_keywords", [])
    start_url = _normalize_url(start_url)
    result = CrawlResult(start_url=start_url)
    deadline = time.monotonic() + cfg["total_budget_s"]
    min_interval = 1.0 / cfg["rate_limit_rps"] if cfg.get("rate_limit_rps") else 0.0
    skip_other_locales = cfg.get("skip_other_locales", True)  # B-60, see module docstring
    skip_auth_pages = cfg.get("skip_auth_pages", True)        # B-78, see is_auth_url

    owns_client = client is None
    client = client or httpx.Client(follow_redirects=True, max_redirects=cfg["max_redirects"])
    try:
        robots = RobotsGate(client)
        counter = itertools.count()
        # heap entries: (priority_rank, depth, discovery_order, url) -- heapq is a min-heap,
        # so lower priority_rank (0 = matches priority_url_keywords) pops first; depth and
        # discovery_order keep it breadth-first and document-ordered within each tier.
        queue: List[tuple] = []
        heapq.heappush(queue, (_priority_rank(start_url, keywords), 0, next(counter), start_url))
        seen = {start_url}          # normalised URLs already queued or fetched (CLN-01, URL half)
        content_hashes: set = set()  # content hashes of pages already kept (CLN-01, content half)
        kept_urls: set = set()       # final URLs of pages already kept (B-76)
        last_request = 0.0

        # B-65 (2026-10-06): max_pages counts pages that were actually fetched, not attempts. A page
        # that 404s or 403s used to use up a slot like any other: loom.com spent 18 of its 40 slots
        # on dead links (/trust, /industries/*, /partners all 404), typeform.com 6 on help-centre
        # pages that answer 403, so the model saw 22 and 34 pages instead of 40. Failed pages are
        # still recorded in result.pages (the diagnostics show them); they just don't count against
        # the page budget -- but only the first max_failed_pages of them (default 20); after that a failure
        # counts like any other attempt, so a site that answers every link with an error cannot keep the
        # crawl going (the total time budget still applies too).
        max_failed = cfg.get("max_failed_pages", 20)
        failed_count = 0
        # B-60 / B-69: True once the site is known to be organised by an English locale prefix.
        english_locale_site = locale_language(start_url) == "en"

        while queue and (len(result.pages) - failed_count) < cfg["max_pages"]:
            if time.monotonic() >= deadline:
                result.budget_exhausted = True
                break

            _rank, depth, _order, url = heapq.heappop(queue)

            if cfg["respect_robots"] and not robots.can_fetch(url):
                result.skipped_by_robots.append(url)
                continue

            wait = min_interval - (time.monotonic() - last_request)
            if wait > 0:
                time.sleep(wait)
            last_request = time.monotonic()

            page = fetch_page(client, url, cfg["max_raw_bytes"], cfg["request_timeout_s"])

            if (page.status == "ok" and js_renderer is not None
                    and needs_fallback(page.html, cfg.get("js_fallback_min_text_chars",
                                                            DEFAULT_MIN_TEXT_CHARS))):
                rendered_html = js_renderer(page.url, cfg.get("js_fallback_timeout_s", DEFAULT_TIMEOUT_S))
                if rendered_html:
                    page = FetchResult(
                        url=page.url, status="ok", status_code=page.status_code,
                        html=rendered_html, elapsed_s=page.elapsed_s,
                        content_hash=content_hash(rendered_html), js_rendered=True,
                        requested_url=page.requested_url, link_base=page.link_base,
                    )
                # A failed render (rendered_html is None) leaves the original static `page`
                # in place -- degrade gracefully, never lose a page just because the
                # fallback itself failed.

            # Two different normalised URLs can still serve the same page (a mirror path, a
            # print-friendly copy, several URLs that redirect to one page). The URL-level `seen`
            # set above can't catch that -- only the fetched content can. Keep the first copy,
            # drop the rest. B-75: compared on cleaned text, not raw HTML (see dedup_hash).
            if page.status == "ok" and page.html:
                page.content_hash = dedup_hash(page.url, page.html)
            # B-76: a redirect that lands on a page already kept is a duplicate by address alone.
            redirected_to_kept = page.requested_url is not None and page.url in kept_urls
            if redirected_to_kept or (
                    page.status == "ok" and page.content_hash and page.content_hash in content_hashes):
                result.skipped_as_duplicate.append(url)
            else:
                if page.status == "ok" and page.content_hash:
                    content_hashes.add(page.content_hash)
                kept_urls.add(page.url)
                seen.add(page.url)       # B-76: a link to the final URL is not queued again
                result.pages.append(page)
                if page.status != "ok" and failed_count < max_failed:
                    failed_count += 1

            if page.status == "ok" and page.html and depth < cfg["max_depth"]:
                # B-76: relative links resolve against where the page actually is.
                page_links = extract_links(page.html, page.link_base or page.url, approved_domains)
                if (skip_other_locales and depth == 0 and not english_locale_site
                        and any(locale_language(l) == "en" for l in page_links)):
                    english_locale_site = True      # B-69: the start page itself links to /en...
                for link in page_links:
                    if link not in seen:
                        seen.add(link)
                        if skip_other_locales and english_locale_site and is_non_english_locale_url(link):
                            result.skipped_as_other_locale.append(link)
                            continue
                        if skip_auth_pages and is_auth_url(link):
                            # B-78: found on freshworks.com, where login.freshworks.com/email-login
                            # took a page slot and a Playwright render for a sign-in form.
                            result.skipped_as_auth.append(link)
                            continue
                        heapq.heappush(
                            queue,
                            (_priority_rank(link, keywords), depth + 1, next(counter), link),
                        )

        # B-73: the loop above also exits when the page budget is full. If URLs are still queued
        # at that point, the cap (not the site running out of pages) ended the crawl.
        if queue and (len(result.pages) - failed_count) >= cfg["max_pages"]:
            result.page_cap_reached = True
    finally:
        if owns_client:
            client.close()

    return result
