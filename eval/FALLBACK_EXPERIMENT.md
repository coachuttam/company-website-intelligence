# Fallback extraction experiment (not merged)

Tried after the held-out v2 run, 2026-10-10 to 2026-10-11. It lowered the dev score and was not
merged. The shipped pipeline is still the tagged code (`pre-heldout-v2`) that produced the recorded
35% held-out result (`eval/HELDOUT_V2_REPORT.md`). Nothing in this experiment touched the v2 labels
or the v2 run.

## What was tried

A fallback extraction pass for list fields the main pass returned as `not_found`:

- **Where:** branch `post-heldout-v2-fallback`, commits e3c9487 and f242117 (B-98),
  `EXTRACTION_LOGIC_VERSION` 27.
- **One extra call:** after the main extraction, evidence gate and classifier, a single extra model
  call per run asked for only the still-missing fields. Those fields are customers.segments,
  customers.industries, traction.named_customers, traction.partnerships,
  comparisons.named_alternatives and traction.certifications.
- **Pages:** at most 6 already-cleaned pages, chosen by a generic score (path words and text
  keywords, top 4 per field).
- **Gate:** the evidence gate was unchanged.
- **Exclusions:**
  - `company_identity.headquarters` was removed before the run, because Decision (d) says an address
    is not a headquarters statement and the gate does not apply Decision (d).
  - `products.names` was never retried.

## Why

The v2 diagnosis found that in 13 of the 25 misses where the model returned `not_found`, the label's
text was in the cleaned text the model had been sent. That looked like a recall problem in one large
call over 34 to 40 pages, which a smaller second call might fix.

## Method

- **Sites:** the 5 dev sites (Calendly, Loom, Typeform, Notion, SimpleStores).
- **Rounds:** 3. In each round, main and the fallback branch ran back to back, alternating which went
  first (main first in rounds 1 and 3, fallback first in round 2).
- **Commands:** `python run_site.py <url> --no-cache`, then
  `python eval/baseline.py --semantic-judge` and `python eval/latency_report.py`.
- **Cost:** about $0.23 estimated (main $0.096, fallback $0.132).
- **Files:**
  - Reports and scripts: `eval/fallback_experiment/` (`dev_compare.sh`, `summarise_dev_compare.py`,
    `summary.txt`).
  - Run files: kept locally in `data/archive/dev_compare/`, not committed.

## Results

| Build | Round 1 | Round 2 | Round 3 | Mean |
| --- | ---: | ---: | ---: | ---: |
| main (control) | 61.3 | 66.7 | 69.3 | **65.8** |
| fallback | 60.0 | 62.7 | 61.3 | **61.3** |

Verdicts summed over 3 rounds (225 field-scores per build):

| Build | correct | partial | semantic | abstention | incorrect | miss | unsupported |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| main | 38 | 24 | 29 | 57 | 27 | 38 | 12 |
| fallback | 39 | 22 | 30 | 47 | 40 | 25 | 22 |

### Fields that changed

Fields that changed by 2 or more verdicts over the 3 rounds (fallback minus main):

| Field | Change | Cause |
| --- | --- | --- |
| customers.industries | abstention −5, unsupported +5, miss −3, incorrect +3 | fallback |
| traction.partnerships | abstention −5, unsupported +5 | fallback |
| traction.named_customers | miss −6, incorrect +6 | fallback |
| customers.segments | miss −2, incorrect +2 | fallback |
| traction.certifications | miss −3, partial +3 | fallback (the only gain) |
| products.names | partial −2, incorrect +2 | run-to-run noise (not retried) |
| pricing.public_plans | correct +2, partial −3, miss +2 | run-to-run noise (not retried) |
| pricing.free_trial | incorrect +2 | run-to-run noise (not retried) |

### Fallback records

- **Calls:** a call was made on 5 of 5 runs in every round, with no skips and no errors.
- **Fields, per round:**

  | Round | Attempted | Filled | Rejected | Fallback seconds (5 runs) |
  | --- | ---: | ---: | ---: | ---: |
  | 1 | 23 | 10 | 2 | 28.4 |
  | 2 | 22 | 7 | 2 | 27.6 |
  | 3 | 23 | 8 | 3 | 26.6 |

- **Total filled:** 25 fields over the 3 rounds. Every one, with its value and quote, is listed in
  `eval/fallback_experiment/summary.txt`, section g.

### Latency and pass test

- **Latency** (`timing.total_s`): main p50 83.4 s and p95 144.7 s; fallback p50 86.4 s and
  p95 152.5 s. The fallback added about 5.6 s per run on average.
- **Pass test** (set before the run):

  | Test | Result |
  | --- | --- |
  | (1) fallback mean ≥ main mean − 1 (61.3 vs 64.8) | FAIL |
  | (2) fallback unsupported ≤ main + 3 (22 vs 15) | FAIL |
  | (3) at least 5 fields filled (25) | PASS |

  **Overall: FAIL.**

## Why it failed

On the dev set, most of the fields the fallback retries are correct abstentions: about 19 to 20 per
round, against 6 to 8 misses. Filling them can only hurt unless the fill is right, and most fills
were real text about the wrong thing:

- **customers' industries:** Calendly "SaaS", from the ClickUp customer story; Loom "Financial
  Services", from the Brex story; Notion "Retail", from the Faire story.
- **customers' users:** Typeform "customers" Azra Games, BombBomb and Timely are users of Typeform's
  customer Gated.
- **the acquirer as a partner:** Loom "Atlassian".
- **an integration as a partner:** Loom "Salesforce", from "Salesforce integration (beta)".
- **laws counted as certifications:** Loom GDPR and CCPA.
- **no company named:** SimpleStores "country distributors in the Gulf, Malaysia and Europe".

The evidence gate checks that a quote exists on a fetched page and contains the value. It does not
check that the value is about this company and belongs to this field.

- **Certifications, the only gain (+3):** the three Loom fills of GDPR (and CCPA) matched Loom's dev
  label, which lists SOC 2, GDPR and CCPA (the dev labels predate Decision (a), which treats laws as
  not certifications).
- **Typeform certifications:** the one fill that was real and on topic, Typeform's list from its
  security help page in round 1 (SOC 2 Type II, ISO 27001/27017/27018/42001, CSA STAR, PCI DSS),
  scored *unsupported*, because Typeform's dev label for the field is `not_found`.

The net effect was about 11 fewer right calls, which accounts for nearly all of the 4.5-point drop.

## Decision

Not merged. The branch `post-heldout-v2-fallback` is kept for reference. The shipped pipeline and
the recorded held-out result (35%, tag `pre-heldout-v2`) are unchanged.

## What a better attempt would need (not done)

- **A scope check** that the quote is about the company itself, not a customer, a customer's users
  or a third party.
- **Field-specific filters:** laws are not certifications, integrations and acquirers are not
  partnerships, and addresses are not headquarters (the labelling guide's Decisions (a), (b) and (d)).
- **A fresh blind set to evaluate it on.** The v2 and dev sites are now both development data.
