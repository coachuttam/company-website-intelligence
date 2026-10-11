#!/usr/bin/env bash
# 13-site development comparison (B-101): eval/dev13_compare.sh <rounds> <ref> [<ref> ...]
# The first ref is the control. For each round, every ref runs back to back, rotating which goes first.
# Per ref and round: run_site.py --no-cache on the 13 sites (5 dev + 8 v2, all development data),
# then eval/baseline.py and eval/held_out.py --set v2, both with --semantic-judge --normalised.
# Reports and run files are copied to data/archive/dev13/ (git-ignored); tracked reports the scorers
# rewrite are restored after every ref. Stops at the first non-zero exit; no retries.
# See eval/DEV13_PROTOCOL.md. Makes model calls (extraction, Jev, judge) and network calls.
set -u

# Re-exec from a temp copy so checking out another ref cannot remove or change the running script.
if [ -z "${DEV13_REEXEC:-}" ]; then
  REPO=$(cd "$(dirname "$0")/.." && pwd)
  TMP=$(mktemp -d)
  cp "$0" "$TMP/dev13_compare.sh"
  cp "$REPO/eval/dev13_summary.py" "$TMP/dev13_summary.py"
  DEV13_REEXEC=1 DEV13_REPO="$REPO" DEV13_TMP="$TMP" exec bash "$TMP/dev13_compare.sh" "$@"
fi
cd "$DEV13_REPO" || exit 1

[ $# -ge 2 ] || { echo "usage: eval/dev13_compare.sh <rounds> <ref> [<ref> ...]" >&2; exit 2; }
ROUNDS=$1; shift
REFS=("$@")
URLS=(https://calendly.com/ https://www.loom.com/ https://www.typeform.com/ https://www.notion.com/
      https://simplestores.in/ https://cashfree.com/ https://chargebee.com/ https://cohere.com/
      https://elevenlabs.io/ https://framer.com/ https://leadsquared.com/ https://mercury.com/ https://miro.com/)
SLUGS=(calendly_com loom_com typeform_com notion_com simplestores_in cashfree_com chargebee_com cohere_com
       elevenlabs_io framer_com leadsquared_com mercury_com miro_com)
OUT=data/archive/dev13
START=$(git rev-parse --abbrev-ref HEAD)

restore() {   # put back every tracked file a scorer rewrote
  local changed
  changed=$(git diff --name-only)
  [ -z "$changed" ] || git checkout -- $changed
}
fail() {
  echo "FAILED: $*" >&2
  restore
  git checkout -q "$START" 2>/dev/null
  exit 1
}

[ -z "$(git status --porcelain)" ] || { echo "FAILED: working tree is not clean" >&2; exit 1; }
for ref in "${REFS[@]}"; do git rev-parse --verify -q "$ref" >/dev/null || fail "unknown ref $ref"; done
(cd data/archive/heldout_v2_prefix && shasum -a 256 -c SHA256SUMS >/dev/null 2>&1) \
  || fail "data/archive/heldout_v2_prefix/SHA256SUMS does not verify (pre-fix v2 run files)"
mkdir -p "$OUT"

run_ref() {   # $1 = ref, $2 = round
  local ref=$1 round=$2 name=${1//\//_} t0 i
  t0=$(date +%s)
  git checkout -q "$ref" || fail "checkout $ref (round $round)"
  for i in "${!URLS[@]}"; do
    python run_site.py "${URLS[$i]}" --no-cache > "$OUT/${name}_r${round}_${SLUGS[$i]}.log" 2>&1 \
      || fail "run_site.py (ref $ref, round $round, site ${URLS[$i]}); log $OUT/${name}_r${round}_${SLUGS[$i]}.log"
  done
  python eval/baseline.py --semantic-judge --normalised > "$OUT/${name}_r${round}_dev5.log" 2>&1 \
    || fail "eval/baseline.py (ref $ref, round $round)"
  python -m eval.held_out --set v2 --semantic-judge --normalised > "$OUT/${name}_r${round}_v2.log" 2>&1 \
    || fail "eval/held_out.py --set v2 (ref $ref, round $round)"
  cp eval/baseline_report.json "$OUT/${name}_r${round}_dev5.json"
  cp eval/held_out_v2_report.json "$OUT/${name}_r${round}_v2.json"
  mkdir -p "$OUT/${name}_r${round}_runs"
  for i in "${!SLUGS[@]}"; do cp "data/runs/${SLUGS[$i]}.json" "$OUT/${name}_r${round}_runs/"; done
  restore
  [ -z "$(git status --porcelain)" ] || fail "tree not clean after ref $ref, round $round"
  echo "DONE ref=$ref round=$round seconds=$(( $(date +%s) - t0 ))"
}

n=${#REFS[@]}
for round in $(seq 1 "$ROUNDS"); do
  for k in $(seq 0 $((n - 1))); do
    run_ref "${REFS[$(( (k + round - 1) % n ))]}" "$round"
  done
done

git checkout -q "$START" || fail "final checkout of $START"
[ -z "$(git status --porcelain)" ] || fail "tree not clean at the end"
echo "ALL DONE on $START. Summary: python eval/dev13_summary.py ${REFS[*]}"
