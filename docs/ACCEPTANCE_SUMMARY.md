# Acceptance summary (AC-01 to AC-12)

Status as of 2026-10-11. Every figure below is taken from a report already in the repo; none comes
from a new measurement.

**The recorded held-out headline is 35%** (held-out set v2, tag `pre-heldout-v2`). Later development
work is measured on the 13 development sites only (`eval/DEV13_RESULTS.md`), which are not held-out
numbers.

| # | Criterion (short) | Status | Recorded figure | Evidence |
| --- | --- | --- | --- | --- |
| AC-01 | ≥90% of returned claims have valid evidence | Met | 100% of returned extracted or inferred claims passed the evidence gate (dev, 3 rounds) | `docs/ERROR_REVIEW.md` (AC-11 breakdown); `eval/check_gate.py` |
| AC-02 | ≥80% accuracy on held-out sites | **Not met** | 35% (42 of 120 field-scores) on held-out set v2; post-hoc category-normalised 45.8%, secondary only | `eval/HELDOUT_V2_REPORT.md` |
| AC-03 | No unsupported value presented as directly extracted | Met | No separate figure: enforced by the gate and tested (B-04, B-05, B-09) | `tests/BEHAVIOURS.md`, `wi/validate/evidence.py` |
| AC-04 | `not_found` when evidence is insufficient | Partial | Abstention quality 85.5% on dev; 4 unsupported of 120 on v2 | `docs/ERROR_REVIEW.md`; `eval/HELDOUT_V2_REPORT.md` |
| AC-05 | New supported site needs no company-specific code | Met | No separate figure: the same code ran 13 sites, and no site-specific rules are allowed | `eval/DEV13_RESULTS.md`; `CLAUDE.md` rules |
| AC-06 | Raw, cleaned, claims and profile kept separate | Met | No separate figure: cleaned text in `data/clean/` snapshots (raw HTML kept as a checksum only), claims and profile as separate keys of the run JSON | README "The run JSON"; B-88 |
| AC-07 | Repeat cached runs are structurally consistent | Met | No separate figure: tested (B-17, B-21) | `tests/BEHAVIOURS.md`, `tests/test_cache.py` |
| AC-08 | Reproducible by a second developer | Partial | A fresh unzip passes setup, tests (637 passed, 3 skipped on 2026-10-11) and the sample check/render; steps that need an API key have not been checked by a second developer | README "Starting from the handoff files" |
| AC-09 | Results reported per field | Met | Per-field tables for dev and v2 | `eval/baseline_report*.json`; `eval/HELDOUT_V2_REPORT.md` |
| AC-10 | p50/p95 latency, tokens and cost reported | Partial | Reported. p50 79.9–91.9 s on dev and 94.1 s on v2, against 60 s (missed); p95 132–134 s on dev, against 180 s (met); mean cost $0.0061–0.0062 per site, against $0.10 (met) | `eval/latency_report_cmp_C_nc1-3.json`; `eval/HELDOUT_V2_REPORT.md` |
| AC-11 | Coverage, evidence, extraction, inference, conflicts, abstention reported separately | Met (dev); partial (v2) | Dev: crawl coverage 100%, evidence 100%, extraction 83.6%, inference 80.0%, conflicts 0, abstention 85.5%. v2: extraction 61%, inference 25%, conflicts 0 | `docs/ERROR_REVIEW.md`; `eval/HELDOUT_V2_REPORT.md` |
| AC-12 | News metrics reported separately (if the spike runs) | Partial | Company-own feeds only. Duplicate rate 0%; source access 33% of URLs; p50 13.7 s; $0. Entity-match precision not measurable (no third-party candidate found) | `docs/NEWS_SPIKE.md` |

## Decisions needed from Abhishek

- **Section 14 items:**
  - the Section 13 parameters;
  - the benchmark split;
  - the confidence rule;
  - the "supported website" definition;
  - the cut order;
  - news shown only as labelled third-party events.
- **Re-approval of PRD v1.1:** §12.1 (held-out set v2) and the note that the dev set has 5 sites, not 8.
- **Jev:** written confirmation of the verbal approval given on 2026-10-06.
- **Latency (AC-10):**
  - whether p50 is measured end to end;
  - whether to change the Section 13 crawl parameters (1 request per second, 40 pages), which
    dominate latency, to reach 60 s.

## Not done or cut

- **DSPy or prompt-optimisation trial (Week 3):** not done; it is third in the Section 10 cut order.
- **Held-out set v3:** not built. It is needed for any new held-out claim, for example about the
  merged cleaner (B-100) and products.names evidence (B-102) changes; see `eval/DEV13_PROTOCOL.md`.
- **News, cut line 2 and beyond:** not built. That covers third-party article fetching (needed before
  anything can be called corroborated) and small-model matching. Built so far:
  - the company-own snapshot (B-104);
  - news on the rendered page (B-105);
  - GDELT headline search with rules only (B-106).
- **Not merged:**
  - fallback extraction pass (B-98), which lowered the dev score: `eval/FALLBACK_EXPERIMENT.md`;
  - fix3 price-window evidence (B-103), which failed its pass test: `eval/DEV13_RESULTS.md`.
