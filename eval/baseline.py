#!/usr/bin/env python3
"""Week 3 field-level accuracy baseline (Final PRD Section 12, AC-02/AC-09/AC-11).

Scores each of the 5 dev-set runs already produced by run_site.py against its hand-labelled
answer key in eval/labels/dev/, using wi.eval.scoring's pure comparison logic. This makes no LLM
or network call itself -- it only reads JSON already on disk -- so, unlike run_site.py, it runs
the same everywhere including this sandboxed environment.

Usage:
    python eval/baseline.py
    python eval/baseline.py --semantic-judge   # B-45, 2026-09-27: also makes an LLM call per
                                                # still-incorrect free-text field (see below)

Prints:
  - a per-site summary (raw verdict counts + headline accuracy)
  - a per-field summary across all 5 sites (AC-09: reported per field, not one blended score)
  - an overall summary, plus the extraction/inference/conflict breakdown AC-11 asks to keep
    separate
  - full label-vs-system detail for every non-"correct"/non-"correct_abstention" verdict, so a
    human can spot-check cases the strict, non-paraphrase-aware normalisation may have scored
    unfairly (see wi/eval/scoring.py's module docstring)

Also writes eval/baseline_report.json with the same data, for diffing against a future baseline
(e.g. after the Week 3 prompt-optimisation trial).

Week 4 (2026-09-27): the actual AC-02 gate ("80% accuracy ... on held-out websites") is scored by
the sibling script eval/held_out.py, not this one -- this file's DEV_SET was, and remains, never
used for that gate (Section 12: held-out sites are frozen before Week 4 and never used for
tuning). The scoring core below was factored out into run_scoring_set() specifically so
held_out.py could reuse it byte-for-byte on a different (label, run) pair list and a different
report filename, without duplicating the per-site/per-field/overall/spot-check logic or risking
the two scripts drifting apart. main() below is unchanged from Week 3 -- same DEV_SET, same
console output, same eval/baseline_report.json -- so this remains the historical dev-set gate
record it always was.

`--semantic-judge` (B-45, 2026-09-27; fields widened B-46): opt-in only, off by default. Without
it, this script makes no LLM or network call, exactly as always. With it, every still-`incorrect`
verdict on one of wi.eval.scoring.FREE_TEXT_JUDGED_FIELDS (company_identity.description,
products.delivery_model, customers.segments, pricing.sales_motion) is run through wi.eval.
scoring's LLM-as-judge check before anything is printed or written to the report -- see that
module's docstring for the full rationale (Uttam's explicit choice, given the tradeoff against
this script's own no-LLM guarantee)
and wi.extract.llm.OpenAIJudgeCompleter for the judge itself. Needs OPENAI_API_KEY in .env, same
as run_site.py; missing it just prints a warning and scores without the judge rather than erroring.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402

from wi.eval.scoring import (  # noqa: E402
    FieldScore, Verdict, apply_semantic_judging, extraction_vs_inference, is_right_call,
    score_run, summarize,
)
from wi.extract.fields import FIELDS  # noqa: E402
from wi.extract.pricing import estimate_cost_usd  # noqa: E402
from wi.schemas.claim import Claim  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEV_LABEL_DIR = ROOT / "eval" / "labels" / "dev"

# Explicit label-file -> run-file pairing, not inferred from the label's site URL. A run's output
# filename is slugged from wherever the crawl actually landed after redirects (e.g. zerodha.com's
# run used to be "www_zerodha_com.json" because that site redirects to its www subdomain) --
# that's crawl-time behaviour that can change between runs, so guessing it at eval time risks
# silently scoring the wrong file, or the previous run's, instead of failing loudly. Five sites,
# so a hardcoded, readable table costs nothing.
#
# DEV SET REPLACED 2026-09-28 (Uttam's decision, methodology-contamination review): the original
# 5 sites (Basecamp, Darwinbox, Zerodha, Bajaj Auto, thoughtbot) are archived at
# eval/labels/archive_old_dev/, not deleted. New dev set: Calendly, Loom, Typeform, Notion,
# SimpleStores.
#
# UNCONFIRMED run-file slugs below: unlike the original table (built only after each site had
# actually been crawled and its post-redirect slug observed, per the paragraph above), no run has
# been made against these 5 new sites yet -- crawling was explicitly deferred. Each run_file value
# is a best-guess slug (domain from the approved URL, dots -> underscores, matching run_site.py's
# `slug = approved_domains[0].replace(".", "_")`), NOT a confirmed one. The first real
# `python run_site.py <url> --no-cache` for each site may resolve to a different slug (e.g. a www-
# or region-prefixed subdomain, the same way zerodha.com did) -- verify and correct the
# corresponding line below after that first run, before trusting eval/baseline.py's output.
DEV_SET: List[Tuple[str, str]] = [
    # Confirmed 2026-09-28 against real run_site.py output (Uttam's machine, real network
    # access) -- validate_company_url() strips a leading "www." before building the slug,
    # so loom/typeform/notion have no www_ prefix even though their URLs do.
    ("calendly.json", "calendly_com.json"),
    ("loom.json", "loom_com.json"),
    ("typeform.json", "typeform_com.json"),
    ("notion.json", "notion_com.json"),
    ("simplestores.json", "simplestores_in.json"),
]


def _load_claims(run_path: Path) -> List[Claim]:
    data = json.loads(run_path.read_text(encoding="utf-8"))
    raw_claims = data["claims"] if isinstance(data, dict) else data
    claims = []
    for raw in raw_claims:
        try:
            claims.append(Claim(**raw))
        except ValidationError as e:
            print(f"  WARNING: skipping schema-invalid claim in {run_path.name}: {e.errors()[0]['msg']}")
    return claims


def _print_verdict_counts(counts: dict, total: int, indent: str = "  ") -> None:
    # B-45: correct_partial/correct_semantic grouped right after correct/correct_abstention --
    # they're both "right call" verdicts (see Verdict's own docstring), just via a looser rule.
    order = ["correct", "correct_partial", "correct_semantic", "correct_abstention",
              "incorrect", "miss", "unsupported", "conflicting"]
    parts = [f"{name}={counts[name]}" for name in order if counts[name]]
    print(f"{indent}{', '.join(parts) if parts else 'nothing scored'} (of {total})")


def run_scoring_set(
    site_set: List[Tuple[str, str]],
    label_dir: Path,
    run_dir: Path,
    set_key: str,
    report_path: Path,
    per_field_heading: str,
    semantic_judge=None,
    semantic_judge_model: Optional[str] = None,
) -> Tuple[Optional[dict], int]:
    """Score one named (label_file, run_file) pair list end-to-end: per-site, per-field (AC-09),
    overall + extraction/inference/conflict breakdown (AC-11), and a human-spot-check listing.
    Prints exactly what baseline.py's Week 3 main() always printed for DEV_SET, parameterised so
    held_out.py can reuse it unchanged for HELD_OUT_SET (see this module's docstring). Returns
    (report_dict_or_None, exit_code); a None report means nothing was scored.

    `semantic_judge`/`semantic_judge_model` (B-45, 2026-09-27): when both are given (only when
    the caller passed `--semantic-judge`), each site's scores are passed through
    wi.eval.scoring.apply_semantic_judging() right after score_run(), upgrading eligible
    `incorrect` free-text verdicts to `correct_semantic` before anything downstream (per-site,
    per-field, overall, the report file) sees them. Left as None by default -- this function
    makes no LLM call under any circumstance unless the caller explicitly opts in."""
    all_scores: List[Tuple[str, FieldScore]] = []  # (site_name, score)
    per_site_results = {}
    missing = []
    scored_sites = []

    for label_file, run_file in site_set:
        label_path, run_path = label_dir / label_file, run_dir / run_file
        if not label_path.exists() or not run_path.exists():
            missing.append((label_file, run_file))
            continue

        label_doc = json.loads(label_path.read_text(encoding="utf-8"))
        claims = _load_claims(run_path)
        scores = score_run(label_doc, claims)
        if semantic_judge is not None:
            scores = apply_semantic_judging(scores, semantic_judge, semantic_judge_model)
        site_name = label_file.removesuffix(".json")
        scored_sites.append(site_name)
        all_scores.extend((site_name, s) for s in scores)

        site_summary = summarize(scores)
        per_site_results[site_name] = {
            "counts": site_summary["counts"], "accuracy": site_summary["accuracy"],
        }
        print(f"{site_name}:")
        _print_verdict_counts(site_summary["counts"], site_summary["total"])
        acc = site_summary["accuracy"]
        print(f"  accuracy (correct + correct_abstention / total): {acc:.0%}" if acc is not None
              else "  accuracy: n/a")

    if missing:
        print("\nSkipped (missing label or run file):")
        for label_file, run_file in missing:
            print(f"  - {label_file} / {run_file}")

    if not all_scores:
        print(f"\nNo {set_key} pairs available -- nothing to score.")
        return None, 1

    flat_scores = [s for _, s in all_scores]

    print(f"\nPer-field summary ({per_field_heading} -- AC-09, reported per field):")
    per_field_results = {}
    for field in FIELDS:
        field_scores = [s for s in flat_scores if s.field == field]
        field_summary = summarize(field_scores)
        per_field_results[field] = {
            "counts": field_summary["counts"], "accuracy": field_summary["accuracy"],
        }
        acc = field_summary["accuracy"]
        acc_str = f"{acc:.0%}" if acc is not None else "n/a"
        print(f"  {field}: {acc_str}", end="  ")
        _print_verdict_counts(field_summary["counts"], field_summary["total"], indent="")

    overall_summary = summarize(flat_scores)
    breakdown = extraction_vs_inference(flat_scores)
    print("\nOverall (all sites, all fields):")
    _print_verdict_counts(overall_summary["counts"], overall_summary["total"])
    acc = overall_summary["accuracy"]
    print(f"  headline accuracy: {acc:.0%}" if acc is not None else "  headline accuracy: n/a")
    ext_acc = breakdown["extraction_accuracy"]
    inf_acc = breakdown["inference_accuracy"]
    print(f"  extraction accuracy (AC-11): {ext_acc:.0%}" if ext_acc is not None else
          "  extraction accuracy (AC-11): n/a (no extracted claims scored)")
    print(f"  inference accuracy (AC-11): {inf_acc:.0%}" if inf_acc is not None else
          "  inference accuracy (AC-11): n/a (no inferred claims scored)")
    print(f"  conflicting claims (AC-11, reported separately): {breakdown['conflicting_count']}")

    # B-45: correct_partial/correct_semantic already went through their own extra scrutiny (a
    # real overlap check, or an LLM judge) to earn their credit -- excluded here the same as
    # correct/correct_abstention, not because they're exempt from review, but because they've
    # already had it. Everything still `incorrect`/`miss`/`unsupported`/`conflicting` remains.
    review_needed = [
        (site, s) for site, s in all_scores if not is_right_call(s.verdict)
    ]
    if review_needed:
        print(f"\n{len(review_needed)} field(s) worth a human spot-check "
              f"(non-right-call verdicts -- see wi/eval/scoring.py's docstring on "
              f"why strict normalising can unfairly flag a substantively-right free-text answer):")
        for site, s in review_needed:
            print(f"  [{s.verdict.value}] {site} / {s.field}")
            print(f"      label:  {s.label_status} -- {s.label_value!r}")
            print(f"      system: {s.system_status} -- {s.system_value!r} ({s.system_claim_id})")

    # Added 2026-09-28 (Uttam asked for cost/benefit visibility everywhere an LLM gets called,
    # not just run_site.py's extraction call): --semantic-judge makes one real OpenAI call per
    # still-incorrect eligible field, and until now that cost was invisible -- OpenAIJudgeCompleter
    # tracked it (wi/extract/llm.py) but nothing ever printed or saved it. semantic_judge is only
    # ever a real OpenAIJudgeCompleter (built by build_semantic_judge()) or None -- never a test
    # double without these attributes, since tests call apply_semantic_judging() directly with
    # their own fake, bypassing this function.
    judge_summary = None
    if semantic_judge is not None:
        upgraded = sum(1 for _, s in all_scores if s.verdict == Verdict.correct_semantic)
        from wi.config import load_config
        pricing = load_config().get("llm", {}).get("pricing_usd_per_1m_tokens", {})
        cost = estimate_cost_usd(semantic_judge.total_prompt_tokens,
                                  semantic_judge.total_completion_tokens,
                                  semantic_judge_model, pricing)
        judge_summary = {
            "model": semantic_judge_model,
            "calls": semantic_judge.call_count,
            "prompt_tokens": semantic_judge.total_prompt_tokens,
            "completion_tokens": semantic_judge.total_completion_tokens,
            "estimated_cost_usd": cost,
            "fields_upgraded_to_correct_semantic": upgraded,
        }
        cost_str = f"${cost:.4f}" if cost is not None else "unknown (no listed price)"
        pts = f"+{upgraded / overall_summary['total']:.0%}" if overall_summary["total"] else "+0%"
        print(f"\nSemantic judge ({semantic_judge_model}): {semantic_judge.call_count} call(s), "
              f"{semantic_judge.total_prompt_tokens + semantic_judge.total_completion_tokens} tokens, "
              f"estimated cost {cost_str} -- upgraded {upgraded} field(s) incorrect -> "
              f"correct_semantic ({pts} of headline accuracy)")

    report = {
        "generated_at": date.today().isoformat(),
        set_key: scored_sites,
        "per_site": per_site_results,
        "per_field": per_field_results,
        "overall": {**overall_summary, **breakdown},
        "semantic_judge": judge_summary,
    }
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {report_path.relative_to(ROOT)}")
    return report, 0


def build_semantic_judge(enabled: bool) -> Tuple[Optional[object], Optional[str]]:
    """B-45 (2026-09-27): builds a real OpenAIJudgeCompleter + model name when the caller passed
    `--semantic-judge`, else (None, None) -- the default, so a plain `python eval/baseline.py` or
    `python eval/held_out.py` makes no LLM/network call, exactly as both scripts' docstrings say.
    Shared here (rather than duplicated in held_out.py) so the two scripts can never drift on how
    the judge gets constructed."""
    if not enabled:
        return None, None
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    import os
    from wi.config import load_config
    from wi.extract.llm import OpenAIJudgeCompleter
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("--semantic-judge was passed but OPENAI_API_KEY is not set (check your .env) "
              "-- scoring without the semantic judge instead.")
        return None, None
    model = load_config()["llm"]["small_model"]
    return OpenAIJudgeCompleter(api_key=api_key), model


def main() -> int:
    semantic_judge_enabled = "--semantic-judge" in sys.argv[1:]
    judge, model = build_semantic_judge(semantic_judge_enabled)

    label_dir = DEV_LABEL_DIR
    run_dir = ROOT / "data" / "runs"
    report_path = ROOT / "eval" / "baseline_report.json"
    _report, code = run_scoring_set(
        DEV_SET, label_dir, run_dir, "dev_set", report_path, "all 5 sites combined",
        semantic_judge=judge, semantic_judge_model=model,
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
