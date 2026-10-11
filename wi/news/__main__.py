"""Command line: python -m wi.news data/runs/<slug>.json [-o data/news]
Collects the company's own news snapshot for a saved run (no re-crawl, no model call) and writes
data/news/<slug>.json. See wi/news/__init__.py for the scope (PRD Section 8 cut line)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wi.news.collect import collect_for_run


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Company-own news snapshot for a saved run.")
    parser.add_argument("run_json")
    parser.add_argument("-o", "--out-dir", default="data/news")
    args = parser.parse_args(argv)
    report, out = collect_for_run(Path(args.run_json), Path(args.out_dir))
    if report is None:
        print("Could not find the company's home URL in the run file.")
        return 1
    print(f"news: {report.status} ({len(report.items)} item(s), {report.record.get('latency_s')}s)"
          + (f": {report.reason}" if report.reason else "") + f" -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
