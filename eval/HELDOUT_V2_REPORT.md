# Held-out v2 report

First and only scoring run of held-out set v2, 2026-10-10. Numbers come from
`eval/held_out_v2_report.json` and the 8 run files (`data/runs/<slug>.json`). The diagnosis in
section 4 is post-hoc and read-only; nothing was changed after the run.

## 1. Result

**Headline 35%: AC-02 (at least 80% on held-out sites) is NOT MET.**

| Verdict | Count |
| --- | ---: |
| correct | 9 |
| correct_partial | 12 |
| correct_semantic | 9 |
| correct_abstention | 12 |
| **right calls** | **42 of 120** |
| incorrect | 31 |
| miss | 43 |
| unsupported | 4 |
| conflicting | 0 |

Extraction accuracy (AC-11) 61%, inference accuracy 25%, conflicting claims 0.

| Site | Accuracy |
| --- | ---: |
| cashfree.com | 47% |
| chargebee.com | 47% |
| cohere.com | 33% |
| elevenlabs.io | 40% |
| framer.com | 40% |
| leadsquared.com | 27% |
| mercury.com | 13% |
| miro.com | 33% |

| Field | Accuracy | Verdicts (of 8) |
| --- | ---: | --- |
| company_identity.name | 88% | correct 7, miss 1 |
| company_identity.description | 50% | correct 2, correct_semantic 2, incorrect 3, miss 1 |
| company_identity.headquarters | 38% | correct_abstention 3, miss 2, unsupported 3 |
| products.names | 12% | correct_partial 1, incorrect 1, miss 6 |
| products.delivery_model | 0% | incorrect 7, miss 1 |
| customers.segments | 25% | correct_semantic 2, miss 6 |
| customers.industries | 12% | correct_partial 1, incorrect 2, miss 5 |
| pricing.public_plans | 12% | correct_partial 1, incorrect 4, miss 3 |
| pricing.sales_motion | 62% | correct_semantic 5, incorrect 2, miss 1 |
| pricing.free_trial | 38% | correct_abstention 3, incorrect 3, miss 1, unsupported 1 |
| pricing.revenue_model | 0% | incorrect 6, miss 2 |
| traction.named_customers | 38% | correct_partial 3, incorrect 1, miss 4 |
| traction.certifications | 75% | correct_partial 6, miss 2 |
| traction.partnerships | 25% | correct_abstention 2, incorrect 2, miss 4 |
| comparisons.named_alternatives | 50% | correct_abstention 4, miss 4 |

**Dev comparison.** The dev headline is 63.6% on current code (mean of the three same-window
`eval/baseline_report_cmp_C_nc1-3.json` rounds, tag `pre-compare-b93`) and 67.6% for the post-B-81
build (`eval/baseline_report_b81_nc1-3.json`). The dev set (5 sites) was used to build and tune the
pipeline, so its headline overstates performance on unseen sites.

## 2. Protocol

- **Sites (8):** miro.com, leadsquared.com, cashfree.com, cohere.com, framer.com, chargebee.com,
  mercury.com, elevenlabs.io (selection and exclusions: `eval/benchmark_sites_v2.md`).
- **Labels:** made by hand before any pipeline run on these sites, following
  `eval/LABELLING_GUIDE_v2.md`; labeller "Uttam, with Claude".
- **Pre-run label fixes**, made before the checksum, each from an alt-text check:
  - framer.com `traction.named_customers`: `not_found` → 15 items.
  - miro.com `traction.named_customers`: 10 → 15 items.
  - leadsquared.com and mercury.com were checked and left unchanged.
- **Freeze:** labels frozen by checksum (`eval/labels_v2.sha256`, commit 3975288), code tagged
  `pre-heldout-v2`.
- **Run:** one `python run_site.py <url> --no-cache` per site on the tagged code, then
  `python -m eval.held_out --set v2 --semantic-judge`. The judge (gpt-4o-mini) made 21 calls at
  about $0.002 and upgraded 9 fields from incorrect to correct_semantic.
- **After the run:** no label, code or scoring change was made.
- **Uncertainty:** a single run, so there is no variance estimate (the dev set was run 3 times).
  8 sites and 120 field-scores give wide uncertainty: one site moves a per-field score by 12.5
  points.

## 3. Latency

| Site | timing.total_s |
| --- | ---: |
| cashfree.com | 99.6 |
| chargebee.com | 76.5 |
| cohere.com | 88.6 |
| elevenlabs.io | 78.5 |
| framer.com | 188.7 |
| leadsquared.com | 80.6 |
| mercury.com | 141.2 |
| miro.com | 114.2 |

- **p50:** 94.1 s against the 60 s target (not met).
- **Framer** hit the crawl time budget at 34 pages.
- **Page cap:** the 40-page cap was hit on the other 7 sites.

## 4. Where the 43 misses came from

Post-hoc diagnosis, read-only, no change made. Method: each run's `rejected`, `schema_errors` and
`classifier` records, and its cleaned-text snapshot (`data/clean/<slug>/`), which records the text of
every page and whether it was sent to the model.

**25: the model returned `not_found`.**

- **13:** the label's text was in the cleaned text that was sent to the model. This is a recall
  problem in one large extraction call over 34 to 40 pages.
- **12:** the model never had the text.
  - 4: the source page was not crawled.
  - 8: the page was crawled, but its menus, footers or logo alt text were removed by the cleaner.
- **0:** input-budget truncation did not occur in any case.

**17: evidence-gate rejections** (each becomes a `replacement:` not_found claim).

- **6, bare-label rule on `products.names`:** the quote equals the value. The rule exists to stop
  menu or card labels being reported as products (the Loom cases).
- **8, "quote not found in page text":**
  - 4 are formatting differences:
    - a dropped `%` sign (Cashfree);
    - table cells joined into one line (Cohere);
    - two real quotes joined on one line (Cohere);
    - a plan name and price that sit in separate table cells (Framer).
  - 4 are one invented Chargebee sentence reused for four fields.
- **3, "quote does not support the value":** including Mercury's company name, where the model cited
  the page title, which does not contain the word "Mercury".

**1: classifier abstention** (LeadSquared `pricing.revenue_model`).

**Harness check:** the dev and v2 paths use the same loader and scorer (`run_scoring_set()` in
`eval/baseline.py`). All 120 claims validated, and each run has one claim per field (no duplicates).
The score is a fair measurement of the pipeline against the labels.

## 5. Label-convention gap

`products.delivery_model` and `pricing.revenue_model` scored 0 of 16.

- **The mismatch:** the v2 labels are descriptive ("Software: <description>", "Subscription tiers
  plus transaction fees"); the system emits a bare term ("software", "subscription").
- **Scoring:** `pricing.revenue_model` is strict-match only. `products.delivery_model` goes to the
  semantic judge, which accepted none of its 7 cases.
- **Secondary figure:** a post-hoc rule, fixed before computing it, counts `delivery_model` as
  correct when the category word matches (the lowercase first word of the label before ":" equals
  the first word of the system value). It upgrades 7 cases, giving 49 of 120 = 40.8%.
  - This figure is secondary and does not replace 35%.
  - `revenue_model` is not comparable and was left as scored.

## 6. Caveats

- **ElevenLabs:** the home-page "Trusted by" logo strip showed an India-specific set from the
  labeller's location.
- **Framer prices:** INR in the label (labeller in Bengaluru), but USD to the crawler.
- **LeadSquared customers:** the home logo strip has slug-style alt text (for example `bharti_axa`,
  `unext_logo`), which does not count as names under the guide. Its customer label of 1 is therefore
  conservative.
- **Borderline label calls:**
  - ElevenLabs headquarters "London".
  - The EU-US Data Privacy Framework counted as a certification (ElevenLabs, Chargebee).
  - The pricing views chosen for Cohere and Chargebee.
  - Cashfree's RBI licences excluded as not certifications.
- **Rendered versus server text:** where the two differed, it is stated in each label file's notes.

## 7. Next steps (not done, not validated)

None of these was applied in this report.

1. Normalise formatting in the evidence gate (joined quotes, table cells, symbols).
2. A fallback extraction pass for list fields returned as `not_found`, over the few most likely
   pages.
3. Keep navigation, footer and logo alt text for the fields that need them.
4. Narrow the bare-label rule, only if the Loom regression still passes.
5. Short `delivery_model` and `revenue_model` label conventions in future sets.

Any of these must be measured on a fresh, blind set: the v2 sites are now development data.

**Update, 2026-10-11:** step 2, a fallback extraction pass for list fields returned as `not_found`, was
tried after the held-out run on branch `post-heldout-v2-fallback` and failed on the dev set: the 3-round
mean was 61.3% against 65.8% for the unchanged code run back to back, with unsupported verdicts rising
from 12 to 22. It was not merged. See `eval/FALLBACK_EXPERIMENT.md`. The 35% above remains the recorded
held-out result.
