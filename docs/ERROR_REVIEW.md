# DRAFT: Error review, post-B-81 dev measurement

Dev set (Calendly, Loom, Typeform, Notion, SimpleStores), 3 rounds, `--no-cache`, scored with
`eval/baseline.py --semantic-judge`, code at `EXTRACTION_LOGIC_VERSION` 22 with Jev on.
Headline 69.3 / 66.7 / 66.7, mean **67.6%**.

## How this was produced

- Verdicts come from re-scoring each round's saved run files against `eval/labels/` with
  `wi.eval.scoring.score_run` (pure comparison, no model calls). Round 3's run files are the ones in
  `data/runs/`; rounds 1 and 2 are the copies saved during the measurement.
- The semantic judge's upgrades are not stored per field, only as counts. They were reconstructed
  by finding the upgrades that reproduce the per-site and per-field `correct_semantic` counts in
  `eval/baseline_report_b81_nc1-3.json`. Exactly one assignment fits in each round, and the
  resulting verdict counts match the reports exactly (round 1: 6 incorrect, 14 miss, 3 unsupported;
  round 2: 7 / 14 / 4; round 3: 7 / 15 / 3).
- "Crawl never reached the page" was checked by comparing each label's `source_url` with the pages
  each run fetched (final and requested URLs). Rejections come from each run's `rejected` list.

## Summary

73 non-right verdicts over 3 rounds × 5 sites × 15 fields (225 scored cells).

| Cause | Verdicts | Share | Notes |
| --- | ---: | ---: | --- |
| Crawl never reached the page | 0 | 0% | Every label source page (59 per round) was fetched in every round. |
| Model missed it | 24 | 33% | Page crawled, model returned `not_found` (or the wrong items) with nothing rejected. |
| Gate rejected it | 22 | 30% | 17 rightly (the model's quote did not support its value, or was not on the page); 5 rejected a value that matches the label (the `products.names` bare-label guard, see below). |
| Wrong inference | 1 | 1% | Calendly round 2: a free plan reported as a free trial. |
| Label ambiguous | 26 | 36% | Label granularity or format the system cannot match (11), two valid wordings on the site (6), label `not_found` where the run found gate-verified text (9). Needs independent re-checking; labels are not edited to match outputs. |

## Every incorrect, miss and unsupported verdict

R1/R2/R3 give the verdict in each round (blank = a right call that round).

| Site | Field | R1 | R2 | R3 | Cause | What happened |
| --- | --- | --- | --- | --- | --- | --- |
| Calendly | customers.industries | miss | miss | miss | Model missed it | Label lists Education, Technology, Financial Services, Professional Services from the homepage, which was crawled; the model returned `not_found`. |
| Calendly | customers.segments | incorrect | incorrect | incorrect | Label ambiguous | Label "Individuals, Small business, Large companies" (homepage); system "Individuals, teams, and organizations" quoted from /about. Both are site text; the judge did not count them as the same. |
| Calendly | pricing.free_trial | | unsupported | | Wrong inference | Label `not_found`; system extracted "Free" from /pricing, i.e. the free plan read as a trial. |
| Calendly | products.delivery_model | unsupported | unsupported | unsupported | Label ambiguous | Label `not_found`; system inferred "software" (B-81 trimmed "web app"). Calendly is software, so the label rather than the answer looks wrong. |
| Calendly | traction.certifications | unsupported | unsupported | unsupported | Label ambiguous | Label `not_found`; system extracted SOC 2 (Type 2), SOC 3, CSA STAR, PCI, ISO/IEC 27001 from /security, each quote verified by the gate. |
| Calendly | traction.named_customers | miss | miss | miss | Model missed it | Label has three customer names from homepage testimonials; the model returned `not_found`. |
| Loom | comparisons.named_alternatives | miss | miss | miss | Model missed it | Label Vidyard, Zoom Clips, Microsoft Clipchamp (homepage); not found by the model. |
| Loom | customers.segments | miss | miss | miss | Model missed it | Label "Teams and individuals" (/pricing, crawled); not found. |
| Loom | pricing.free_trial | incorrect | incorrect | incorrect | Label ambiguous | System "14-day free trial"; label is per plan ("Business + AI: 14-day free trial; Enterprise: ... by contacting sales"). Same substance, different granularity; this field is not one the judge reviews. |
| Loom | pricing.revenue_model | | | miss | Gate rejected it (rightly) | Quote "$29/month" not found on the page. |
| Loom | products.names | miss | miss | miss | Gate rejected it (rightly) | Model offered "Loom for Enterprise / Sales / Engineering ..." (use-case pages) with bare-label quotes; the guard rejected them. The label's "Loom AI" was never proposed. |
| Loom | traction.certifications | miss | miss | miss | Model missed it | Label SOC 2 Type 2, GDPR, CCPA from /enterprise, which was crawled; not found. |
| Notion | company_identity.description | miss | miss | miss | Gate rejected it (rightly) | The model wrote its own summary each round ("Notion is a workspace that brings together ..."); not page text. |
| Notion | products.delivery_model | incorrect | miss | incorrect | Label ambiguous (R1, R3); gate rejected it (R2) | Label "Digital software delivered online with a downloadable app" vs system "software". R2: the quote was not on the page. |
| Notion | products.names | miss | incorrect | miss | Gate rejected a correct value | "Notion AI" (the label's only item) was rejected by the bare-label guard because its quote was just "Notion AI" (R1, R3); in R2 its quote did not support it and only "Custom Agents" survived. |
| SimpleStores | comparisons.named_alternatives | miss | miss | miss | Model missed it | Label Shopify, Dukaan from /platform (crawled); not found. |
| SimpleStores | customers.segments | miss | miss | miss | Gate rejected it (rightly) | Value matched the label ("Product and service businesses"), but the quote ("The product connects storefront and ERP workflows.") does not support it. |
| SimpleStores | pricing.revenue_model | incorrect | incorrect | incorrect | Label ambiguous | System "subscription"; label "Subscription with flat platform transaction fees". Partly right; not a judge-reviewed field. |
| SimpleStores | products.delivery_model | incorrect | incorrect | incorrect | Label ambiguous | Label "Digital software delivered through an online platform, storefronts, and mobile applications" vs system "software". |
| SimpleStores | products.names | miss | miss | miss | Model missed it | Label "Cart Vault" (/pricing). R2 offered plan names (Standard, Business ...), rightly rejected as bare labels. |
| SimpleStores | traction.named_customers | unsupported | unsupported | unsupported | Label ambiguous | Label `not_found`; system extracted HostelNests (R1) and nine names (R2, R3) from /customers and the homepage, quotes verified by the gate. |
| Typeform | company_identity.description | incorrect | incorrect | incorrect | Label ambiguous | Label "Typeform provides AI-powered forms and automation." (homepage); system "... we give forms a better look and feel ..." (/about-us). Both are site text. |
| Typeform | pricing.free_trial | miss | miss | miss | Gate rejected it (rightly) | Value "14-day free trial" quoted "379USD/mo after 14 days", which does not say free. |
| Typeform | pricing.public_plans | miss | miss | miss | Gate rejected it (rightly) | Model added "plan" to each name ("Free plan", "Basic plan" ...) and quoted feature lines ("Includes: 100 responses/mo"); the first item failed. |
| Typeform | products.names | | incorrect | incorrect | Gate rejected a correct value | Only "AI forms" survived; "Growth Flow", which is in the label, was rejected as a bare-label quote. (R1 kept Growth Flow: correct_partial.) |
| Typeform | traction.named_customers | miss | miss | miss | Model missed it | Label lists ten logos from /pricing (crawled). Not checked whether the names are text or only images on the page; cleaned text is not saved. |

## Patterns

1. **Labels cost about as much as the model.** 26 of 73 verdicts are label granularity or format
   (`delivery_model` labels are long free text that predate the "category (channels)" convention of
   B-66; `free_trial` and `revenue_model` labels carry per-plan detail), two valid wordings, or a
   `not_found` label where the run found gate-verified text (Calendly certifications, SimpleStores
   named customers). The labels were made by hand from website screenshots (see each file's
   `labeling_metadata`), so text on pages the screenshots did not cover can be missing. These need
   an independent re-check of the labels, not output-matching edits.
2. **No crawl misses.** Every page a label cites was fetched in every round, so the remaining
   misses are extraction, not discovery.
3. **The gate mostly rejects real problems.** 17 of 22 rejections are the model quoting the wrong
   line, adding words, or writing its own summary. The exception is the `products.names`
   bare-label guard (5 verdicts on Notion and Typeform), which also rejects a correct name when the
   only quote available is the name itself.
4. **Same misses every round.** 23 of the 26 rows fail in all three rounds, so these are stable
   behaviours, not sampling noise.

## AC-11 breakdown

| Measure | R1 | R2 | R3 | Mean | How it is computed |
| --- | ---: | ---: | ---: | ---: | --- |
| Crawl coverage | 59/59 | 59/59 | 59/59 | 100% | Label source pages fetched by the run (final or requested URL). |
| Evidence-support rate (returned claims) | 100% | 100% | 100% | 100% | Every returned extracted or inferred claim passed the evidence gate (by construction; AC-01). |
| Gate pass rate (claims attempted) | 82.0% | 82.4% | 80.0% | 81.5% | Returned claims / (returned + fully rejected). Partial trims: 1, 2, 2. |
| Extraction accuracy | 87.5% | 80.0% | 83.3% | 83.6% | From the baseline reports. |
| Inference accuracy | 78.6% | 84.6% | 76.9% | 80.0% | From the baseline reports. |
| Conflict handling | 0 | 0 | 0 | 0 | Conflicting claims returned; no dev label is conflicting, so this is untested on the dev set. |
| Abstention quality | 20/23 | 19/23 | 20/23 | 85.5% | Correct abstentions / fields the label marks `not_found`. |
| Miss rate | 14/52 | 14/52 | 15/52 | 27.6% | Misses / fields the label gives a value. |
| Headline accuracy | 69.3% | 66.7% | 66.7% | 67.6% | Right calls / 75 (judge on). |
