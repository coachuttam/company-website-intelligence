#!/usr/bin/env python3
"""DIAGNOSTIC ONLY -- not part of the production pipeline, writes nothing into the
project besides this file itself and its own output file. Reuses wi.config /
wi.crawl.fetch / wi.crawl.clean read-only for the same 40-page Loom corpus the
production pipeline uses, then bypasses wi.extract.prompt (Rule 18) and
wi.extract.pipeline (evidence checker) entirely with a separate, unfiltered
candidate-enumeration prompt. Safe to delete after use."""
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("CWI_PROJECT_ROOT", ".")).resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
from wi.config import load_config
from wi.crawl.clean import clean_page, resolve_char_cap
from wi.crawl.fetch import crawl_site
from wi.crawl.url import validate_company_url

load_dotenv(PROJECT_ROOT / ".env")
config = load_config(PROJECT_ROOT / "config.yaml")

validated = validate_company_url("https://www.loom.com/")
if validated.status != "ok":
    print(f"REJECTED ({validated.error_code}): {validated.message}")
    sys.exit(1)

print(f"Crawling {validated.url} ...")
crawl_result = crawl_site(validated.url, validated.approved_domains, config)
ok_pages = [p for p in crawl_result.pages if p.status == "ok" and p.html]
print(f"  fetched {len(crawl_result.pages)} page(s), {len(ok_pages)} usable")

clean_pages = [clean_page(p.url, p.html, resolve_char_cap(p.url, config)) for p in ok_pages]
for cp in clean_pages:
    print(f"  cleaned {cp.url}: {len(cp.text)} chars" + (" (truncated)" if cp.truncated else ""))

page_blocks = [
    f"--- PAGE ---\nURL: {p.url}\nTITLE: {p.title or '(no title)'}\nTEXT:\n{p.text}\n"
    for p in clean_pages
]

DIAGNOSTIC_SYSTEM_PROMPT = """You are conducting a read-only research review of a company \
website's crawled content. You are NOT extracting a structured profile and you are NOT \
applying any product-naming policy or filter. Your only job is discovery.

Review the entire supplied website corpus and enumerate every candidate that could reasonably \
be a named product or productized offering.

For each candidate provide:
1. candidate name
2. source URL
3. exact supporting quote
4. one-sentence reason why it appears to be a named product/offering

Do not decide whether the candidate ultimately qualifies for products.names. Do not filter out \
candidates because they may be features, use cases, solutions, audience-specific offerings, or \
marketing phrases -- include them anyway, and let the "reason" field describe what kind of \
thing you think it is. The purpose is only to discover what product-name candidates you notice \
across the corpus, not to judge them.

Return a JSON object with exactly one top-level key "candidates": a list of objects each with \
exactly the keys "name", "source_url", "quote", "reason"."""

user_content = "Company website: https://www.loom.com/\n\n" + "\n".join(page_blocks)

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("OPENAI_API_KEY is not set (check your .env). Cannot call the LLM.")
    sys.exit(1)

from openai import OpenAI
client = OpenAI(api_key=api_key)
model = config["llm"]["small_model"]
temperature = config.get("llm", {}).get("temperature", 0.1)

print(f"Calling {model} (diagnostic enumeration -- no Rule 18, no schema, no evidence checker) ...")
response = client.chat.completions.create(
    model=model,
    messages=[
        {"role": "system", "content": DIAGNOSTIC_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ],
    temperature=temperature,
    response_format={"type": "json_object"},
)
usage = response.usage
print(f"  tokens: {usage.total_tokens} ({usage.prompt_tokens} prompt + {usage.completion_tokens} completion)")

out_path = PROJECT_ROOT / "tools" / "diagnostics" / "_diagnostic_loom_candidates_output.json"
out_path.write_text(response.choices[0].message.content)
print(f"Wrote raw candidate list to {out_path}")
print()
print(response.choices[0].message.content)
