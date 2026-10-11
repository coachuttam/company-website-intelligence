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
