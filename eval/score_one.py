#!/usr/bin/env python3
"""Score exactly one site -- dev-set or held-out -- without the other 4 or 9 scrolling past it.

eval/baseline.py and eval/held_out.py always score their whole fixed site list in one call;
there was no way to check just the one site you just ran without hunting for its block in a
much longer printout (or, worse, misreading a neighbouring site's numbers as your own). This
script reuses eval/baseline.py's own run_scoring_set() -- the exact same core both of those
call -- with a one-item site list, so the number this prints is always identical to what
baseline.py/held_out.py would print for that site on their own; there is no second scoring
implementation to drift out of sync with either one.

Usage:
    python eval/score_one.py basecamp
    python eval/score_one.py razorpay --semantic-judge

The name is the label file's own name (eval/labels/<name>.json), with or without ".json" --
same name eval/baseline.py's DEV_SET or eval/held_out.py's HELD_OUT_LABELS already use. Looked
up in both: a dev-set name uses DEV_SET's confirmed run-file pairing directly; a held-out name
goes through eval/held_out.py's own at-execution-time run-file resolution (same
"fail loudly, never silently on an ambiguous or missing run file" behaviour, see that module).

Makes no LLM or network call unless --semantic-judge is passed, exactly like the two scripts
this reuses.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.baseline import DEV_SET, build_semantic_judge, run_scoring_set  # noqa: E402
from eval.held_out import HELD_OUT_LABELS, _resolve_run_file  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _resolve_site(name: str, run_dir: Path) -> Tuple[Optional[List[Tuple[str, str]]], Optional[str]]:
    """Returns (site_set, error_message). site_set is a one-item list ready for
    run_scoring_set(), or None with error_message explaining why (unknown name, or a held-out
    site with no run file yet / an ambiguous one)."""
    label_file = name if name.endswith(".json") else f"{name}.json"

    for lf, run_file in DEV_SET:
        if lf == label_file:
            return [(lf, run_file)], None

    for lf, candidates in HELD_OUT_LABELS:
        if lf == label_file:
            resolved, matches = _resolve_run_file(candidates, run_dir)
            if resolved is not None:
                return [(lf, resolved)], None
            if matches:
                return None, f"ambiguous run file for {name!r}, candidates found = {matches}"
            return None, (f"no run file found under data/runs/ for {name!r} yet -- run "
                           f"`python run_site.py <url> --no-cache` for it first")

    known = sorted(lf.removesuffix(".json") for lf, _ in DEV_SET) + \
            sorted(lf.removesuffix(".json") for lf, _ in HELD_OUT_LABELS)
    return None, f"{name!r} isn't a known dev-set or held-out site. Known: {', '.join(known)}"


def main() -> int:
    positional = [a for a in sys.argv[1:] if a != "--semantic-judge"]
    if len(positional) != 1:
        print(__doc__)
        return 2
    name = positional[0]

    label_dir = ROOT / "eval" / "labels"
    run_dir = ROOT / "data" / "runs"

    site_set, error = _resolve_site(name, run_dir)
    if site_set is None:
        print(error)
        return 1

    judge, model = build_semantic_judge("--semantic-judge" in sys.argv[1:])
    report_path = ROOT / "eval" / f"score_one_{name.removesuffix('.json')}_report.json"
    _, exit_code = run_scoring_set(
        site_set, label_dir, run_dir, set_key=name,
        report_path=report_path, per_field_heading=name,
        semantic_judge=judge, semantic_judge_model=model,
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
