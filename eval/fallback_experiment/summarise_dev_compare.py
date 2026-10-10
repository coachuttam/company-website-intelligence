"""Summary of data/archive/dev_compare (copied files only; no model calls)."""
import json, statistics, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent              # the 12 baseline/latency reports (committed)
RUNS = ROOT / "data/archive/dev_compare"           # the 30 run files (git-ignored, local only)
BUILDS, ROUNDS = ["main", "fallback"], [1, 2, 3]
V = ["correct", "correct_partial", "correct_semantic", "correct_abstention", "incorrect", "miss", "unsupported"]
SLUGS = ["calendly_com", "loom_com", "typeform_com", "notion_com", "simplestores_in"]

rep = {(b, r): json.load(open(OUT / f"{b}_r{r}_baseline.json")) for b in BUILDS for r in ROUNDS}
runs = {(b, r, s): json.load(open(RUNS / f"{b}_r{r}_runs/{s}.json")) for b in BUILDS for r in ROUNDS for s in SLUGS}

print("a) headline per round")
mean = {}
for b in BUILDS:
    accs = [rep[(b, r)]["overall"]["accuracy"] * 100 for r in ROUNDS]
    mean[b] = statistics.mean(accs)
    print(f"  {b:8s} " + " / ".join(f"{a:.1f}" for a in accs) + f"   mean {mean[b]:.1f}")

print("\nb) verdict counts summed over 3 rounds")
tot = {b: Counter() for b in BUILDS}
fld = {b: {} for b in BUILDS}
for b in BUILDS:
    for r in ROUNDS:
        tot[b].update({k: rep[(b, r)]["overall"]["counts"][k] for k in V})
        for f, v in rep[(b, r)]["per_field"].items():
            fld[b].setdefault(f, Counter()).update({k: v["counts"][k] for k in V})
print("  overall  | " + " | ".join(V))
for b in BUILDS:
    print(f"  {b:8s} | " + " | ".join(str(tot[b][k]) for k in V))
print("  per field (main -> fallback), only non-zero verdicts:")
for f in fld["main"]:
    m, x = fld["main"][f], fld["fallback"][f]
    print(f"  {f}: main {dict((k, m[k]) for k in V if m[k])} | fallback {dict((k, x[k]) for k in V if x[k])}")

print("\nc) fields where fallback differs from main by >= 2 verdicts (summed over 3 rounds)")
any_diff = False
for f in fld["main"]:
    diffs = {k: fld["fallback"][f][k] - fld["main"][f][k] for k in V if abs(fld["fallback"][f][k] - fld["main"][f][k]) >= 2}
    if diffs:
        any_diff = True
        print(f"  {f}: " + ", ".join(f"{k} {d:+d}" for k, d in diffs.items()))
if not any_diff:
    print("  none")

print("\nd) fallback records (fallback build)")
filled_list = []
filled_total = 0
for r in ROUNDS:
    recs = [(s, runs[("fallback", r, s)].get("fallback")) for s in SLUGS]
    attempted = sum(1 for _, x in recs if x and x["model_calls"] > 0)
    skipped = [(s, x["skipped_reason"]) for s, x in recs if x and x["skipped_reason"]]
    fa = sum(len(x["attempted_fields"]) for _, x in recs if x)
    fi = sum(len(x["filled_fields"]) for _, x in recs if x)
    rj = sum(len(x["rejected_fields"]) for _, x in recs if x)
    calls = sum(x["model_calls"] for _, x in recs if x)
    secs = sum(x["seconds"] for _, x in recs if x)
    errs = [(s, x["error"]) for s, x in recs if x and x["error"]]
    filled_total += fi
    print(f"  round {r}: runs with a call {attempted}/5, skipped {len(skipped)} {skipped}, fields attempted {fa}, "
          f"filled {fi}, rejected {rj}, calls {calls}, seconds {secs:.1f}" + (f", errors {errs}" if errs else ""))
    for s, x in recs:
        if x and x["filled_fields"]:
            print(f"     {s}: filled {x['filled_fields']}")
            claims = {c["field"]: c for c in runs[("fallback", r, s)]["claims"]}
            for f in x["filled_fields"]:
                filled_list.append((r, s, f, claims[f]["value"], claims[f]["evidence"], claims[f]["source_url"]))

print("\ne) latency (timing.total_s)")
def pct(vals, q):
    vals = sorted(vals); k = (len(vals) - 1) * q; lo = int(k); hi = min(lo + 1, len(vals) - 1)
    return vals[lo] + (vals[hi] - vals[lo]) * (k - lo)
for b in BUILDS:
    t = [runs[(b, r, s)]["timing"]["total_s"] for r in ROUNDS for s in SLUGS]
    print(f"  {b:8s} p50 {pct(t, .5):.1f}s  p95 {pct(t, .95):.1f}s  (n={len(t)})")
fb_s = [runs[("fallback", r, s)]["timing"].get("fallback_s", 0.0) for r in ROUNDS for s in SLUGS]
print(f"  mean fallback phase seconds per run: {statistics.mean(fb_s):.1f}s")

print("\nf) pass test")
t1 = mean["fallback"] >= mean["main"] - 1
t2 = tot["fallback"]["unsupported"] <= tot["main"]["unsupported"] + 3
t3 = filled_total >= 5
print(f"  (1) fallback mean {mean['fallback']:.1f} >= main mean {mean['main']:.1f} - 1: {'PASS' if t1 else 'FAIL'}")
print(f"  (2) fallback unsupported {tot['fallback']['unsupported']} <= main {tot['main']['unsupported']} + 3: {'PASS' if t2 else 'FAIL'}")
print(f"  (3) fallback filled {filled_total} >= 5: {'PASS' if t3 else 'FAIL'}")
print(f"  overall: {'PASS' if t1 and t2 and t3 else 'FAIL'}")

print("\ng) every filled field")
for r, s, f, val, ev, src in filled_list:
    print(f"  r{r} {s} {f}: value={val!r} | evidence={ev!r} | source={src}")

print("\ncost (usage.estimated_cost_usd + classifier + judge)")
for b in BUILDS:
    c = sum((runs[(b, r, s)].get("usage") or {}).get("estimated_cost_usd") or 0 for r in ROUNDS for s in SLUGS)
    j = sum((rep[(b, r)].get("semantic_judge") or {}).get("estimated_cost_usd") or 0 for r in ROUNDS)
    jev = sum((runs[(b, r, s)].get("classifier") or {}).get("estimated_cost_usd") or 0 for r in ROUNDS for s in SLUGS)
    print(f"  {b:8s} extraction ${c:.4f}  judge ${j:.4f}  jev ${jev:.4f}  total ${c + j + jev:.4f}")
