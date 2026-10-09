# DRAFT: Known limitations (for the handoff docs)

Status as of 2026-10-09, code at `EXTRACTION_LOGIC_VERSION` 25, `prompt_version` 16, Jev on.

## Accuracy

- **Dev headline is about 68%, against an 80% target (AC-02).** The post-B-81 3-round mean is
  67.6% (69.3 / 66.7 / 66.7); the build before B-75 measured 68.9%. The 80% target applies to
  held-out sites, which have not been measured on this code (see below).
- **Run-to-run noise is about ±3 points.** The model is called at temperature 0.1, and Jev's
  decisions move with it (Calendly's `sales_motion` came out at probability 0.71 to 0.76, just
  under the 0.8 threshold). Judge a change on 3 or more `--no-cache` runs; a single run cannot show a
  difference of 3 points or less.
- **About a third of dev errors trace to the labels, not the system.** See
  `docs/ERROR_REVIEW.md`: 26 of 73 non-right verdicts are label granularity or format, two valid
  wordings on the site, or a `not_found` label where the run found gate-verified text. The dev labels
  were made by hand by Uttam on 2026-09-28, from the sites' screenshots and pages, so text on a
  page they did not cover can be missing from them; they have not had a second independent check.

## Evaluation sets

- **The old held-out set is contaminated.** After the held-out sites were first run and scored
  (2026-09-27), fixes B-39 to B-54 were made using their failures; every one of those rows except
  B-46 names held-out sites, and B-46 (semantic-judge widening) followed the same results. B-51
  re-labelled one field, `customers.segments`, in all 10 held-out label files after comparing them
  with the live sites. (B-37 and B-38 came from the dev set, before the first held-out run.) A score
  on these sites is no longer a held-out measurement. A fresh set must be labelled by hand before
  any run, the code tagged, and the set run once.
- **The dev set is saturated.** Calendly, Loom, Typeform, Notion and SimpleStores have been used to
  find and check every recent fix, so the dev headline overstates performance on unseen sites.
- **Peeked sites** (run outside the dev set, so excluded from the fresh held-out set) are listed in
  `eval/peeked_sites.txt`.

## Latency and cost

- **p50 latency misses its target.** Post-B-81: p50 87 s against 60 s; p95 182 s against 180 s,
  just over because of one 136 s model call (the other rounds' p95 were 132 to 134 s). The crawl is
  most of the time (69 s per site on average, against 24 s for the model call), set by
  `rate_limit_rps: 1` and `max_pages: 40`;
  SimpleStores also hits the 120 s `total_budget_s` after 14 to 16 pages. Meeting 60 s needs a
  change to those Section 13 parameters, which needs approval.
- **Cost is well inside its targets:** mean $0.0062 and p95 $0.0089 per site against $0.10 and
  $0.25 (gpt-4o-mini list prices; Jev adds about $0.0001).

## Field-specific

- **`pricing.sales_motion` misses demo-led cues worded "Book a demo" or "Get a demo".** On
  freshworks.com the pricing page's own button block lists "Book a demo", "Get a demo" and
  "Contact us" next to "Start for free", yet both runs answered "Self-serve signup" and Jev answered
  "unclear" (p 0.87 to 0.89, not applied). Prompt rule 14 names "Request a Demo", "Contact Sales",
  "Talk to Sales", "Get a Quote" and "Get in Touch", but not these two phrasings. Whether that gap is
  the cause, or the model simply stopped at the first cue (which rule 17 already warns against), is
  not confirmed. No change has been made.
- **`products.delivery_model` scoring does not reward the B-81 trim.** B-81 removes detail the
  quote does not mention (for example "software (web app)" becomes "software" in 11 of 15 dev runs),
  so the value is better supported, but the field's score stayed at 40%: two dev labels are long
  free-text descriptions ("Digital software delivered online with a downloadable app") and Calendly's
  label is `not_found`, so neither the trimmed nor the untrimmed value matches.
- **`products.names` bare-label guard also rejects correct names.** When the only quote available
  for a product is its own name (Notion "Notion AI", Typeform "Growth Flow"), the guard that stops
  menu labels being reported as products rejects the real product too.

## Crawl

- **B-80 drops redirects that leave the approved domain.** A page whose redirect ends on another
  domain is dropped and recorded in `dropped_after_redirect`. Loom now redirects 15 of its links
  (`/security`, `/signup`, blog posts) to atlassian.com, so those pages are no longer read; Loom's
  crawl fell from 60 fetches to 25 kept pages. Company information that has moved to a parent
  company's domain is not collected. (A start URL that itself redirects off the domain is reported
  as `crawl_status: "redirected"`, B-86.)
- **Login check is links only.** B-78 skips login and SSO links before fetching, but a normal link
  that redirects to a login page is still fetched (it is then dropped only if it leaves the
  approved domains, B-80).
- **Pages a JS-only site renders after load** are read only through the Playwright fallback, when
  the static text is under the threshold.

## Error handling (PRD Section 9, B-83 to B-87)

Unreachable, blocked and off-domain-redirect start pages are reported with `crawl_status` and an
error code, and the rendered page shows a banner for them (B-83, B-84, B-86, B-87). What is left:

- **No backoff for a 429 after the start page.** Only the start URL waits out a 429 (B-84). A later
  page that answers 429 is recorded in `blocked_pages` and skipped, with no wait or retry, so a
  rate-limited site can lose pages that a short backoff would have recovered (Section 9 asks for
  exponential backoff within the time budget).
- **No `TIMEOUT` error code.** A page that times out is skipped, recorded with the exception text and
  the crawl continues (Section 9's "skip the page, log it, continue"), but it has no distinct
  `error_code`, so timeouts are counted only by reading the error text. A start page that times out
  is retried and then reported as `SITE_UNREACHABLE` (B-83).
- **A start URL that redirects within the domain to a robots-disallowed path** is dropped by B-80,
  and the run ends with 0 pages and `crawl_status: "ok"` instead of `blocked` /
  `ROBOTS_DISALLOWED`. No model call is made, but a missing `OPENAI_API_KEY` still stops the run.
- **Jev has no retry on a rate limit.** Any Jev HTTP error, including 429, leaves the extraction
  result unchanged and is recorded in the run JSON's `classifier.error`; the decision is simply not
  made for that run. (The OpenAI client retries its own calls twice by default; that is the SDK's
  behaviour, not this project's code.)
- **The bot-challenge detector (B-84) has not been checked against real crawled HTML.** No raw page
  HTML is saved for any run. It was checked on test fixtures, on the 6 rendered HTML files on disk,
  and on 504 claim titles and quotes across the 29 saved runs (0 false positives), not on the pages
  themselves. The next sanctioned `--no-cache` run lists any flagged page in `blocked_pages` with its
  reason, so a false positive would be visible there.
- **The language check (B-85) was run on quotes, not full page text.** Saved runs keep no page text,
  so the check over all 29 runs used their claim quotes and page titles: 0 flagged non-English (22
  "en", 7 "unknown"). Its thresholds were set from test fixtures only. On those short quotes
  Freshworks and SimpleStores sit just above the English threshold (0.106 to 0.107 against 0.10);
  below it they would read "unknown", which is still not flagged.

## Deferred (found on postman.com, 2026-10-09)

- **Docs subdomains crowd out company pages.** The approved domains include every subdomain of the
  site, so on postman.com 12 of the 38 pages fetched within the 120 s budget were
  `learning.postman.com` documentation (integration and admin guides). Company pages compete with
  them for the same page and time budget; `traction.partnerships` came back `not_found` although
  `/partner-program` was crawled. No change has been made.
- **`pricing.revenue_model` can rest on a metered price.** On postman.com the model's own answer was
  rejected and Jev filled the field with "Subscription", quoting "$20 per 50,000 requests / team /
  month", a usage-priced add-on rather than a plan price. B-68's evidence rule accepts any
  recurring per-period price line, including metered ones. "Subscription" is probably right for
  Postman's plans, but that quote supports usage-based pricing at least as well.
- **Text the cleaner drops has no cause category of its own.** `docs/ERROR_REVIEW.md` sorts misses
  into crawl, model, gate, inference and label causes, but not "on the page, dropped by the
  cleaner". On postman.com the certification badge grid (PCI DSS, HIPAA, ISO 27001, ISO 42001 ...)
  was visible text in the raw HTML that trafilatura removed, so the model could only see "SOC 2";
  B-92 now folds badge grids back in, but other layouts can be lost the same way, and in a review
  they look like "model missed it". B-88 snapshots save the cleaned text and only a checksum of the
  raw HTML, so a cleaner loss still needs a fresh fetch of the page to confirm.
- **Locale skipping can still misread a section path in one rare case.** B-93 skips non-English
  locale copies on any site when there is evidence they are locales (a locale start URL, a language
  switcher, an English locale link, a country code such as `/jp/`, or a language-with-region form),
  which fixes postman.com's `/jp/` pages. A lone `/hr/` or `/it/` section on a bare-domain site is
  kept as a possible HR or IT section. But since B-90 reads `/us/`, `/uk/` and the other
  English-speaking country segments as English, a start page that links to a country page such as
  `/us/pricing` now counts as an English-locale site (B-69's rule), and a lone `/hr/` section on
  that same site would then be skipped as Croatian. It needs both a country-site link and an HR
  section at `/hr/` on one site, so it should be rare; no test covers it and no change has been made.
