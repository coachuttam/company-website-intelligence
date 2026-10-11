#!/usr/bin/env python3
"""Summary of a 13-site development comparison (B-101; eval/DEV13_PROTOCOL.md).

Usage: python eval/dev13_summary.py <control-ref> <candidate-ref> [...] [--dir data/archive/dev13]

Reads only the copied files in data/archive/dev13 (<ref>_r<round>_dev5.json, _v2.json, _runs/); makes
no model or network call. Prints, per ref and round, the strict and normalised headlines for dev5
(75 field-scores), v2 (120) and combined (195); per-ref means; verdict totals; the fields where a
candidate differs from the control by 2+ verdicts; latency; and the pass test for each candidate.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional

RIGHT = ("correct", "correct_partial", "correct_semantic", "correct_abstention")
VERDICTS = RIGHT + ("incorrect", "miss", "unsupported", "conflicting")
SETS = ("dev5", "v2")
NAME = re.compile(r"^(?P<ref>.+)_r(?P<round>\d+)_(?P<set>dev5|v2)\.json$")


def safe(ref: str) -> str:
    return ref.replace("/", "_")


def load(directory: Path) -> Dict[str, Dict[int, Dict[str, dict]]]:
    """{ref: {round: {"dev5": report, "v2": report}}} for every complete ref-round."""
    out: Dict[str, Dict[int, Dict[str, dict]]] = {}
    for f in sorted(directory.glob("*.json")):
        m = NAME.match(f.name)
        if m:
            out.setdefault(m["ref"], {}).setdefault(int(m["round"]), {})[m["set"]] = json.loads(f.read_text())
    return {ref: {r: s for r, s in rounds.items() if all(k in s for k in SETS)} for ref, rounds in out.items()}


def right_calls(report: dict) -> int:
    return sum(report["overall"]["counts"].get(k, 0) for k in RIGHT)


def headlines(sets: Dict[str, dict]) -> dict:
    """Strict and normalised accuracy (in %) for dev5, v2 and combined."""
    row = {}
    tot = {"strict": 0, "norm": 0, "n": 0}
    for s in SETS:
        rep = sets[s]
        n, strict = rep["overall"]["total"], right_calls(rep)
        norm = rep.get("normalised", {}).get("right_calls", strict)
        row[s] = (100 * strict / n, 100 * norm / n)
        tot["strict"] += strict
        tot["norm"] += norm
        tot["n"] += n
    row["combined"] = (100 * tot["strict"] / tot["n"], 100 * tot["norm"] / tot["n"])
    row["n"] = tot["n"]
    return row


def verdict_totals(rounds: Dict[int, Dict[str, dict]]) -> Dict[str, int]:
    t = {v: 0 for v in VERDICTS}
    for sets in rounds.values():
        for s in SETS:
            for v in VERDICTS:
                t[v] += sets[s]["overall"]["counts"].get(v, 0)
    return t


def field_totals(rounds: Dict[int, Dict[str, dict]]) -> Dict[str, Dict[str, int]]:
    t: Dict[str, Dict[str, int]] = {}
    for sets in rounds.values():
        for s in SETS:
            for field, v in sets[s]["per_field"].items():
                ft = t.setdefault(field, {k: 0 for k in VERDICTS})
                for k in VERDICTS:
                    ft[k] += v["counts"].get(k, 0)
    return t


def mean_combined_strict(rounds: Dict[int, Dict[str, dict]]) -> float:
    return statistics.mean(headlines(s)["combined"][0] for s in rounds.values())


def pass_test(control: Dict[int, Dict[str, dict]], cand: Dict[int, Dict[str, dict]]) -> Dict[str, bool]:
    """(1) combined strict mean >= control + 1.0 point; (2) unsupported total <= control + 3;
    (3) no field with more than 3 extra incorrect-or-unsupported verdicts than the control."""
    c_fields, k_fields = field_totals(control), field_totals(cand)
    worst = max((k_fields[f]["incorrect"] + k_fields[f]["unsupported"]
                 - c_fields.get(f, {}).get("incorrect", 0) - c_fields.get(f, {}).get("unsupported", 0))
                for f in k_fields) if k_fields else 0
    res = {
        "headline": mean_combined_strict(cand) >= mean_combined_strict(control) + 1.0,
        "unsupported": verdict_totals(cand)["unsupported"] <= verdict_totals(control)["unsupported"] + 3,
        "no_field_regression": worst <= 3,
    }
    res["overall"] = all(res.values())
    return res


def latency(directory: Path, ref: str) -> Optional[tuple]:
    vals = sorted(json.loads(f.read_text()).get("timing", {}).get("total_s")
                  for d in directory.glob(f"{safe(ref)}_r*_runs") for f in d.glob("*.json"))
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    q = lambda p: vals[min(len(vals) - 1, max(0, round(p * (len(vals) - 1))))]
    return q(0.5), q(0.95), len(vals)


def main(argv: List[str]) -> int:
    directory = Path("data/archive/dev13")
    if "--dir" in argv:
        i = argv.index("--dir")
        directory = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if len(argv) < 2:
        print(__doc__)
        return 2
    data = load(directory)
    refs = [safe(r) for r in argv]
    missing = [r for r in refs if not data.get(r)]
    if missing:
        print(f"no complete rounds for: {missing}")
        return 1
    control = refs[0]
    print("headlines (strict / normalised, %):  dev5 | v2 | combined")
    for ref in refs:
        for r, sets in sorted(data[ref].items()):
            h = headlines(sets)
            print(f"  {ref} r{r}: " + " | ".join(f"{h[k][0]:.1f} / {h[k][1]:.1f}" for k in ("dev5", "v2", "combined")))
        hs = [headlines(s) for s in data[ref].values()]
        print(f"  {ref} mean: " + " | ".join(
            f"{statistics.mean(h[k][0] for h in hs):.1f} / {statistics.mean(h[k][1] for h in hs):.1f}"
            for k in ("dev5", "v2", "combined")))
    spread = [headlines(s)["combined"][0] for s in data[control].values()]
    print(f"control round-to-round spread (combined strict): {max(spread) - min(spread):.1f} points "
          f"({', '.join(f'{x:.1f}' for x in spread)})")
    print("\nverdict totals over rounds (dev5 + v2):")
    for ref in refs:
        t = verdict_totals(data[ref])
        print(f"  {ref}: " + ", ".join(f"{k} {t[k]}" for k in VERDICTS if k != "conflicting" or t[k]))
    print("\nfields differing from the control by 2+ verdicts (candidate minus control):")
    cf = field_totals(data[control])
    any_diff = False
    for ref in refs[1:]:
        kf = field_totals(data[ref])
        for f in sorted(kf):
            d = {k: kf[f][k] - cf.get(f, {}).get(k, 0) for k in VERDICTS}
            d = {k: v for k, v in d.items() if abs(v) >= 2}
            if d:
                any_diff = True
                print(f"  {ref} {f}: " + ", ".join(f"{k} {v:+d}" for k, v in d.items()))
    if not any_diff:
        print("  none")
    print("\nlatency (timing.total_s):")
    for ref in refs:
        lat = latency(directory, ref)
        print(f"  {ref}: " + (f"p50 {lat[0]:.1f}s, p95 {lat[1]:.1f}s (n={lat[2]})" if lat else "no run files"))
    print("\npass test against the control:")
    for ref in refs[1:]:
        res = pass_test(data[control], data[ref])
        print(f"  {ref}: headline +1.0 {'PASS' if res['headline'] else 'FAIL'} | unsupported <= +3 "
              f"{'PASS' if res['unsupported'] else 'FAIL'} | no field > +3 incorrect/unsupported "
              f"{'PASS' if res['no_field_regression'] else 'FAIL'} | overall {'PASS' if res['overall'] else 'FAIL'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
