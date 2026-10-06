# 1. Final PRD

Deliverable: Final PRD incorporating the founder scope brief, stable requirement IDs and behavioral acceptance criteria.
Exit criterion: Required, excluded and deferred scope is explicit; every retained feature is testable and ready for founder review.
Order: 1
Owner: Uttam
Stage: Product contract
Status: Done

# Final PRD — Company Website Intelligence Prototype

> **Version:** 1.0 · **Owner:** Uttam · **Approver:** Abhishek · **Date:** 21 September 2026 · **Delivery window:** 4 weeks
Founder scope decisions are treated as **confirmed**. Only the parameters in Section 13 and the decisions in Section 14 are proposals for approval.
> 

---

## 1. Product definition

> Given one public company website URL, produce a structured, evidence-backed profile of what the company states on its own website.
> 
- A company website is a **self-reported source**. The system extracts and classifies the company's claims. It never presents them as independently verified.
- The MVP is a **controlled extraction pipeline**, not a research agent. No autonomous behaviour is included unless it is necessary and benchmarked.
- The LLM is a bounded extraction component. It is not the crawler, orchestrator, calculator or renderer.

**Definition of success:** a reproducible, measured prototype that turns first-party web claims into a typed evidence ledger, a canonical profile and a simple source-traced page, without treating self-reported claims as verified fact.

---

## 2. Scope

### In scope (MVP)

- One public company URL in, one profile out.
- Same-domain page discovery and a bounded crawl.
- Cleaning, de-duplication and rule-based page classification.
- The frozen core schema (Section 4).
- An evidence ledger and a canonical profile as separate outputs.
- Caching, plus measurement of accuracy, evidence support, abstention, latency, tokens and variable AI cost.
- A reproducible Python module or CLI.
- A lightweight read-only reference profile page that consumes saved JSON.
- **Conditional P1:** a bounded latest-news snapshot (Section 8).

### Out of scope

- Broad or unrestricted external research (other than the P1 news snapshot).
- Independent competitor discovery, market-size estimation, objective market positioning or company scoring.
- Revenue, profitability or valuation estimates.
- Legal, regulatory or negative-signal research beyond pages published on the approved company domain.
- LinkedIn, X/Twitter or other restricted-platform scraping.
- Private, authenticated or paywalled sources.
- Investment recommendations or automated diligence conclusions.
- A universal crawler for every site architecture.
- Production deployment, production database integration or direct Prajna integration.
- A polished dashboard.
- Multi-agent orchestration, LangChain, CrewAI or similar frameworks, unless a measured baseline shows a specific need.

### Deferred (future work only)

- Continuous monitoring, notifications, email digests and portfolio-scale alerts.
- Broad external enrichment.
- Agentic research.
- Production API and database integration.
- Polished UI.
- Batch processing.

**Rule for out-of-scope topics.** Funding, financial, legal, regulatory, competitor and acquisition fields are not core fields. If the company states one on its own site, it may be captured only as a dated **company-reported announcement** with evidence. It is never presented as verified intelligence.

---

## 3. Requirements

Each requirement has a stable ID and a testable acceptance criterion (AC). Requirements are MVP unless marked **P1** (conditional, Section 8).

### 3.1 Input and retrieval

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| INP-01 | Accept one public company URL and reject invalid input with a structured error (`INVALID_URL`). | 10 malformed inputs return the error and make no network request. |
| INP-02 | Resolve redirects, the canonical URL and the approved domain (canonical host plus its `www` variant). | http to https and apex to www resolve correctly. The final URL is recorded. |
| INP-03 | Return a structured status for unreachable or blocking sites (`SITE_UNREACHABLE`, `crawl_status: blocked`). | A blocked-site fixture returns a partial or empty profile with the flag set. |
| CRL-01 | Discover and prioritise same-domain pages by type (about, product, solutions, pricing, customers, case studies, partners, news, comparison). | Principal relevant pages are found on at least 80% of development sites (Week 2 gate). |
| CRL-02 | Enforce caps on depth, page count, timeout, rate limit and page size (Section 13). | On a 10,000-page fixture site, no cap is exceeded. |
| CRL-03 | Respect robots directives. Never bypass CAPTCHA or bot protection. | A robots-disallowed path is not fetched. |
| CRL-04 | Fetch static pages first. Use a JavaScript renderer only when static content is insufficient, and flag the page. | The fallback triggers only on the JS-only fixture. |
| CRL-05 | Store raw retrieval separately from cleaned content. | Raw and cleaned files are distinct artefacts with a shared page ID. |
| CLN-01 | Remove navigation, boilerplate and scripts. Deduplicate by normalised URL and content hash. | Duplicate fixtures collapse to one page. |
| CLN-02 | Classify pages by purpose using URL and title rules, with no LLM. | Zero model calls in classification (verified by the run log). |

### 3.2 Extraction and evidence

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| EXT-01 | Extract schema.org, OpenGraph, meta tags and regex patterns before any model call. | Fields resolvable this way are populated with no model tokens spent. |
| EXT-02 | Select relevant passages only. Never send full pages to the model. | Input tokens per run stay under the cap (Section 13). |
| EXT-03 | Use a small structured-output model to emit **claim objects only** (no prose). | Output validates against the claim schema. |
| EXT-04 | Escalate to a stronger model only for unresolved ambiguity or conflicts, within a hard call limit. | Escalated claims are 10% or fewer of all claims. The count is logged. |
| EXT-05 | Keep provider and model configurable. | Swapping the model needs a config change only. |
| EVD-01 | Every `extracted` or `inferred` claim carries `source_url`, `page_title`, `evidence` and `retrieved_at`. | 100% of such claims pass the presence check. |
| EVD-02 | Evidence must be verbatim or near-verbatim text from the cleaned page, checked deterministically. The quote must also support the value: key terms in the value (numbers, names) must appear in the quote. | Quote found in the page text (normalised match, or fuzzy 0.9 or above). Key-term check passes. Failing claims are rejected or set to `not_found`. Ambiguous cases go to escalation. |
| EVD-03 | Use exactly four statuses: `extracted`, `inferred`, `not_found`, `conflicting`. Allow `inferred` only for whitelisted fields, with a `notes` explanation. | An inference on a non-whitelisted field fails validation. |
| EVD-04 | `not_found` records coverage: which page types and how many pages were checked. | Every `not_found` claim has a coverage record. |
| EVD-05 | Preserve conflicting values with evidence. Never silently pick one. | The conflict fixture yields one `conflicting` claim listing both values. |
| EVD-06 | Use one representation per field type. Never mix bare values, `null`, `"not_found"` strings and wrapped objects. | The schema rejects mixed forms. |
| EVD-07 | "Contact sales" supports a sales-led motion only. It does not prove subscription pricing. Absent pricing is `not_found`. | The pricing fixtures behave as specified. |

### 3.3 Output, cost and interface

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| OUT-01 | Produce two separate outputs: an **evidence ledger** (claims) and a **canonical profile** that references claim IDs. The profile is derived from validated claims, not from model prose. | Every profile value resolves to at least one claim ID. |
| OUT-02 | Validate against a typed schema and stamp the schema version. | Invalid output never reaches the profile. |
| OUT-03 | Repeat runs on unchanged cached content give structurally consistent output. | Same fields, statuses and claim count across 3 runs. |
| OUT-04 | Capture company-reported announcements only as dated first-party items, never as core fields. | A funding-statement fixture appears under `evidence_traction` with a date and quote. |
| CST-01 | Cache by content fingerprint plus prompt, schema and model version. Reprocess only changed pages. | An unchanged re-run makes 0 model calls. |
| CST-02 | Log model, tokens, latency, cache status and variable cost for every run. Produce a per-website cost report. | The report exists for every benchmark site. |
| CST-03 | Enforce hard limits on pages, characters and tokens. Degrade gracefully on breach. | A breach fixture returns a partial profile with a `limit_reached` flag. |
| UI-01 | Render a read-only reference page from saved JSON. Opening or refreshing it makes **no** LLM call. | The page loads with the LLM endpoint blocked. |
| UI-02 | Show the sections in Section 6, with a visible status badge per fact and `not_found` fields in a gaps panel only. | A visual check against the Section 6 list passes. |
| PKG-01 | Package as a Python module or CLI with setup, run and evaluation documented. | A second developer reproduces the benchmark from the docs alone (Week 4 gate). |

---

## 4. Frozen core schema

Six groups. Every populated field is a claim (Section 5).

| Group | Fields |
| --- | --- |
| **A. Company identity** | Company or brand name · website and canonical domain · description · headquarters and disclosed operating geographies · stated company category |
| **B. Products and services** | Names · descriptions · features and capabilities · use cases · delivery model (software, service, marketplace, physical) · product page URLs |
| **C. Customers and positioning** | Target segments · industries served · buyer or user personas mentioned · problems claimed to be addressed · geographies served · positioning statements and claimed differentiators |
| **D. Pricing and commercial signals** | Public plans and amounts · billing frequency and currency · free trial, freemium, demo or contact-sales model · usage, subscription, transaction, licensing or service-fee signals. Delivery model, revenue model, sales motion and actual pricing are **separate fields**. |
| **E. Traction claimed by the company** | Named customers · testimonials and case studies · partnerships and integrations · certifications · quantitative claims with qualifiers and dates · dated first-party announcements and product launches |
| **F. Company-named comparisons** | Competitors or alternatives the company names · comparison pages · claimed advantages and disadvantages, each with evidence. These are the company's comparisons, not an independent conclusion. |

**Not in the schema:** funding, financials, legal, regulatory, independent competitors, acquisitions and market size.

---

## 5. Data contracts

### Claim object (the only unit of fact)

```json
{
  "claim_id": "claim_001",
  "field": "business_model",
  "value": "Subscription SaaS",
  "status": "inferred",
  "confidence": 0.72,
  "source_url": "https://example.com/pricing",
  "page_title": "Pricing",
  "evidence": "Choose a monthly or annual plan.",
  "retrieved_at": "2026-09-21",
  "notes": "The website does not explicitly name the business model."
}
```

### Rules

1. The quotation must support the value.
2. Model output and search snippets are not evidence. The underlying page is.
3. `not_found` needs no quotation, but it records coverage.
4. Conflicting values are preserved, never silently resolved.
5. The input URL is the only field exempt from evidence.
6. **Confidence is a heuristic, not proof.** It is assigned by rule, not by model self-score. Proposed rule: `extracted` with an exact quote match and one clean source scores 0.80 or above. `inferred` is capped at 0.75. Any conflict lowers the score. The user-facing page shows High, Medium or Low only, not the number.

### Output 1 — Evidence ledger

The ledger stores every atomic claim with its status, source, quotation, retrieval date, inference note and conflict. This is the **audit layer**.

### Output 2 — Canonical company profile

The profile holds the current display value for each approved field and references the supporting claim IDs. This is the **product-facing layer**.

```json
{
  "profile": {
    "company_identity": {},
    "products_services": [],
    "customers_positioning": {},
    "pricing_commercial": {},
    "evidence_traction": [],
    "company_comparisons": [],
    "coverage": {},
    "gaps_conflicts": []
  },
  "claims": []
}
```

**Build order:** extract claim objects, validate them, reconcile conflicts, then derive the profile. One model is never asked to read all content and write polished prose directly.

---

## 6. Reference profile page (Week 4)

Read-only, rendered from stored JSON, with no LLM call. It proves the schema can drive a product surface. It is not a polished dashboard and not a Prajna integration.

1. Header: company name, domain, "Website-sourced profile" label.
2. Trust and coverage strip: pages scanned, fields populated, evidence-support rate, inferences, conflicts, last retrieval date.
3. Company overview.
4. Products and services.
5. Customers, industries and use cases.
6. Positioning and claimed differentiators.
7. Pricing and commercial signals.
8. Customers, partnerships, certifications and claims.
9. Gaps and conflicts (all `not_found` fields live here, not as empty cards).
10. Evidence ledger and source drawer.

Every displayed fact carries a status: **Sourced**, **Inferred** or **Conflicting**.

---

## 7. Pipeline and cost controls

```
URL
→ deterministic crawl and clean
→ rule-based page classification
→ metadata, schema.org and regex extraction
→ relevant-passage selection
→ small structured-output model
→ deterministic schema and evidence validation
→ stronger model only for unresolved ambiguity or conflicts
→ cached ledger and canonical profile
→ zero-LLM page rendering
```

- No LLM for URL validation, crawling, cleaning, de-duplication or URL and title classification.
- Hard limits on pages, characters, input tokens and output tokens.
- Cache by content fingerprint and prompt version. Reprocess only changed pages. Store generated profiles and never regenerate them on page view.
- Provider and model stay configurable until benchmark evidence supports a default.
- **DSPy** is introduced only after the labelled baseline and metric exist. It is kept only if held-out quality improves without unacceptable cost, latency or provenance loss.
- **Implementation candidates (provisional until the baseline shows a need):** httpx, Scrapy, lxml or BeautifulSoup, Trafilatura or readability-lxml, Playwright (fallback only), feedparser, Pydantic, SQLite. Firecrawl may be benchmarked as a self-hosted candidate against Scrapy plus Trafilatura. It is not mandated until its current licence, maintenance status, deployment burden and measured extraction quality are verified.

---

## 8. Conditional P1 — latest-news snapshot

Built **only after the Week 3 website-profile gate passes**, as a bounded spike in Week 4. It stays separate from the website profile.

- **Two evidence layers:** website profile (what the company states) and external news (what third-party publishers reported). They are never merged without source class, publisher, publication date, retrieval date and evidence.
- **Scope:** resolve company name, domain and available location and category signals. Search a 90-day lookback (configurable). Return at most 10 deduplicated items. Capture headline, publisher, URL, published date, retrieved date, supporting excerpt, event category and relevance status. Separate `company_announcement` from `third_party_news`. Return `not_found` when no credible result exists.
- **Event categories:** funding, product launch, partnership, customer or contract, leadership change, expansion, acquisition, hiring or layoffs, legal or regulatory, other material announcement. These are reported events only. No sentiment scoring, company scoring or autonomous risk conclusions.
- **Free and open first:** company and publisher RSS, GDELT, `feedparser`. Escalation order: static HTTP, then RSS or sitemap, then deterministic text extraction, then Playwright only for JS-heavy sources, then a small model only for ambiguous relevance or classification, then a stronger model only for unresolved conflicts.
- **Google Alerts** may support development (comparing missed articles, supplying candidate URLs, a temporary monitoring feed). It is never the required ingestion mechanism.
- Respect robots directives, publisher terms, access controls and rate limits. Never bypass CAPTCHA or bot protection. Never crawl whole publisher sites.
- Record news latency, tokens, model calls and variable cost **separately** from website-profile processing.
- Open-source software is low licence cost, not zero operating cost. Measure browser compute, storage and maintenance.

### Canonical news object

```json
{
  "news_id": "news_001",
  "company_id": "company_001",
  "source_class": "third_party_news",
  "publisher": "Publisher name",
  "url": "https://example.com/article",
  "headline": "Example headline",
  "published_at": "2026-09-10",
  "retrieved_at": "2026-09-21",
  "evidence": "Supporting passage from the underlying article.",
  "event_type": "partnership",
  "relevance_status": "matched"
}
```

| ID | Requirement | Acceptance criterion |
| --- | --- | --- |
| R-NEWS-001 | Retrieve a bounded list of recent external items for the resolved company. | At most 10 items, within the lookback. |
| R-NEWS-002 | Never represent third-party news as company-website evidence. | Every item carries `source_class: third_party_news`. None is labelled first-party or verified. |
| R-NEWS-003 | Use name, canonical domain and context for entity resolution. | At least 90% of retained articles refer to the intended company on the held-out news benchmark. |
| R-NEWS-004 | Enforce lookback, cap, timeout and de-duplication. | Syndicated duplicates collapse to one event cluster. |
| R-NEWS-005 | A headline or snippet is not a claim unless the article text supports it. Label inaccessible sources. | Every item has publisher, URL, dates, and evidence or an explicit `inaccessible` status. |
| R-NEWS-006 | News failure is non-blocking. | The website profile completes when the news collector is forced to fail. |

---

## 9. Error handling and edge cases

| Scenario | Expected behaviour |
| --- | --- |
| Invalid URL | Structured `INVALID_URL` error. No crawl. |
| Site unreachable | Bounded retries, then `SITE_UNREACHABLE`. |
| Site blocks crawler | Respect the block. Return a partial result with `crawl_status: blocked`. |
| JavaScript-heavy site | Extract what static HTML gives. Use the Playwright fallback only if content is insufficient. Flag low completeness. |
| Very little information | Mostly `not_found` with coverage recorded. Never fabricate. |
| Very large site | Enforce page and depth caps. Prioritise known-relevant page types. |
| Duplicate pages | De-duplicate by normalised URL and content hash. |
| Conflicting information | `conflicting` status. Keep both values with evidence. |
| Model returns invalid JSON or fails validation | One corrective retry with the specific error. If it still fails, mark the section `not_found` and continue. |
| LLM or site rate limit | Exponential backoff within the time budget. |
| Timeout | Skip the page, log it, continue with partial data. |
| Redirect | Cap the chain. Record the final resolved URL as the source. |
| Non-English site | Attempt extraction and flag the language. Translation is deferred. |
| News collector fails | Website profile still completes. Flag that news was unavailable. |

---

## 10. Four-week delivery plan

| Week | Build | Gate (pass or reduce scope) |
| --- | --- | --- |
| **1. Contract and baseline** | Confirm repository, working terms, permitted tools and benchmark sites. Freeze the schema and claim object. Hand-label at least 5 reference profiles. Complete the behavioural test list. Build the simplest end-to-end baseline for one static site. | One URL gives schema-valid output and every populated value has evidence. **If it fails:** reduce scope to labelled-data preparation and extraction QA. |
| **2. Controlled discovery and retrieval** | Same-domain discovery, cleaning, de-duplication, redirects, caching, limits, structured failure logs. Raw and cleaned content stored separately. | Principal relevant pages found on at least 80% of development sites, with no uncontrolled crawling. |
| **3. Extraction and bounded optimisation** | Frozen schema, ledger, canonical profile. Schema and evidence-presence checks. Field-level baseline. One bounded DSPy or prompt-optimisation trial, only after the baseline exists. | Keep the optimisation only if held-out gain is measurable and provenance is intact. |
| **4. Held-out evaluation and handoff** | Test on unseen sites. Review false positives, false negatives, unsupported claims and abstention failures. Reference renderer. P1 news spike (only if the Week 3 gate passed). Package code, tests, sample outputs, benchmark results and documentation. | Another developer reproduces the benchmark and runs the prototype from the documentation. |

**Proposed cut order if Week 4 overruns:** (1) news spike, (2) renderer polish, (3) DSPy trial. Held-out evaluation and reproducibility are never cut.

---

## 11. Acceptance criteria

| # | Criterion |
| --- | --- |
| AC-01 | At least 90% of returned factual claims have valid supporting evidence. |
| AC-02 | At least 80% accuracy across the agreed core fields on held-out websites (scoring rules in Section 12). |
| AC-03 | No unsupported value is presented as directly extracted. |
| AC-04 | `not_found` is returned when evidence is insufficient. |
| AC-05 | A new supported website is processed with no company-specific code changes. |
| AC-06 | Raw retrieval, cleaned content, claims and canonical profile remain separate. |
| AC-07 | Repeat runs on unchanged cached content are structurally consistent. |
| AC-08 | Setup, execution and evaluation are reproducible by a second developer. |
| AC-09 | Results are reported **per field**, not as one blended score. |
| AC-10 | p50 and p95 latency, token use and variable AI cost per website are reported. |
| AC-11 | Reported separately: crawl coverage, evidence-support rate, extraction accuracy, inference accuracy, conflict handling and abstention quality. |
| AC-12 | If the P1 news spike runs: entity-match precision, duplicate rate, source-access rate, p50 and p95 news latency, and news cost are reported separately. |

**"Supported website"** (proposed definition, for AC-05): a public, English-language site whose principal content is available in static HTML or through the JS fallback, within the caps in Section 13. Sites outside this definition return a flagged partial result, never a silent failure.

---

## 12. Evaluation, scoring and benchmark

**Benchmark split (proposed):** 8 development sites and 10 unseen held-out sites, 18 in total. Held-out sites are frozen before Week 4 and never used for tuning. Coverage: SaaS, fintech, healthcare, manufacturing, AI startup, services, marketplace, plus at least one sparse site and one JS-heavy site. The exact list goes in Appendix A and is approved before Week 1 labelling.

**Ground truth:** researched manually and independently of the pipeline, with the source URL recorded per field.

**Scoring rules (per field):**

| Case | Counts as |
| --- | --- |
| Value matches the label (after normalising) | Correct |
| Value differs from the label | Incorrect |
| Label is `not_found` and the system returns `not_found` | Correct abstention |
| Label has a value and the system returns `not_found` | Miss |
| Label is `not_found` and the system returns a value | **Unsupported** (most serious) |

**Test layers** (behavioural list in Appendix B; Work Item 4 expands it into deterministic tests):

| Layer | Examples |
| --- | --- |
| Unit | URL validation, redirect and canonical resolution, de-duplication, page classification rules, quote matching, status and schema validation |
| Contract | Claim and profile schema, mixed-representation rejection, claim-ID references |
| Behavioural | Absent pricing gives `not_found`. "Contact sales" is not subscription. Conflicting pages give `conflicting`. Funding statement becomes a dated announcement only. Unsupported quote is rejected. |
| Robustness | Blocked site, timeout, huge site, non-English site, JS-only site, malformed LLM output, limit breach |
| Cost and cache | Unchanged re-run makes 0 model calls. Per-run cost record is complete. |
| Interface | Page renders offline from JSON with the LLM blocked |
| Evaluation | Field-level accuracy, evidence-support rate and abstention quality on the dev and held-out sets |

---

## 13. Proposed parameters (for Abhishek's approval)

These are implementation parameters, not scope. They are tunable after the Week 1 baseline.

| Parameter | Proposed default |
| --- | --- |
| Crawl depth | 2 levels from the homepage |
| Page cap | 25 pages per site |
| Request timeout and total crawl budget | 10 s per request, 120 s per site |
| Rate limit | 1 request per second per domain |
| Page size cap | 2 MB raw, 12,000 cleaned characters per page |
| Token budget per run | 40,000 input, 6,000 output |
| Small model | A Flash or Haiku-class structured-output model (configurable) |
| Escalation model | One stronger model, at most 3 calls per run |
| Cache invalidation | Key is content hash plus prompt, schema and model version. Re-run changed pages only. 30-day maximum age. |
| Latency target | p50 60 s or less, p95 180 s or less per website |
| Variable AI cost | Mean USD 0.10 or less per website, p95 USD 0.25 or less |
| News (P1) | 90-day lookback, at most 10 items, 15 s timeout per source |

---

## 14. Decisions requested

1. Approve the Section 13 parameters, or change them.
2. Approve the benchmark split and selection rule (Appendix A to follow).
3. Confirm the confidence rule in Section 5 (rule-derived, shown as High, Medium or Low).
4. Confirm the "supported website" definition in Section 11.
5. Confirm the cut order in Section 10.
6. Confirm that news items, including the "legal or regulatory" category, are shown only as labelled third-party reported events and are never scored or turned into conclusions.

---

## Appendix A — Benchmark site list

**Proposed list for approval** (8 development, 10 held-out, chosen by the coverage rule in Section 12). Each site is verified against the checklist below before it is locked. Any site that blocks crawlers or disallows the needed paths in `robots.txt` is swapped for another of the same type.

### Development set (used for building and tuning)

| # | Company | URL | Type | Why it is included |
| --- | --- | --- | --- | --- |
| D1 | Basecamp | basecamp.com | SaaS, public pricing | Clear plans and amounts, simple static pages |
| D2 | Darwinbox | darwinbox.com | SaaS, demo or contact-sales | Tests "contact sales" handling and absent pricing |
| D3 | Zerodha | zerodha.com | Fintech | Public fee pages, compliance and product claims |
| D4 | Bajaj Auto | bajajauto.com | Manufacturing | Product-heavy pages, little pricing |
| D5 | thoughtbot | thoughtbot.com | Services | Services rather than software, case studies |
| D6 | Berkshire Hathaway | berkshirehathaway.com | Sparse, plain-HTML site | Very little product or pricing text. Tests abstention. |
| D7 | Linear | linear.app | JavaScript-heavy | Tests the JS-fallback flag |
| D8 | Urban Company | urbancompany.com | Marketplace | Different delivery and revenue model |

### Held-out set (frozen, not opened until Week 4)

| # | Company | URL | Type | Why it is included |
| --- | --- | --- | --- | --- |
| H1 | Razorpay | razorpay.com | Fintech | Product breadth, public pricing, certifications |
| H2 | Buffer | buffer.com | SaaS, public pricing | Pricing extraction on an unseen layout |
| H3 | Innovaccer | innovaccer.com | Healthcare tech | Regulated domain, many claims and certifications |
| H4 | Sarvam AI | sarvam.ai | AI startup | Fast-changing site, product and model claims |
| H5 | Tata Motors | tatamotors.com | Manufacturing | Large multi-section site, tests caps |
| H6 | Thoughtworks | thoughtworks.com | Services | Large services site, many case studies |
| H7 | NoBroker | nobroker.in | Marketplace | Consumer marketplace with a different structure |
| H8 | Gong | gong.io | SaaS, contact-sales | Enterprise site, demo-led sales motion |
| H9 | Plaid | plaid.com | Fintech, developer-led | Developer docs mixed with marketing |
| H10 | *(you choose)* |  | Second sparse site | Small local business site. Tests abstention on unseen data. |

### Verification checklist (about 5 minutes per site, before locking the list)

1. Open the homepage and confirm it loads without login.
2. Check `robots.txt`. Swap the site if it blocks the pages you need.
3. Check whether a pricing page exists, and whether it shows amounts or only "contact sales".
4. View the page source. If the main text is missing from the raw HTML, the site is JS-heavy (expected for D7, a problem elsewhere).
5. Confirm the site is in English and the company is still operating.
6. Record the date checked and any note (for example "pricing behind login").

## Appendix B — Behavioural test list

| ID | Behaviour |
| --- | --- |
| B-01 | Given a pricing page with plan amounts, plans, currency and billing period are captured with the quote. |
| B-02 | Given only "Contact sales" and no amounts, sales motion is `sales-led` (inferred) and public plans are `not_found`. |
| B-03 | Given "Contact sales", the business model is not set to subscription. |
| B-04 | Given a quote that does not appear in the page text, the claim is rejected. |
| B-05 | Given a quote that exists but does not support the value, the claim is rejected. |
| B-06 | Given two pages with different headquarters, status is `conflicting` and both values are kept. |
| B-07 | Given a page stating "we raised $5M", it appears only as a dated company-reported announcement, never as a core field. |
| B-08 | Given no customer logos, case studies or testimonials, named customers is `not_found` with coverage recorded. |
| B-09 | Given an inference on a non-whitelisted field, validation fails. |
| B-10 | Given mixed forms for one field type (bare value, `null` and `"not_found"`), the schema rejects it. |
| B-11 | Given an invalid URL, `INVALID_URL` is returned and no network call is made. |
| B-12 | Given a redirect chain longer than the cap, the crawl stops and reports the limit. |
| B-13 | Given a robots-disallowed path, it is not fetched. |
| B-14 | Given a site with 10,000 pages, no cap is exceeded. |
| B-15 | Given duplicate URLs and duplicate content, only one page is processed. |
| B-16 | Given a JS-only page, the fallback triggers and the page is flagged. |
| B-17 | Given an unchanged site on a second run, zero model calls are made. |
| B-18 | Given malformed model JSON, one corrective retry occurs, then the section is marked `not_found`. |
| B-19 | Given a token or page limit breach, a partial profile is returned with `limit_reached`. |
| B-20 | Given the LLM endpoint is blocked, the profile page still renders from saved JSON. |
| B-21 | Given three runs on unchanged cached content, structure is identical. |
| B-22 | Given a same-name company in the news, the item is rejected by entity resolution (P1). |
| B-23 | Given syndicated copies of one article, they collapse to one event cluster (P1). |
| B-24 | Given a forced news failure, the website profile still completes (P1). |
| B-25 | Given a news item, it is never labelled first-party or verified (P1). |

---

*Prepared by Uttam · Company Website Intelligence Prototype · Final PRD v1.0*