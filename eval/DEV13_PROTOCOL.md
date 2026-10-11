# 13-site development comparison (dev5 + v2)

**Purpose.** To compare a candidate change with the unchanged code (the control) on more sites than
the 5 dev sites alone. Five sites are too few to separate a real gain from run-to-run noise.

**Sites.** The 5 dev sites (Calendly, Loom, Typeform, Notion, SimpleStores) and the 8 held-out v2
sites (Cashfree, Chargebee, Cohere, ElevenLabs, Framer, LeadSquared, Mercury, Miro). Together they
give 75 + 120 = 195 field-scores per run.

**v2 is development data from now on.** The v2 sites were run once on the tagged code
(`pre-heldout-v2`), and that result, 35% strict, stays the recorded held-out headline
(`eval/HELDOUT_V2_REPORT.md`). Every later run on them, including this comparison, is development use.
The pre-fix v2 run files are preserved in `data/archive/heldout_v2_prefix/` (checked by SHA256SUMS
before every comparison).

**Rules.**
- **Order:** the control and each candidate run back to back in every round, rotating which goes first.
- **Commands:**
  - `run_site.py <url> --no-cache` on all 13 sites;
  - `eval/baseline.py --semantic-judge --normalised` for dev5;
  - `python -m eval.held_out --set v2 --semantic-judge --normalised` for v2.
- **Failures:** no retries; stop at the first failure.
- **Labels and files:** labels are never edited to match an output. Reports and run files are kept in
  `data/archive/dev13/` and are not committed.
- **Commands:** `eval/dev13_compare.sh <rounds> <control> <candidate> ...`, then
  `python eval/dev13_summary.py <control> <candidate> ...`.

**Pass test** (each candidate against the control, over all rounds):
1. The combined strict mean headline is at least 1.0 point above the control's.
2. The total unsupported verdicts are at most 3 more than the control's.
3. No single field has more than 3 extra incorrect-or-unsupported verdicts.

The summary also prints the control's round-to-round spread, so a +1.0 gain can be judged against
noise. The normalised headline is shown for reading only; the pass test uses the strict one.

**Next held-out claim.** A fresh set, v3, will be labelled blind under one convention before any run,
frozen by checksum and tag, and run once. Any change accepted here must still be confirmed there.
