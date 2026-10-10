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
    python eval/held_out.py --set v2 [--semantic-judge]   # B-97: held-out set v2 (see below)

Held-out set v2 (B-97, 2026-10-10): `--set v2` scores the 8 sites of eval/benchmark_sites_v2.md
instead of the old 10 (which are contaminated and stay the default only so their results remain
reproducible). The v2 label files are found the way eval/checksum_labels.py finds them (split
"held_out_v2" in eval/labels/heldout_v2/), each site's URL comes from its label file's
labeling_metadata.website_url, and the run-file candidates are built from that URL the way
run_site.py names its output (www. dropped, dots -> underscores). Before anything is scored the
labels must match eval/labels_v2.sha256 (`eval/checksum_labels.py --verify`); a missing or
mismatched checksum file refuses the run. Scoring is the same run_scoring_set() call; the report
goes to eval/held_out_v2_report.json so the old eval/held_out_report.json is never overwritten.

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

import json
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.baseline import build_semantic_judge, run_scoring_set  # noqa: E402
from eval.checksum_labels import v2_label_files, verify  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
HELD_OUT_LABEL_DIR = ROOT / "eval" / "labels" / "heldout_v1_archived"
V2_LABEL_DIR = ROOT / "eval" / "labels" / "heldout_v2"
V2_CHECKSUM_FILE = ROOT / "eval" / "labels_v2.sha256"
V2_REPORT_PATH = ROOT / "eval" / "held_out_v2_report.json"

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


def _selected_set(argv: List[str]) -> Optional[str]:
    """B-97: "v1" (the old 10, the default) or "v2" from `--set v1|v2`; None for anything else."""
    if "--set" not in argv:
        return "v1"
    i = argv.index("--set")
    value = argv[i + 1] if i + 1 < len(argv) else None
    return value if value in ("v1", "v2") else None


def v2_sites(label_dir: Path = V2_LABEL_DIR) -> List[Tuple[str, str, List[str]]]:
    """B-97: (label_file, website_url, run-file candidates) for every held-out v2 label file, in
    file-name order. The URL is the label's own labeling_metadata.website_url; the candidates
    follow run_site.py's slug (validate_company_url() drops "www.", then dots -> underscores),
    with a www_ variant second for a run made before that rule, as HELD_OUT_LABELS lists."""
    sites = []
    for label_file in v2_label_files(label_dir):
        doc = json.loads((label_dir / label_file).read_text(encoding="utf-8"))
        url = doc["labeling_metadata"]["website_url"]
        host = (urlparse(url).hostname or "").lower()
        slug = (host[4:] if host.startswith("www.") else host).replace(".", "_")
        sites.append((label_file, url, [slug, "www_" + slug]))
    return sites


def main_v2(argv: List[str], label_dir: Path = V2_LABEL_DIR, checksum_file: Path = V2_CHECKSUM_FILE,
            run_dir: Path = ROOT / "data" / "runs", report_path: Path = V2_REPORT_PATH) -> int:
    """B-97: score held-out set v2. Same resolution, scoring and AC-02 printout as main()'s old
    set; only the sites, label folder, checksum guard and report path differ."""
    sites = v2_sites(label_dir)
    print(f"Held-out set v2: {len(sites)} site(s):")
    for label_file, url, _ in sites:
        print(f"  {url}  ({label_file})")
    print()

    ok, message = verify(label_dir, checksum_file)
    if not ok:
        print(f"REFUSED: the held-out v2 labels are not frozen -- {message}. Label all sites, run "
              f"`python eval/checksum_labels.py --write`, tag the code, then score. Nothing was scored.")
        return 1
    print(f"Checksum OK ({checksum_file.name}): {message}\n")

    judge, model = build_semantic_judge("--semantic-judge" in argv)

    resolved_pairs: List[Tuple[str, str]] = []
    unresolved: List[Tuple[str, List[str]]] = []
    for label_file, _url, candidates in sites:
        resolved, matches = _resolve_run_file(candidates, run_dir)
        if resolved is None:
            unresolved.append((label_file, matches))
        else:
            resolved_pairs.append((label_file, resolved))

    if unresolved:
        print("Could not confidently resolve a run file for these held-out v2 sites:")
        for label_file, matches in unresolved:
            if matches:
                print(f"  - {label_file}: ambiguous, candidates found = {matches}")
            else:
                print(f"  - {label_file}: no run file found under data/runs/ yet "
                      f"(needs `python run_site.py <url> --no-cache` first)")
        print()

    if not resolved_pairs:
        print("No held-out v2 runs resolved -- nothing to score. Run the pipeline on the v2 sites "
              "first (see eval/benchmark_sites_v2.md).")
        return 1

    print(f"Resolved {len(resolved_pairs)}/{len(sites)} held-out v2 sites to a run file:")
    for label_file, run_file in resolved_pairs:
        print(f"  {label_file} -> {run_file}")
    print()

    report, code = run_scoring_set(
        resolved_pairs, label_dir, run_dir, "held_out_v2_set", report_path,
        f"{len(resolved_pairs)} held-out v2 site(s)",
        semantic_judge=judge, semantic_judge_model=model,
    )
    if report is None:
        return code

    headline = report["overall"]["accuracy"]
    print(f"\nAC-02 gate (>= {AC_02_THRESHOLD:.0%} accuracy on held-out sites, set v2):")
    if headline is None:
        print("  n/a -- nothing scored")
    elif headline >= AC_02_THRESHOLD:
        print(f"  PASS -- {headline:.0%} >= {AC_02_THRESHOLD:.0%}")
    else:
        print(f"  NOT MET -- {headline:.0%} < {AC_02_THRESHOLD:.0%}")

    if len(resolved_pairs) < len(sites):
        print(f"  NOTE: only {len(resolved_pairs)}/{len(sites)} held-out v2 sites scored "
              f"-- this is a partial gate check, not the final one, until every site has a run.")

    return code


def main(argv: Optional[List[str]] = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    selected = _selected_set(argv)
    if selected is None:
        print("--set takes v1 (the old 10 sites, the default) or v2 (held-out set v2).")
        return 2
    if selected == "v2":
        return main_v2(argv)

    judge, model = build_semantic_judge("--semantic-judge" in argv)

    label_dir = HELD_OUT_LABEL_DIR
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
