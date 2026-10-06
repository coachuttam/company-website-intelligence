# Company Website Intelligence (Samkhya.ai assignment)
One company URL in -> crawl -> clean -> LLM extraction of 15 fields -> evidence gate -> JSON + profile.

## Commands
- Run a site: python run_site.py <url> [--no-cache]
- Gate check: python eval/check_gate.py data/runs/<slug>.json
- Render page: python -m wi.render data/runs/<slug>.json
- Tests: python -m pytest -q
- Dev score: python eval/baseline.py [--semantic-judge]; one site: python eval/score_one.py <name>

## Layout
wi/crawl (url, fetch, clean, cache, sales_cues, js_fallback), wi/extract (prompt, llm, pipeline, focus),
wi/validate/evidence.py, wi/classify (Jev), wi/profile, wi/render, wi/eval/scoring.py, eval/, config.yaml.
Spec: docs/PRD.MD. Behaviour log: tests/BEHAVIOURS.md.

## Rules
- Every extracted/inferred value needs a real quote from the cited page. Never loosen the evidence gate to raise accuracy.
- Changed logic in pipeline.py or evidence.py: bump EXTRACTION_LOGIC_VERSION in wi/crawl/cache.py. Changed prompt: bump prompt_version in config.yaml.
- Every behaviour change needs a test and a row in tests/BEHAVIOURS.md (next id is B-75).
- Use --no-cache for any real measurement. Headline noise is about +/-3 points, so judge on 3 or more runs.
- Dev set (calendly, loom, typeform, notion, simplestores) is saturated. Do not tune against it. Never edit a label to match an output.
- Do not run or tune against the held-out set until a fresh set is labelled by hand and the code is tagged. Run it once.
- The 15-field schema is frozen. Never print or commit keys from .env.
- After each session, update PROGRESS.md (stale since 2026-09-27).

## State at last session
prompt_version 16, EXTRACTION_LOGIC_VERSION 19, focus_retry off (B-72), Jev on for sales_motion and revenue_model.
