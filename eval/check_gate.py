"""Week 1 gate check (Day 5): schema-valid output and evidence on every populated value.

Usage:  python eval/check_gate.py data/runs/<site>.json
The run file is a JSON list of claim objects, or {"claims": [...]}.
Exit code 0 = PASS, 1 = FAIL.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pydantic import ValidationError  # noqa: E402

from wi.schemas.claim import Claim, Status  # noqa: E402


def main(path: str) -> int:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_claims = data["claims"] if isinstance(data, dict) else data

    valid, problems = [], []
    for i, raw in enumerate(raw_claims):
        try:
            valid.append(Claim(**raw))
        except ValidationError as e:
            problems.append(f"claim #{i} ({raw.get('field', '?')}): {e.errors()[0]['msg']}")

    populated = [c for c in valid if c.status in (Status.extracted, Status.inferred)]
    with_evidence = [c for c in populated if c.evidence and c.source_url and c.retrieved_at]

    print(f"{Path(path).name}: {len(raw_claims)} claims, {len(valid)} schema-valid, "
          f"{len(with_evidence)}/{len(populated)} populated claims have evidence")
    for p in problems:
        print("  INVALID:", p)

    passed = not problems and len(with_evidence) == len(populated)
    print("PASS" if passed else "FAIL")
    return 0 if passed else 1


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1]))
