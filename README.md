# Company Website Intelligence Prototype

Given one public company website URL, produce a structured, evidence-backed profile of what the company states on its own website.
A company website is a **self-reported source**. Claims are never presented as independently verified.

Spec: Final PRD v1.0 (Notion: "1. Final PRD").

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt       # core + pytest
cp .env.example .env                      # add the API key for the provider (openai, per config.yaml -- approved by Abhishek, 2026-09-27)
```

Install exactly one LLM client by uncommenting a line in `requirements-llm.txt`, then `pip install -r requirements-llm.txt`.
Set `llm.provider`, `llm.small_model` and `llm.escalation_model` in `config.yaml`.

## Run the tests

```bash
pytest -q
```

## Project layout

| Path | Purpose | Week |
| --- | --- | --- |
| `config.yaml` | All caps, limits, model names, targets (PRD Section 13) | 1 |
| `wi/schemas/claim.py` | The claim contract and four statuses | 1 (done) |
| `wi/crawl/url.py` | URL validation and approved domains | 1 (done), redirects and robots in 2 |
| `wi/validate/evidence.py` | Deterministic quote and value-support checks | 1 (done) |
| `wi/crawl/` | Discovery, fetch, clean, cache | 2 |
| `wi/extract/` | Deterministic extraction, passage selection, model calls | 3 |
| `wi/profile/` | Ledger to canonical profile, conflicts, coverage | 3 |
| `wi/render/` | Read-only reference page (reads JSON, no AI call) | 4 |
| `eval/` | Benchmark site list, label template, scorer, gate check | 1 to 4 |
| `tests/` | Behaviour tests. `BEHAVIOURS.md` is the full list from PRD Appendix B | all |
| `data/raw`, `data/clean`, `data/runs`, `data/labels` | Downloaded pages, cleaned text, run outputs, answer keys | all |

## Rules that never change

1. Never invent missing information. Return `not_found` with coverage.
2. Every `extracted` or `inferred` claim needs source URL, exact quote and retrieval date.
3. The quote must appear on the page **and** support the value (checked by code, not by the model).
4. Do not tune on held-out sites. Tag `pre-heldout` before the Week 4 run.
5. Log tokens, latency and cost for every run from the first model call.
