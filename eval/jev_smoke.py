#!/usr/bin/env python3
"""Smoke test for the TypeSafe Jev (System One) API. Makes ONE small real call so we can see the
actual request/response shape before building anything on it. Prints the HTTP status, latency, the
response JSON and the usage/quota block. Never prints the API key.

Setup: put your key in .env (git-ignored) as a line:   JEV_API_KEY=your-key-here
Run:   python eval/jev_smoke.py
Optional in .env: JEV_BASE_URL (default https://api.typesafe.ai/v1/systemone) and JEV_MODEL (default jev-latest).
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_URL = "https://api.typesafe.ai/v1/systemone"
# The API rejects a body without "model" (HTTP 422 seen on the first live call). jev-latest is the
# route named in the public write-ups; JEV_MODEL in .env overrides it (e.g. a pinned jev-1.13.0).
DEFAULT_MODEL = "jev-latest"

# A realistic pricing-page excerpt, in the same shape our cleaner now produces (B-61).
STATE = """Pricing
Free
$0 per member / month
Plus
$10 per member / month
Business
$20 per member / month
Enterprise
Custom pricing
Buttons and links on this page:
Get Notion free
Contact Sales
Request a demo
"""

QUESTIONS = {
    "sales_motion": {
        "type": "choice",
        "instructions": "How does a visitor become a customer according to this pricing page?",
        "criteria": {
            "self_serve": "Only self-serve signup or checkout cues; no contact-sales cue.",
            "sales_led": "Only contact-sales, demo or custom-quote cues; no self-serve signup.",
            "hybrid": "Both a self-serve signup cue and a contact-sales cue are present.",
            "unclear": "The text does not show how a visitor becomes a customer.",
        },
    },
    "has_free_plan": {
        "type": "noul",
        "instructions": "Does the page list a plan that costs nothing?",
        "criteria": {"true": "A free ($0) plan is listed.", "false": "No free plan is listed."},
    },
}


def main():
    load_dotenv(ROOT / ".env")
    key = os.environ.get("JEV_API_KEY", "").strip()
    if not key:
        print("JEV_API_KEY is not set. Add a line JEV_API_KEY=... to .env (never paste it in chat).")
        return 1
    url = os.environ.get("JEV_BASE_URL", DEFAULT_URL).strip() or DEFAULT_URL
    model = os.environ.get("JEV_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    body = {"model": model, "state": STATE, "questions": QUESTIONS}
    start = time.monotonic()
    try:
        resp = httpx.post(url, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=30)
    except httpx.HTTPError as e:
        print(f"Request failed before a response arrived: {type(e).__name__}: {e}")
        return 1
    elapsed = time.monotonic() - start
    print(f"HTTP {resp.status_code} in {elapsed * 1000:.0f} ms  (POST {url})")
    try:
        print(json.dumps(resp.json(), indent=2))
    except ValueError:
        print("Non-JSON body:", resp.text[:800])
    return 0 if resp.status_code == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
