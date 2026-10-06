#!/usr/bin/env python3
"""Week 4 held-out evaluation (Final PRD Section 12, the actual AC-02 gate).

AC-02 says "At least 80% accuracy across the agreed core fields on held-out websites" --
distinct from eval/baseline.py's DEV_SET, which Section 12 explicitly says is "never used for
tuning" and was only ever a Week 3 proxy signal. This script scores the 10 frozen held-out sites
(H1-H10, eval/benchmark_sites.md) the same way baseline.py scores the dev set, by calling the
shared eval/baseline.py:run_scoring_set() core so the two never drift apart on scoring logic,
per-field/per-site breakdown, or report shape.

Usage:
    python eval/held_out.py
    python eval/held_out.py --semantic-judge   # B-45, 2026-09-27 (fields widened B-46): see
                                                # eval/baseline.py's docstring -- opt-in, off by default

Prerequisite: each held-out site must already have a live `python run_site.py <url> --no-cache`
run on disk under data/runs/ -- this script makes no LLM or network call itself, it only reads
JSON already there (same design as baseline.py, so it also runs unchanged in this sandbox),
UNLESS `--semantic-judge` is passed, in which case it makes one additional LLM call per
still-incorrect verdict on one of wi.eval.scoring.FREE_TEXT_JUDGED_FIELDS.

Run-file resolution (2026-09-27): unlike baseline.py's DEV_SET, which hardcodes a confirmed
(label, run-file) pairing table because every dev-set run has actually been executed and its
slug observed, most of these 10 held-out sites have NEVER been run yet as of this script's
writing -- their post-redirect slug (e.g. does razorpay.com resolve to "razorpay_com.json" or
does it redirect to a www/regional subdomain, the way zerodha.com became
"www_zerodha_com.json"?) is genuinely unknown in advance. Guessing wrong would silently score
against a stale or wrong file, or (worse) another site's file. So this script resolves each
label's run file at execution time from its own "site" URL, deterministically, and REFUSES to
guess when more than one candidate file matches -- it reports the ambiguity and asks for the
exact filename instead of picking one, same "fail loudly, never silently" principle DEV_SET's
comment documents.

Also writes eval/held_out_report.json (mirrors eval/baseline_report.json's shape) and prints
whether the 80% AC-02 gate is met, both on the headline number and per-field, since the PRD's
own scoring rules (Section 12) and AC-09 require field-level reporting, not one blended pass/fail.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.baseline import build_semantic_judge, run_scoring_set  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

# The 10 frozen held-out sites (eval/benchmark_sites.md H1-H10). Label file -> the site's own
# registered domain fragment(s) to search for among data/runs/*.json, in priority order (a site
# that might resolve to a www-prefixed or regional subdomain lists that candidate first).
HELD_OUT_LABELS: List[Tuple[str, List[str]]] = [
    ("razorpay.json", ["razorpay_com"]),
    ("buffer.json", ["buffer_com"]),
    ("innovaccer.json", ["innovaccer_com"]),
    ("sarvamai.json", ["sarvam_ai"]),
    ("temenos.json", ["temenos_com"]),
    ("thoughtworks.json", ["thoughtworks_com", "www_thoughtworks_com"]),
    ("nobroker.json", ["nobroker_in", "www_nobroker_in"]),
    ("gong.json", ["gong_io", "www_gong_io"]),
    ("plaid.json", ["plaid_com"]),
    ("renaissancetech.json", ["rentec_com", "www_rentec_com"]),
]

AC_02_THRESHOLD = 0.80


def _resolve_run_file(candidates: List[str], run_dir: Path) -> Tuple[Optional[str], List[str]]:
    """Return (resolved_filename_or_None, all_matching_filenames_found). Tries each candidate
    slug in order (first real match wins); if a candidate slug matches nothing, falls back to a
    loose substring search across data/runs/*.json using the first candidate's domain word (e.g.
    "razorpay" from "razorpay_com") so a genuinely unexpected redirect slug is still found --
    but only auto-picks it when EXACTLY one file matches. Two or more matches is reported as
    ambiguous rather than guessed."""
    for candidate in candidates:
        exact = run_dir / f"{candidate}.json"
        if exact.exists():
            return exact.name, [exact.name]

    domain_word = re.split(r"[_.]", candidates[0])[0]
    loose_matches = sorted(
        p.name for p in run_dir.glob("*.json") if domain_word in p.name.lower()
    )
    if len(loose_matches) == 1:
        return loose_matches[0], loose_matches
    return None, loose_matches


def main() -> int:
    judge, model = build_semantic_judge("--semantic-judge" in sys.argv[1:])

    label_dir = ROOT / "eval" / "labels"
    run_dir = ROOT / "data" / "runs"
    report_path = ROOT / "eval" / "held_out_report.json"

    resolved_pairs: List[Tuple[str, str]] = []
    unresolved: List[Tuple[str, List[str]]] = []
    for label_file, candidates in HELD_OUT_LABELS:
        resolved, matches = _resolve_run_file(candidates, run_dir)
        if resolved is None:
            unresolved.append((label_file, matches))
        else:
            resolved_pairs.append((label_file, resolved))

    if unresolved:
        print("Could not confidently resolve a run file for these held-out sites:")
        for label_file, matches in unresolved:
            if matches:
                print(f"  - {label_file}: ambiguous, candidates found = {matches}")
            else:
                print(f"  - {label_file}: no run file found under data/runs/ yet "
                      f"(needs `python run_site.py <url> --no-cache` first)")
        print()

    if not resolved_pairs:
        print("No held-out runs resolved -- nothing to score. Run the pipeline on the held-out "
              "sites first (see eval/benchmark_sites.md for URLs).")
        return 1

    print(f"Resolved {len(resolved_pairs)}/{len(HELD_OUT_LABELS)} held-out sites to a run file:")
    for label_file, run_file in resolved_pairs:
        print(f"  {label_file} -> {run_file}")
    print()

    report, code = run_scoring_set(
        resolved_pairs, label_dir, run_dir, "held_out_set", report_path,
        f"{len(resolved_pairs)} held-out site(s)",
        semantic_judge=judge, semantic_judge_model=model,
    )
    if report is None:
        return code

    headline = report["overall"]["accuracy"]
    print(f"\nAC-02 gate (>= {AC_02_THRESHOLD:.0%} accuracy on held-out sites):")
    if headline is None:
        print("  n/a -- nothing scored")
    elif headline >= AC_02_THRESHOLD:
        print(f"  PASS -- {headline:.0%} >= {AC_02_THRESHOLD:.0%}")
    else:
        print(f"  NOT MET -- {headline:.0%} < {AC_02_THRESHOLD:.0%}")

    if len(resolved_pairs) < len(HELD_OUT_LABELS):
        print(f"  NOTE: only {len(resolved_pairs)}/{len(HELD_OUT_LABELS)} held-out sites scored "
              f"-- this is a partial gate check, not the final one, until every site has a run.")

    return code


if __name__ == "__main__":
    sys.exit(main())
