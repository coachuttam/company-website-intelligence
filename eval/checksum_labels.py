#!/usr/bin/env python3
"""Freeze and check the held-out v2 label files (eval/benchmark_sites_v2.md, freeze protocol).

Usage:
    python eval/checksum_labels.py --write    # after every v2 file is labelled: writes eval/labels_v2.sha256
    python eval/checksum_labels.py --verify   # before the one held-out run: exit 0 only if unchanged

--write refuses while any file still has the template's placeholders (`date_labeled`
"YYYY-MM-DD" or an empty `company_name`), because an unlabelled template file reads as "every
field not_found" and would otherwise be frozen as if it were a real answer key.
Makes no network or model call.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
LABEL_DIR = ROOT / "eval" / "labels"
CHECKSUM_FILE = ROOT / "eval" / "labels_v2.sha256"
V2_SPLIT = "held_out_v2"


def v2_label_files(label_dir: Path = LABEL_DIR) -> List[str]:
    """The v2 label files, found from the files themselves: every eval/labels/*.json whose
    labeling_metadata.split is "held_out_v2" (templates excluded), sorted by name. No fixed count:
    the set is whatever eval/benchmark_sites_v2.md settled on."""
    names = []
    for path in sorted(label_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            meta = json.loads(path.read_text(encoding="utf-8")).get("labeling_metadata", {})
        except (ValueError, OSError):
            continue
        if meta.get("split") == V2_SPLIT:
            names.append(path.name)
    return names


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unlabelled(label_dir: Path, names: List[str]) -> List[str]:
    """Files that still carry the template's placeholders."""
    out = []
    for name in names:
        meta = json.loads((label_dir / name).read_text(encoding="utf-8")).get("labeling_metadata", {})
        if meta.get("date_labeled") in (None, "", "YYYY-MM-DD") or not meta.get("company_name"):
            out.append(name)
    return out


def write(label_dir: Path = LABEL_DIR, checksum_file: Path = CHECKSUM_FILE,
          names: Optional[List[str]] = None) -> Tuple[bool, str]:
    names = v2_label_files(label_dir) if names is None else names
    if not names:
        return False, f"not written: no label files with split {V2_SPLIT!r} found"
    pending = unlabelled(label_dir, names)
    if pending:
        return False, "not written: still unlabelled (template placeholders): " + ", ".join(pending)
    lines = [f"{_sha256(label_dir / n)}  {n}" for n in sorted(names)]
    checksum_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True, f"wrote {checksum_file.name} for {len(lines)} file(s)"


def verify(label_dir: Path = LABEL_DIR, checksum_file: Path = CHECKSUM_FILE,
           names: Optional[List[str]] = None) -> Tuple[bool, str]:
    names = v2_label_files(label_dir) if names is None else names
    if not checksum_file.exists():
        return False, f"{checksum_file.name} does not exist; run --write after labelling"
    recorded = {}
    for line in checksum_file.read_text(encoding="utf-8").splitlines():
        digest, name = line.split(None, 1)
        recorded[name.strip()] = digest
    problems = []
    if sorted(recorded) != sorted(names):
        problems.append(f"file list differs: recorded {sorted(recorded)}, expected {sorted(names)}")
    for name in sorted(names):
        path = label_dir / name
        if not path.exists():
            problems.append(f"{name}: missing")
        elif recorded.get(name) != _sha256(path):
            problems.append(f"{name}: changed since --write")
    return (not problems), ("all label files match" if not problems else "; ".join(problems))


def main(argv: List[str]) -> int:
    if argv not in (["--write"], ["--verify"]):
        print(__doc__)
        return 2
    ok, message = write() if argv == ["--write"] else verify()
    print(("OK: " if ok else "FAIL: ") + message)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
