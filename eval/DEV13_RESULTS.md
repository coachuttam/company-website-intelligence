# 13-site comparison: main versus cleaner-alt-nav (2026-10-11)

**What was run.** `eval/dev13_compare.sh 2 main cleaner-alt-nav`, following `eval/DEV13_PROTOCOL.md`:
13 sites (5 dev and 8 v2), 2 rounds, each round running both refs back to back with the first ref
rotated, `--no-cache`, `--semantic-judge --normalised`. Estimated cost about $0.38 (main $0.187,
cleaner $0.190).

**What the candidate changes** (B-100): logo and image labels from the main content, and homepage
navigation text, are added to the cleaned text.

## Headlines (strict / normalised, %)

| Build | Round | dev5 (75) | v2 (120) | Combined (195) |
| --- | --- | --- | --- | --- |
| main | 1 | 66.7 / 69.3 | 34.2 / 43.3 | 46.7 / 53.3 |
| main | 2 | 62.7 / 65.3 | 35.8 / 45.8 | 46.2 / 53.3 |
| **main** | **mean** | 64.7 / 67.3 | 35.0 / 44.6 | **46.4 / 53.3** |
| cleaner | 1 | 68.0 / 70.7 | 38.3 / 48.3 | 49.7 / 56.9 |
| cleaner | 2 | 66.7 / 70.7 | 40.0 / 49.2 | 50.3 / 57.4 |
| **cleaner** | **mean** | 67.3 / 70.7 | 39.2 / 48.8 | **50.0 / 57.2** |

The control's combined strict score moved 0.5 points between its two rounds (dev5 alone moved 4.0).

## Verdict totals (2 rounds, dev5 + v2)

| Build | correct | partial | semantic | abstention | incorrect | miss | unsupported |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| main | 45 | 37 | 36 | 63 | 86 | 108 | 15 |
| cleaner | 45 | 51 | 39 | 60 | 78 | 99 | 18 |

## Fields that changed by 2 or more verdicts (cleaner minus main)

| Field | Change |
| --- | --- |
| customers.industries | partial +4, miss −4 |
| traction.named_customers | partial +3, miss −2 |
| traction.partnerships | partial +2, miss −3 |
| comparisons.named_alternatives | correct +2, miss −2 |
| products.names | partial +2, incorrect −5, miss +3 |
| pricing.public_plans | partial +3, incorrect −4, miss +2 |
| products.delivery_model | miss −2 |
| customers.segments | incorrect +3, miss −4 |
| pricing.free_trial | unsupported +2, abstention −2, incorrect −2, miss +2 |

## Latency and pass test

- **Latency** (`timing.total_s`): main p50 83.1 s and p95 167.1 s; cleaner p50 85.9 s and p95 165.6 s.
- **Pass test:**

  | Test | Result |
  | --- | --- |
  | Combined strict mean +3.6 points (needs ≥ +1.0) | PASS |
  | Unsupported +3 (limit +3) | PASS |
  | Worst field +3 incorrect-or-unsupported (customers.segments; limit 3) | PASS |

  **Overall: PASS.**

## Caveats

- **Only 2 rounds.**
- **Unsupported is exactly at the limit (+3).**
- **v2 is development data from now on**, so the v2 columns are not held-out numbers. The recorded
  held-out headline is unchanged: 35% strict, tag `pre-heldout-v2` (`eval/HELDOUT_V2_REPORT.md`).
- **Raw data:** reports and run files are in `data/archive/dev13/`, local only.

## fix1: sentence evidence for bare products.names quotes (B-102), 2026-10-11

**What was run.** `eval/dev13_compare.sh 2 main fix1-bare-label-evidence`. The control is `main` at
099ec9e, which already includes the cleaner change.

| Build | Round | dev5 | v2 | Combined |
| --- | --- | --- | --- | --- |
| main | 1 | 68.0 / 72.0 | 38.3 / 48.3 | 49.7 / 57.4 |
| main | 2 | 68.0 / 72.0 | 36.7 / 46.7 | 48.7 / 56.4 |
| **main** | **mean** | 68.0 / 72.0 | 37.5 / 47.5 | **49.2 / 56.9** |
| fix1 | 1 | 70.7 / 74.7 | 39.2 / 49.2 | 51.3 / 59.0 |
| fix1 | 2 | 68.0 / 72.0 | 38.3 / 47.5 | 49.7 / 56.9 |
| **fix1** | **mean** | 69.3 / 73.3 | 38.8 / 48.3 | **50.5 / 57.9** |

Figures are strict / normalised (%). The control's spread between rounds was 1.0 point.

**products.names:** miss −12, partial +7, correct +2, incorrect +3.
- Of the 3 extra incorrect answers, 2 are Chargebee naming (one per round): "Chargebee Billing"
  against the label's "Billing" scores as disjoint. The third is Loom round 1, which had no upgrades,
  so it is run-to-run noise.
- 39 items were upgraded over the 2 rounds.

**Unsupported:** unchanged at 16.

**Pass test:**

| Test | Result |
| --- | --- |
| Combined strict +1.3 (needs ≥ +1.0) | PASS |
| Unsupported +0 | PASS |
| Worst field +3 incorrect (limit 3) | PASS |

**Overall: PASS. Cost:** about $0.38.

**Caveats:**
- **Only 2 rounds,** and the +1.3 gain is barely above the 1.0-point spread.
- **v2 is development data,** so the v2 columns are not held-out numbers. The held-out headline is
  unchanged (35%, `pre-heldout-v2`).
- **Raw data** is in `data/archive/dev13/`; the earlier main-versus-cleaner files are in
  `data/archive/dev13_main-vs-cleaner/`. Both are local only.

## fix3: price-window evidence for public_plans (B-103), not merged

**What was run.** Branch `fix3-plan-price-evidence` (47ea010), compared with `main` (52e29d5) using
`eval/dev13_compare.sh 2 main fix3-plan-price-evidence`.

**Result.** Combined strict mean 51.3%, against 51.5% for the control (it needed +1.0; the control's
spread between rounds was 1.5 points). It fails the pass test, so the branch is kept but not merged.

**Why it did not help.**
- **ElevenLabs** was the only site whose public_plans improved: its 7 upgraded plan quotes found the
  plan name and price in separate cells.
- **Framer:** the upgrades found real USD prices, but the label records INR (geo-dependent prices),
  so the field stayed a miss.
- **Other sites:** the remaining plan misses and disjoint answers were not "quote not found" cases,
  so the fix could not reach them.

**Cost:** about $0.38.

**Planned but not done.** A further cleaner exploration (what else the cleaner drops beyond menus,
footers and logo text) was planned after the cleaner merge but not carried out.
