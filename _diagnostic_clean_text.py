#!/usr/bin/env python3
"""Exploratory, read-only: fetch one or more URLs exactly the way the crawler does and print the
CLEANED text the model would see (plus its length), so "why was this field not_found?" can be
answered by looking at the page text instead of guessing.

Usage:
    python _diagnostic_clean_text.py https://www.snowflake.com/en/solutions/industries
    python _diagnostic_clean_text.py URL1 URL2 --chars 3000     # print up to 3000 chars per page
Changes nothing; makes no model call.
"""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wi.config import load_config                    # noqa: E402
from wi.crawl.clean import clean_page, resolve_char_cap   # noqa: E402
from wi.crawl.fetch import USER_AGENT                # noqa: E402


def main(argv):
    chars = 2000
    if "--chars" in argv:
        i = argv.index("--chars")
        chars = int(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print(__doc__)
        return 1
    cfg = load_config()
    with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": USER_AGENT}) as client:
        for url in argv:
            print("=" * 100)
            try:
                r = client.get(url)
            except httpx.HTTPError as e:
                print(f"{url}\n  fetch failed: {e}")
                continue
            page = clean_page(str(r.url), r.text, resolve_char_cap(str(r.url), cfg))
            print(f"{url}\n  HTTP {r.status_code}, raw {len(r.text)} chars -> cleaned {len(page.text)} chars\n")
            print(page.text[:chars])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
