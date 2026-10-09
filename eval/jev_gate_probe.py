#!/usr/bin/env python3
"""What-if probe (B-63, exploratory, changes nothing): would Jev have rescued claims that the
evidence check rejected?

For every rejected claim in the given run files whose quote really is on the page (the check said
"does not support the value", or the bare-label / no-signal rules, but NOT "quote not found"), ask
Jev one yes/no question: "does this quote support this value for this field?" and print Jev's
probability next to the check's reason and next to the hand label for the same field. Nothing is
written to a run file and the pipeline is not touched; the point is to see, on real data, whether a
Jev support-judge would rescue claims that are right or wrongly let through claims that are wrong.

Usage:
    python eval/jev_gate_probe.py                     # the 5 dev-set runs
    python eval/jev_gate_probe.py data/runs/notion_com.json data/runs/loom_com.json
Needs JEV_API_KEY in .env. Cost: a few cents at most.
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from eval.baseline import DEV_LABEL_DIR                 # noqa: E402
from wi.classify.decisions import parse_choice          # noqa: E402
from wi.classify.jev import JevClient, JevError         # noqa: E402
from wi.config import load_config                       # noqa: E402

DEV_RUNS = ["calendly_com", "loom_com", "typeform_com", "notion_com", "simplestores_in"]
LABEL_FILE = {"calendly_com": "calendly", "loom_com": "loom", "typeform_com": "typeform",
              "notion_com": "notion", "simplestores_in": "simplestores"}

QUESTION = {
    "type": "noul",
    "instructions": ("Decide whether the QUOTE, taken from a company's website, supports the CLAIMED "
                     "VALUE for the given field. Judge only what the quote itself says."),
    "criteria": {
        "true": "The quote states or clearly implies the claimed value for this field.",
        "false": "The quote does not state or imply the claimed value, or says something else.",
    },
}


def pairs(rej):
    v, e = rej["attempted_value"], rej["attempted_evidence"]
    if isinstance(v, list) and isinstance(e, list):
        return list(zip(v, e))
    if isinstance(v, list):
        return [(item, e) for item in v]
    return [(v, e)]


def main(paths):
    cfg = load_config()
    try:
        client = JevClient.from_env(cfg.get("classifier"))
    except JevError as e:
        print(e)
        return 1
    calls = tokens = 0
    for path in paths:
        slug = Path(path).stem
        run = json.loads(Path(path).read_text(encoding="utf-8"))
        label_path = DEV_LABEL_DIR / f"{LABEL_FILE.get(slug, slug)}.json"
        labels = json.loads(label_path.read_text(encoding="utf-8")) if label_path.exists() else {}
        todo = [r for r in run.get("rejected", []) if "quote not found" not in r["reason"]]
        print(f"\n=== {slug}: {len(todo)} rejected claim(s) with a real quote ===")
        for rej in todo:
            lab = labels.get(rej["field"], {})
            print(f"\n{rej['field']}\n  check said : {rej['reason'][:110]}\n  hand label : "
                  f"{json.dumps(lab.get('value'), ensure_ascii=False)[:150]}")
            for value, quote in pairs(rej):
                state = f"Field: {rej['field']}\nCLAIMED VALUE: {value}\nQUOTE: {quote}"
                try:
                    res = client.evaluate(state, {"supports": QUESTION})
                except JevError as e:
                    print(f"  ! Jev error: {e}")
                    continue
                calls += 1
                tokens += res.input_tokens
                parsed = parse_choice(res.answers.get("supports"), ["true", "false"])
                verdict = (f"{parsed[0]} (p={parsed[1]:.2f})" if parsed
                           else f"raw={json.dumps(res.answers.get('supports'))[:120]}")
                print(f"  Jev: {verdict:<18} value={json.dumps(value, ensure_ascii=False)[:60]}"
                      f"  quote={json.dumps(quote, ensure_ascii=False)[:90]}")
    print(f"\n{calls} Jev call(s), {tokens} input tokens (~${tokens * 0.042 / 1e6:.5f}).")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:] or [str(ROOT / "data" / "runs" / f"{s}.json") for s in DEV_RUNS]
    sys.exit(main(args))
