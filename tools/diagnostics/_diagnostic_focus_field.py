#!/usr/bin/env python3
"""Exploratory: does a field come back when the model sees ONLY the page(s) it lives on?

Fetches the given URL(s) the way the crawler does, cleans them, runs the normal extraction with just
those pages, and prints the claim for the requested field(s) (and anything rejected for it). Compare
with the full 40-page run: if the field is populated here but not_found there, the model is losing
the fact among too many pages. One model call (~1-3k tokens). Writes nothing (no run file, no cache).

Usage:
    python tools/diagnostics/_diagnostic_focus_field.py customers.industries https://www.snowflake.com/en/solutions/industries
    python tools/diagnostics/_diagnostic_focus_field.py traction.certifications URL1 URL2
"""
import os
import sys
from datetime import date
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from wi.config import load_config                          # noqa: E402
from wi.crawl.clean import clean_page, resolve_char_cap     # noqa: E402
from wi.crawl.fetch import USER_AGENT                      # noqa: E402
from wi.extract.llm import OpenAIChatCompleter             # noqa: E402
from wi.extract.pipeline import extract_claims             # noqa: E402


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    field, urls = argv[0], argv[1:]
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        print("OPENAI_API_KEY is not set (check your .env).")
        return 1
    cfg = load_config()
    pages = []
    with httpx.Client(follow_redirects=True, timeout=30, headers={"User-Agent": USER_AGENT}) as client:
        for u in urls:
            r = client.get(u)
            r.raise_for_status()
            pages.append(clean_page(str(r.url), r.text, resolve_char_cap(str(r.url), cfg)))
            print(f"page {r.url}: cleaned {len(pages[-1].text)} chars")
    completer = OpenAIChatCompleter(api_key=key, temperature=cfg.get("llm", {}).get("temperature", 0.1))
    site = urls[0].split("/")[2]
    run = extract_claims(f"https://{site}/", pages, cfg, completer, cache=None,
                         retrieved_at=date.today().isoformat())
    for c in run.claims:
        if c.field == field:
            print(f"\n{c.field}: {c.status.value}\n  value   : {c.value}\n  evidence: {c.evidence}")
    for rej in getattr(run, "rejected", []) or []:
        rf = rej.get("field") if isinstance(rej, dict) else getattr(rej, "field", None)
        if rf == field:
            print(f"\nREJECTED: {rej}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
