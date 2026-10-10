#!/usr/bin/env bash
# Dev comparison, main versus post-heldout-v2-fallback, back to back (3 rounds, alternating order).
# Five dev sites only. Stops at the first non-zero exit; no retries. Outputs go to
# data/archive/dev_compare/ (git-excluded). Tracked reports are restored after every build.
set -u
cd "$(dirname "$0")/../.."

SITES=(https://calendly.com/ https://www.loom.com/ https://www.typeform.com/ https://www.notion.com/ https://simplestores.in/)
SLUGS=(calendly_com loom_com typeform_com notion_com simplestores_in)
OUT=data/archive/dev_compare
mkdir -p "$OUT"

fail() { echo "FAILED: $*" >&2; exit 1; }

[ -z "$(git status --porcelain)" ] || fail "working tree is not clean"
git rev-parse --verify -q main >/dev/null || fail "branch main missing"
git rev-parse --verify -q post-heldout-v2-fallback >/dev/null || fail "branch post-heldout-v2-fallback missing"

run_build() {   # $1 = build name (main|fallback), $2 = branch, $3 = round
  local build=$1 branch=$2 round=$3 t0 i
  t0=$(date +%s)
  git checkout -q "$branch" || fail "checkout $branch (build $build, round $round)"
  for i in "${!SITES[@]}"; do
    python run_site.py "${SITES[$i]}" --no-cache > "$OUT/${build}_r${round}_${SLUGS[$i]}.log" 2>&1 \
      || fail "run_site.py exit $? (build $build, round $round, site ${SITES[$i]}); log: $OUT/${build}_r${round}_${SLUGS[$i]}.log"
  done
  python eval/baseline.py --semantic-judge > "$OUT/${build}_r${round}_baseline.log" 2>&1 \
    || fail "baseline.py exit $? (build $build, round $round)"
  python eval/latency_report.py > "$OUT/${build}_r${round}_latency.log" 2>&1 \
    || fail "latency_report.py exit $? (build $build, round $round)"
  cp eval/baseline_report.json "$OUT/${build}_r${round}_baseline.json"
  cp eval/latency_report.json "$OUT/${build}_r${round}_latency.json"
  mkdir -p "$OUT/${build}_r${round}_runs"
  for i in "${!SLUGS[@]}"; do cp "data/runs/${SLUGS[$i]}.json" "$OUT/${build}_r${round}_runs/"; done
  git checkout -- eval/baseline_report.json eval/latency_report.json
  [ -z "$(git status --porcelain)" ] || fail "tree not clean after build $build, round $round"
  echo "DONE build=$build round=$round headline=$(python3 -c "import json;print(round(json.load(open('$OUT/${build}_r${round}_baseline.json'))['overall']['accuracy']*100,1))")% seconds=$(( $(date +%s) - t0 ))"
}

for round in 1 2 3; do
  if [ "$round" = 2 ]; then
    run_build fallback post-heldout-v2-fallback "$round"; run_build main main "$round"
  else
    run_build main main "$round"; run_build fallback post-heldout-v2-fallback "$round"
  fi
done

git checkout -q post-heldout-v2-fallback || fail "final checkout"
[ -z "$(git status --porcelain)" ] || fail "tree not clean at the end"
echo "ALL DONE on $(git branch --show-current)"
