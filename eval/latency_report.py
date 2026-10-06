#!/usr/bin/env python3
"""AC-10 / CST-02 latency, token and cost report (B-74).

Reads run JSONs already on disk and prints p50/p95 end-to-end latency, LLM tokens and estimated
variable cost per website, against config.yaml's targets (PRD Section 13: p50 <= 60 s,
p95 <= 180 s, mean cost <= USD 0.10, p95 cost <= USD 0.25). Makes no LLM or network call.

Usage:
    python eval/latency_report.py                         # the 5 dev-set runs (eval/baseline.py DEV_SET)
    python eval/latency_report.py data/runs/a.json ...    # any run files

Only runs written by run_site.py after B-74 carry a "timing" key, and only runs with
cache_status "miss" are real measurements, so produce the runs with --no-cache first. Skipped
runs are listed with the reason. Also writes eval/latency_report.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.baseline import DEV_SET  # noqa: E402
from wi.config import load_config  # noqa: E402
from wi.eval.latency import latency_report  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def _fmt(value, unit: str = "") -> str:
    if value is None:
        return "-"
    if unit == "$":
        return f"${value:.4f}"
    return f"{value:.1f}{unit}"


def main(argv: list) -> int:
    paths = [Path(a) for a in argv] or [ROOT / "data" / "runs" / run for _label, run in DEV_SET]
    runs = []
    for path in paths:
        if not path.exists():
            print(f"missing run file: {path}")
            return 1
        runs.append((path.stem, json.loads(path.read_text(encoding="utf-8"))))

    report = latency_report(runs, load_config().get("targets", {}))

    for r in report["sites"]:
        phases = ", ".join(f"{k[:-2]} {v:.1f}s" for k, v in r["phases"].items())
        print(f"{r['site']}: {r['total_s']:.1f}s ({phases}), {r['llm_tokens']} LLM tokens, "
              f"{r['jev_tokens']} Jev tokens, cost {_fmt(r['cost_usd'], '$')}, {r['pages']} pages")
    for s in report["skipped"]:
        print(f"{s['site']}: SKIPPED -- {s['reason']}")

    sm = report["summary"]
    print(f"\n{sm['sites_measured']} site(s) measured")
    print(f"  latency p50 {_fmt(sm['latency_p50_s'], 's')}, p95 {_fmt(sm['latency_p95_s'], 's')}")
    print(f"  LLM tokens p50 {_fmt(sm['llm_tokens_p50'])}, p95 {_fmt(sm['llm_tokens_p95'])}")
    print(f"  cost mean {_fmt(sm['cost_mean_usd'], '$')}, p95 {_fmt(sm['cost_p95_usd'], '$')}"
          + (f" ({sm['sites_with_unknown_cost']} site(s) with no listed price left out)"
             if sm["sites_with_unknown_cost"] else ""))
    for key, check in report["targets"].items():
        print(f"  {key}: {'met' if check['met'] else 'NOT met'} (target {check['target']})")

    out = ROOT / "eval" / "latency_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
